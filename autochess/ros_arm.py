"""Talking to the arm through ROS 2 (the ROBOTIS controllers, real or simulated).

Needs the arm bringup running first, either
  real:       ros2 launch open_manipulator_x_bringup hardware.launch.py port_name:=/dev/ttyACM0
  simulated:  ros2 launch open_manipulator_x_bringup base.launch.py use_sim:=false use_fake_hardware:=true fake_sensor_commands:=true start_rviz:=true
"""
import threading
import time

import rclpy
from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory, GripperCommand
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectoryPoint

from .kinematics import JOINTS

GRIPPER_OPEN, GRIPPER_CLOSED = 0.019, -0.01


class RosArm:
    def __init__(self):
        if not rclpy.ok():
            rclpy.init()
        self.node = Node("autochess_arm")
        self._angles = None
        self._gripper = None
        self._lock = threading.Lock()
        self.node.create_subscription(JointState, "/joint_states", self._on_joints, 10)
        self._arm = ActionClient(self.node, FollowJointTrajectory, "/arm_controller/follow_joint_trajectory")
        self._grip = ActionClient(self.node, GripperCommand, "/gripper_controller/gripper_cmd")
        self._exec = MultiThreadedExecutor()
        self._exec.add_node(self.node)
        self._spin = threading.Thread(target=self._exec.spin, daemon=True)
        self._spin.start()

    def _on_joints(self, msg):
        pos = dict(zip(msg.name, msg.position))
        with self._lock:
            if all(j in pos for j in JOINTS):
                self._angles = tuple(pos[j] for j in JOINTS)
            if "gripper_left_joint" in pos:
                self._gripper = pos["gripper_left_joint"]

    def angles(self, timeout=10.0):
        """(base, shoulder, elbow, wrist) in radians, or None if the arm isn't reporting."""
        end = time.time() + timeout
        while time.time() < end:
            with self._lock:
                if self._angles is not None:
                    return self._angles
            time.sleep(0.05)
        return None

    def move(self, q4, seconds):
        """Move all four joints to q4 over `seconds`, and wait. Returns True if it got there."""
        return self.move_path([q4], [seconds])

    def move_path(self, points, times):
        """Pass through each q4 in points, reaching point i at times[i] seconds from now; wait."""
        if not self._arm.wait_for_server(timeout_sec=10.0):
            raise RuntimeError("the arm controller isn't running (start the arm bringup first)")
        goal = FollowJointTrajectory.Goal()
        goal.trajectory.joint_names = JOINTS
        for q4, t in zip(points, times):
            sec = int(t)
            goal.trajectory.points.append(JointTrajectoryPoint(
                positions=[float(a) for a in q4],
                time_from_start=Duration(sec=sec, nanosec=int((t - sec) * 1e9))))
        done = self._send(self._arm, goal, times[-1] + 10)
        return done is not None and done.status == 4      # GoalStatus.STATUS_SUCCEEDED

    def gripper(self, position, effort=100.0):
        """Open or close the gripper. Returns where the fingers stopped (m), or None if it failed.
        Closing on a piece stops early; closing on nothing goes all the way to GRIPPER_CLOSED."""
        if not self._grip.wait_for_server(timeout_sec=10.0):
            raise RuntimeError("the gripper controller isn't running")
        goal = GripperCommand.Goal()
        goal.command.position = float(position)
        goal.command.max_effort = float(effort)
        done = self._send(self._grip, goal, 10)
        if done is None:
            return None
        time.sleep(0.2)
        with self._lock:
            finger = self._gripper
        return finger if finger is not None else done.result.position

    def _send(self, client, goal, timeout):
        sent = client.send_goal_async(goal)
        if not _wait(sent, 10) or not sent.result().accepted:
            return None
        done = sent.result().get_result_async()
        if not _wait(done, timeout):
            return None
        return done.result()

    def close(self):
        # Stop spinning and wait for it before destroying the node, or rclpy warns
        # "cannot use Destroyable because destruction was requested".
        self._exec.shutdown(timeout_sec=2.0)
        self._spin.join(timeout=2.0)
        self.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def _wait(future, timeout):
    end = time.time() + timeout
    while not future.done() and time.time() < end:
        time.sleep(0.02)
    return future.done()

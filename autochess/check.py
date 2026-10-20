"""Check that everything Auto-chess needs is installed:  python3 -m autochess.check

FAIL = must be fixed before playing. WARN = fine for now (e.g. the arm isn't plugged in yet).
"""
import grp
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

results = []


def report(status, what, detail=""):
    results.append(status)
    mark = {"ok": "  ok ", "warn": " WARN", "fail": " FAIL"}[status]
    print(f"[{mark}] {what}" + (f": {detail}" if detail else ""))


def check(what, fn, warn_only=False):
    try:
        detail = fn()
        report("ok", what, detail or "")
    except Exception as e:     # each check reports its own problem
        report("warn" if warn_only else "fail", what, str(e))


def version_below(v, limit):
    return tuple(int(x) for x in v.split(".")[:2]) < limit


# ---------- Python and packages ----------
def python():
    v = platform.python_version()
    if sys.version_info[:2] != (3, 10):
        raise RuntimeError(f"Python {v}; the Jetson uses 3.10 (other versions may work)")
    return v


def chess_pkg():
    import chess
    return chess.__version__


def numpy_pkg():
    import numpy
    if not version_below(numpy.__version__, (2, 0)):
        raise RuntimeError(f"NumPy {numpy.__version__}: ROS 2 Humble needs NumPy < 2 (pip3 install --user 'numpy<2')")
    return numpy.__version__


def opencv_pkg():
    import cv2
    if not version_below(cv2.__version__, (4, 12)):
        raise RuntimeError(f"OpenCV {cv2.__version__}: Robo's setup pins opencv-python < 4.12")
    return cv2.__version__


def tk_pkg():
    import tkinter
    if platform.system() == "Linux" and not os.environ.get("DISPLAY"):
        return f"Tk {tkinter.TkVersion} (no screen in this terminal: run on the Jetson's own desktop to see the window)"
    return f"Tk {tkinter.TkVersion}"


def piece_font():
    if platform.system() != "Linux":
        return "not needed on this computer"
    out = subprocess.run(["fc-list", "DejaVu Sans"], capture_output=True, text=True).stdout
    if not out.strip():
        raise RuntimeError("chess pieces may not draw: sudo apt install fonts-dejavu-core")
    return "DejaVu Sans"


# ---------- Stockfish and a full pretend game ----------
def stockfish():
    import chess
    from .engine import LEVEL_NAMES, Engine, find_stockfish
    path = find_stockfish()
    e = Engine(path)
    try:
        board = chess.Board()
        for name in LEVEL_NAMES:
            if e.choose(board, name, max_think=0.05) not in board.legal_moves:
                raise RuntimeError(f"level {name} gave an illegal move")
    finally:
        e.close()
    return f"{path}, all {len(LEVEL_NAMES)} levels answer"


def pretend_game():
    from .engine import Engine, Level
    from .game import Game, Player
    from .pretend import PretendArm
    fast = {"Fast": Level("Fast", skill=0, think=0.01, depth=1)}
    e = Engine(levels=fast)
    try:
        g = Game(Player("robot", "A", "Fast"), Player("robot", "B", "Fast"), 10, e, PretendArm(0, lambda s: None))
        g.run()
    finally:
        e.close()
    if g.result not in ("1-0", "0-1", "1/2-1/2"):
        raise RuntimeError(f"game ended with {g.result}")
    return f"robot vs robot finished: {g.result} ({g.reason}) after {len(g.board.move_stack)} moves"


# ---------- ROS 2 and the ROBOTIS software (Jetson only) ----------
def ros():
    distro = os.environ.get("ROS_DISTRO")
    if distro != "humble":
        raise RuntimeError("ROS 2 Humble isn't loaded in this terminal: source /opt/ros/humble/setup.bash "
                           "(Robo's ~/.bashrc does this)")
    import rclpy  # noqa: F401
    from control_msgs.action import FollowJointTrajectory, GripperCommand  # noqa: F401
    from sensor_msgs.msg import JointState  # noqa: F401
    return "Humble, rclpy, control_msgs, sensor_msgs"


def robotis():
    from ament_index_python.packages import get_package_share_directory
    share = get_package_share_directory("open_manipulator_x_bringup")
    if not (Path.home() / "colcon_ws" / "install" / "setup.bash").exists():
        raise RuntimeError("~/colcon_ws isn't built (see docs/robo_handoff.md section 4)")
    return share


def base_gains():
    xacro = (Path.home() / "colcon_ws/src/open_manipulator/open_manipulator_x_description/ros2_control/"
             "open_manipulator_x_system.ros2_control.xacro")
    if not xacro.exists():
        raise RuntimeError(f"{xacro} not found")
    if "400" not in xacro.read_text():
        raise RuntimeError("base servo gains (P 400) look missing: redo Robo's README Step 5b")
    return "P 400 found"


def dialout():
    user = os.environ.get("USER", "")
    groups = [g.gr_name for g in grp.getgrall() if user in g.gr_mem]
    if "dialout" not in groups and grp.getgrgid(os.getgid()).gr_name != "dialout":
        raise RuntimeError("add yourself: sudo usermod -aG dialout $USER, then log out and in")
    return "yes"


# ---------- hardware and other programs (warnings only) ----------
def arm_port():
    if not os.path.exists("/dev/ttyACM0"):
        raise RuntimeError("/dev/ttyACM0 not found (the OpenCR isn't plugged in; fine for now)")
    return "/dev/ttyACM0"


def camera():
    cams = sorted(str(p) for p in Path("/dev").glob("video*"))
    if not cams:
        raise RuntimeError("no /dev/video* (the camera isn't plugged in; fine for now)")
    return ", ".join(cams)


def power_mode():
    out = subprocess.run(["nvpmodel", "-q"], capture_output=True, text=True).stdout
    if "25W" not in out and "\n3" not in out:
        raise RuntimeError(f"{' '.join(out.split())}: Robo's setup uses sudo nvpmodel -m 3 (25 W)")
    return "25 W"


def robo_running():
    out = subprocess.run(["pgrep", "-af", "open_manipulator_x_bringup|ros2_control_node|robo.sh"],
                         capture_output=True, text=True).stdout.strip()
    if out:
        raise RuntimeError("Robo or another arm program is running: ~/Documents/Open_manipulator_x/launch/stop.sh")
    return "nothing else is using the arm"


def main():
    jetson = platform.system() == "Linux" and Path("/etc/nv_tegra_release").exists()
    print(f"Auto-chess check on {platform.node()} ({'Jetson' if jetson else platform.system()})\n")
    print("Python and packages")
    check("Python", python, warn_only=not jetson)
    check("python-chess", chess_pkg)
    check("NumPy", numpy_pkg)
    check("OpenCV", opencv_pkg)
    check("Tkinter", tk_pkg)
    check("Chess-piece font", piece_font, warn_only=True)
    print("\nChess")
    check("Stockfish", stockfish)
    check("A full pretend game", pretend_game)
    if jetson:
        print("\nROS 2 and the arm software")
        check("ROS 2", ros)
        check("ROBOTIS packages", robotis)
        check("Base servo gains", base_gains, warn_only=True)
        check("In the dialout group", dialout)
        print("\nHardware and other programs (warnings are fine until the robot is set up)")
        check("Arm port", arm_port, warn_only=True)
        check("Camera", camera, warn_only=True)
        check("Power mode", power_mode, warn_only=True)
        check("Robo stopped", robo_running, warn_only=True)
    else:
        print("\n(ROS 2, arm and camera checks only run on the Jetson.)")

    fails, warns = results.count("fail"), results.count("warn")
    print(f"\n{len(results) - fails - warns} ok, {warns} warnings, {fails} failed")
    if fails:
        print("Fix the FAIL lines, then run this again.")
    else:
        print("Everything Auto-chess needs is installed.")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

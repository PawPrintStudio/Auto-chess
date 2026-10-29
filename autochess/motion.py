"""Moving the fingertips around safely: joint moves between poses, and straight lines (up and down).

Every move is checked before it's sent: inside the joint limits, clear of the mount plate, and,
for joint moves, never lower than `floor` (a depth below the plate) along the way.
"""
import time

import numpy as np

from .kinematics import LIMITS, PARK, clear_of_mount, fingertip, ik, joints_xyz, within_limits

JOINT_SPEED = 0.6       # rad/s for the joint that moves furthest
LINE_SPEED = 60.0       # mm/s along straight lines
LINE_STEP = 8.0         # mm between points on a straight line
ARRIVE_TOL = 0.05       # rad (about 3 degrees): how far a joint may be from where it was sent and still count as there
ARRIVE_TIMEOUT = 2.0    # s the joints get to settle onto the pose they were sent to


class Unsafe(Exception):
    """A move was refused before it was sent."""


class Mover:
    def __init__(self, arm, joint_speed=JOINT_SPEED, line_speed=LINE_SPEED):
        self.arm = arm                      # RosArm (or a fake with angles/move/move_path/gripper)
        self.joint_speed, self.line_speed = joint_speed, line_speed
        self.q = None

    def refresh(self):
        q = self.arm.angles()
        if q is None:
            raise Unsafe("no joint angles from the arm: is the arm bringup running?")
        self.q = tuple(q)
        return self.q

    def where(self):
        return fingertip(self.q)

    def arrive(self, tol=None, timeout=None):
        """Check that the arm is really at the pose it was last sent to, waiting up to `timeout` s for
        the joints to settle. The controller says a move is done even when a joint stalled short (an
        elbow against its limit, say), so call this before the gripper closes or lets go: a piece let
        go from the wrong place falls on the wrong square. Raises Unsafe (the gripper isn't touched)
        if a joint stays more than `tol` rad off. Afterwards self.q is where the arm really is."""
        tol = ARRIVE_TOL if tol is None else tol
        timeout = ARRIVE_TIMEOUT if timeout is None else timeout
        target = np.array(self.q if self.q is not None else self.refresh())
        end = time.monotonic() + timeout
        while True:
            actual = self.arm.angles()
            if actual is None:
                raise Unsafe("no joint angles from the arm: is the arm bringup running?")
            off = np.array(actual, float) - target
            if np.max(np.abs(off)) <= tol:
                self.q = tuple(float(a) for a in actual)
                return
            if time.monotonic() >= end:
                self.q = tuple(float(a) for a in actual)       # later moves (parking) start from where it really is
                names = ("base", "shoulder", "elbow", "wrist")
                worst = ", ".join(f"{n} {np.degrees(d):+.1f}°" for n, d in zip(names, off) if abs(d) > tol)
                raise Unsafe(f"the arm stopped short of where it was sent ({worst} off): the gripper was not moved")
            time.sleep(0.05)

    def joint_move(self, q4, floor=None, seconds=None):
        """Move to q4 with all joints turning together. floor: the arm mustn't go deeper than this
        (a depth below the plate), or a function of the joint angles that says whether a pose is high enough."""
        start = np.array(self.q if self.q is not None else self.refresh())
        end = np.array(q4, float)
        if not within_limits(end):
            j = next(i for i, (a, (lo, hi)) in enumerate(zip(end, LIMITS)) if not lo <= a <= hi)
            raise Unsafe(f"the {['base', 'shoulder', 'elbow', 'wrist'][j]} is at the end of its range")
        for f in np.linspace(0, 1, 30)[1:]:
            q = start + (end - start) * f
            if not clear_of_mount(q[1:]):
                raise Unsafe("the move passes too close to the mount plate")
            low = (not floor(q)) if callable(floor) else (floor is not None and max(p[1] for p in joints_xyz(q[1:])) > floor)
            if low:
                raise Unsafe("the move would dip too low over the board")
        t = seconds or max(1.0, float(np.max(np.abs(end - start))) / self.joint_speed)
        if not self.arm.move(tuple(end), t):
            raise Unsafe("the arm didn't finish the move")
        self.q = tuple(end)

    def line_to(self, point, max_tilt=None):
        """Move the fingertips in a straight line to point (X, Y, Z)."""
        a, b = self.where(), np.array(point, float)
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / LINE_STEP)))
        qs, near = [], self.q
        kw = {} if max_tilt is None else {"max_tilt": max_tilt}
        for i in range(1, n + 1):
            q = ik(a + (b - a) * i / n, near=near, smooth=True, **kw)
            if q is None:
                raise Unsafe(f"can't reach {np.round(a + (b - a) * i / n)} (out of reach)")
            if np.max(np.abs(np.array(q) - np.array(near))) > 0.35:
                raise Unsafe("the arm would have to flip suddenly along this line")
            qs.append(q)
            near = q
        step = max(0.05, float(np.linalg.norm(b - a)) / n / self.line_speed)
        times = [0.2 + step * (i + 1) for i in range(n)]
        if not self.arm.move_path(qs, times):
            raise Unsafe("the arm didn't finish the move")
        self.q = qs[-1]

    def go_to(self, point, floor):
        """Get the fingertips to point (X, Y, Z) staying above floor: a joint move if it doesn't dip,
        otherwise up through the park pose (fold up, turn, come back down)."""
        q = ik(point, near=self.q)
        if q is None:
            raise Unsafe(f"can't reach {np.round(point)} (out of reach)")
        self.go_to_q(q, floor)

    def go_to_q(self, q, floor):
        """Joint move to q staying above floor, or up through the park pose if the direct move dips."""
        try:
            self.joint_move(q, floor=floor)
        except Unsafe as e:
            if "dip" not in str(e):
                raise
            try:
                self.joint_move((self.q[0], *PARK), floor=floor)
                self.joint_move((q[0], *PARK))
                self.joint_move(q, floor=floor)
            except Unsafe as e2:
                if "dip" not in str(e2):
                    raise
                self._route_to(q, floor)       # neither is clear of the board: search for a route that is

    def _route_to(self, q, floor):
        """Last resort: a chain of small joint moves from here to q that stays clear of the board (route.find)."""
        from .route import NoRoute, find
        if callable(floor):
            ok = floor
        else:
            ok = lambda q4: max(p[1] for p in joints_xyz(q4[1:])) <= floor
        try:
            moves = find(self.q, q, ok)
        except NoRoute as e:
            raise Unsafe(f"the move would dip too low over the board ({e})")
        times = np.cumsum([s for _, s, _ in moves])
        if not self.arm.move_path([m for m, _, _ in moves], [float(t) for t in times]):
            raise Unsafe("the arm didn't finish the move")
        self.q = tuple(float(x) for x in moves[-1][0])

    def park(self):
        base = float(np.clip(self.q[0] if self.q else self.refresh()[0], *LIMITS[0]))
        self.joint_move((base, *PARK))

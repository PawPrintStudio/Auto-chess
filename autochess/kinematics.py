"""Geometry of the OpenMANIPULATOR-X hanging upside down from the frame.

Arm frame, in mm: r = distance out from the base axis, z = depth below the mount plate.
(The arm doesn't know it's upside down: its "up" is our "down".) Joint angles in radians; for
shoulder, elbow and wrist, positive = forward. All 0 (ROBOTIS's home) is an L: the upper arm hangs
down and the forearm and gripper point sideways, ~205 mm below the plate. Hanging limp, the arm
is straight down: elbow about -1.57, just past its -1.5 limit.
"""
import numpy as np

SHOULDER = 76.5                       # shoulder joint below the plate
UPPER = np.array([24.0, 128.0])       # shoulder -> elbow at 0
FOREARM = np.array([124.0, 0.0])      # elbow -> wrist at 0
FINGERS = 150.0                       # wrist -> fingertips; the measured arm (480 mm) suggests ~150, not ROBOTIS's 126
GRIPPER_HALF_WIDTH = 35.0             # the gripper body sticks out this far each side of the wrist-fingertip line

JOINTS = ["joint1", "joint2", "joint3", "joint4"]
LIMITS = [(-2.8, 2.8), (-1.5, 1.5), (-1.5, 1.4), (-1.7, 1.9)]

# Folded up under the beam, clear of the plate and of the pieces. Lowest point ~236 mm below the
# plate (~195 mm above the board at a 430 mm mount, well over the 80 mm king); sticks out ~115 mm
# from the axis; fingertips ~100 mm below the plate.
PARK = (-1.24, 0.63, 1.42)            # shoulder, elbow, wrist; the base keeps its current angle

HANGING = (0.0, -1.57, 0.0)          # limp, straight down (shoulder, elbow, wrist)
START_SLACK = 0.12                    # how far past a limit a limp arm may start (elbow -1.57 vs -1.5)

PLATE_CLEARANCE = 70.0                # every part of the arm stays this far below the plate
BASE_RADIUS, BASE_DEPTH = 50.0, 95.0  # the base servo: forearm and gripper keep out of this


def _rot(v, a):
    """Turn a (forward, along-the-arm) vector forward by angle a."""
    return np.array([v[0] * np.cos(a) + v[1] * np.sin(a), -v[0] * np.sin(a) + v[1] * np.cos(a)])


def joints_xyz(q, fingers=FINGERS):
    """Shoulder, elbow, wrist and fingertip positions (r, z) for (shoulder, elbow, wrist) angles."""
    q2, q3, q4 = q
    s = np.array([0.0, SHOULDER])
    e = s + _rot(UPPER, q2)
    w = e + _rot(FOREARM, q2 + q3)
    t = w + _rot([fingers, 0.0], q2 + q3 + q4)
    return s, e, w, t


def outline(q, fingers=FINGERS):
    """Points along the upper arm, forearm and gripper (including the gripper's width)."""
    s, e, w, t = joints_xyz(q, fingers)
    f = np.linspace(0, 1, 15)[:, None]
    upper = s + (e - s) * f
    rest = np.vstack([e + (w - e) * f, w + (t - w) * f])
    d = t - w
    n = np.array([-d[1], d[0]]) / np.linalg.norm(d)
    g = w + d * np.linspace(0, 1, 8)[:, None]
    rest = np.vstack([rest, g + GRIPPER_HALF_WIDTH * n, g - GRIPPER_HALF_WIDTH * n])
    return upper, rest


def within_limits(q4, slack=0.0):
    """q4 = (base, shoulder, elbow, wrist)."""
    return all(lo - slack <= a <= hi + slack for a, (lo, hi) in zip(q4, LIMITS))


def clear_of_mount(q, fingers=FINGERS):
    """True if no part of the arm reaches into the plate/beam or the base servo."""
    upper, rest = outline(q, fingers)
    pts = np.vstack([upper, rest])
    if np.any(pts[:, 1] < PLATE_CLEARANCE):
        return False
    near_base = np.abs(rest[:, 0]) < BASE_RADIUS
    return not np.any(near_base & (rest[:, 1] < BASE_DEPTH))


def lowest(q, fingers=FINGERS):
    """Depth below the plate of the lowest part of the arm, mm."""
    upper, rest = outline(q, fingers)
    return float(max(upper[:, 1].max(), rest[:, 1].max()))


def path_clear(q_from, q_to, fingers=FINGERS, steps=40):
    """A straight joint-space move from q_from to q_to (shoulder, elbow, wrist) stays clear of the mount."""
    a, b = np.array(q_from, float), np.array(q_to, float)
    return all(clear_of_mount(a + (b - a) * f, fingers) for f in np.linspace(0, 1, steps)[1:])

"""Fold the hanging arm up into its park pose, clear of the pieces:  python3 -m autochess.park

Checks first that the arm reports sensible angles and that the whole move stays clear of the
mount plate and never goes lower than where the arm already is, then asks before moving.
"""
import argparse
import sys

import numpy as np

import itertools

from .kinematics import LIMITS, PARK, START_SLACK, clear_of_mount, lowest, within_limits

SPEED = 0.3          # rad/s for the joint that moves furthest: slow on purpose
MIN_SECONDS = 6.0    # for a move of all joints together
JOINT_NAMES = ["shoulder", "elbow", "wrist"]


def _worst(path):
    """Deepest point (mm below the plate) along a path of (shoulder, elbow, wrist), or None if any
    part of it comes too close to the mount."""
    worst = 0.0
    for a, b in zip(path, path[1:]):
        for f in np.linspace(0, 1, 40):
            q = a + (b - a) * f
            if not clear_of_mount(q):
                return None
            worst = max(worst, lowest(q))
    return worst


def plan(current):
    """[(q4, seconds), ...]: the moves that get the arm to the park pose from the current angles,
    never closer to the mount than allowed and never lower than the arm already is. All joints
    together if that's safe, otherwise one joint at a time in the safest order. Raises ValueError
    saying why not if there's no safe way."""
    if not within_limits(current, slack=START_SLACK):
        raise ValueError("the arm is past its joint limits (it may have slumped). Hold it, power it off, "
                         "let it hang straight down, then try again.")
    base = float(np.clip(current[0], *LIMITS[0]))
    a, park = np.array(current[1:], float), np.array(PARK)
    # 10 mm of slack: swinging out of a limp, straight-down hang dips a few mm (the upper arm's offset)
    allowed = lowest(a) + 10
    routes = [[a, park]]
    for order in itertools.permutations(range(3)):
        path, q = [a], a.copy()
        for j in order:
            q = q.copy()
            q[j] = park[j]
            path.append(q)
        routes.append(path)
    blocked_by_mount = False
    for path in routes:
        worst = _worst(path)
        if worst is None:
            blocked_by_mount = True
            continue
        if worst <= allowed:
            moves, prev = [], np.array([current[0], *a])
            for q in path[1:]:
                q4 = np.array([base, *q])
                t = float(np.max(np.abs(q4 - prev))) / SPEED
                moves.append((tuple(float(x) for x in q4), max(MIN_SECONDS if len(path) == 2 else 2.0, t)))
                prev = q4
            return moves
    if blocked_by_mount:
        raise ValueError("every way to the park pose from here passes too close to the mount plate or would "
                         "go lower than the arm is now. Hold the arm, power it off, let it hang straight down, "
                         "then try again.")
    raise ValueError("the way to the park pose would go lower than the arm is now (toward the pieces).")


def main():
    ap = argparse.ArgumentParser(description="Fold the hanging arm into its park pose")
    ap.add_argument("--yes", action="store_true", help="don't ask before moving")
    args = ap.parse_args()

    from .ros_arm import RosArm
    arm = RosArm()
    try:
        current = arm.angles()
        if current is None:
            sys.exit("No joint angles from the arm. Is the arm bringup running? (see README)")
        print("Now:  " + "  ".join(f"{a:+.2f}" for a in current) + "   (base, shoulder, elbow, wrist, rad)")
        try:
            moves = plan(current)
        except ValueError as e:
            sys.exit(f"Not moving: {e}")
        prev = current
        for i, (q4, seconds) in enumerate(moves, 1):
            changed = [JOINT_NAMES[j] for j in range(3) if abs(q4[j + 1] - prev[j + 1]) > 1e-6]
            what = "all joints together" if len(changed) > 1 else f"{changed[0]} only" if changed else "hold"
            print(f"Move {i}: " + "  ".join(f"{a:+.2f}" for a in q4) + f"   ({what}, {seconds:.0f} s)")
            prev = q4
        if not args.yes:
            input("Keep a hand near the arm and the 12 V switch. Press Enter to move (Ctrl+C to cancel)... ")
        for q4, seconds in moves:
            if not arm.move(q4, seconds):
                sys.exit("The move didn't finish: check the arm and the bringup terminal.")
        print("Parked.")
    finally:
        arm.close()


if __name__ == "__main__":
    main()

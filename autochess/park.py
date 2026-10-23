"""Fold the hanging arm up into its park pose, clear of the pieces:  python3 -m autochess.park

Checks first that the arm reports sensible angles and that the whole move stays clear of the
mount plate and never goes lower than where the arm already is, then asks before moving.
"""
import argparse
import sys

import numpy as np

from .kinematics import LIMITS, PARK, START_SLACK, lowest, path_clear, within_limits

SPEED = 0.3          # rad/s for the joint that moves furthest: slow on purpose
MIN_SECONDS = 6.0


def plan(current):
    """The park target and move time for the current angles, or raise ValueError saying why not."""
    if not within_limits(current, slack=START_SLACK):
        raise ValueError("the arm is past its joint limits (it may have slumped). Hold it, power it off, "
                         "let it hang straight down, then try again.")
    base = float(np.clip(current[0], *LIMITS[0]))
    target = (base, *PARK)
    if not path_clear(current[1:], PARK):
        raise ValueError("the way to the park pose passes too close to the mount plate from here. "
                         "Move the arm by hand to hang straight down, then try again.")
    a, b = np.array(current[1:]), np.array(PARK)
    start_low = lowest(current[1:])
    # 10 mm of slack: swinging out of a limp, straight-down hang dips a few mm (the upper arm's offset)
    if any(lowest(a + (b - a) * f) > start_low + 10 for f in np.linspace(0, 1, 40)):
        raise ValueError("the way to the park pose would go lower than the arm is now (toward the pieces).")
    seconds = max(MIN_SECONDS, float(np.max(np.abs(np.array(target) - np.array(current)))) / SPEED)
    return target, seconds


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
            target, seconds = plan(current)
        except ValueError as e:
            sys.exit(f"Not moving: {e}")
        print("Park: " + "  ".join(f"{a:+.2f}" for a in target) + f"   over {seconds:.0f} s")
        if not args.yes:
            input("Keep a hand near the arm and the 12 V switch. Press Enter to move (Ctrl+C to cancel)... ")
        ok = arm.move(target, seconds)
        print("Parked." if ok else "The move didn't finish: check the arm and the bringup terminal.")
    finally:
        arm.close()


if __name__ == "__main__":
    main()

"""Teach the arm where the board is:  python3 -m autochess.calibrate [--height 430]

You steer the fingertips with the keyboard to the centres of a1, h1 and a8 (just touching the board),
then to the spot where captured pieces are dropped. The result is saved in data/board.json.

  w / s   away from / toward the arm's front        r / f   up / down
  a / d   sideways                                   1 2 3   step 1, 5 or 20 mm
  Enter   this is the spot                           q       quit without saving
"""
import argparse
import sys
import termios
import tty

import chess
import numpy as np

from .geometry import GRIPPER_CLOSED, Board
from .motion import Mover, Unsafe
from .park import follow, plan

STEPS = {"1": 1.0, "2": 5.0, "3": 20.0}
MOVES = {"w": (1, 0, 0), "s": (-1, 0, 0), "a": (0, 1, 0), "d": (0, -1, 0), "r": (0, 0, -1), "f": (0, 0, 1)}


def read_key():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def jog(mover, prompt, deepest):
    """Let the user steer the fingertips; returns the point when they press Enter (None on q)."""
    step = 5.0
    print(f"\n>>> {prompt}")
    while True:
        p = mover.where()
        print(f"\r    fingertips X {p[0]:7.1f}  Y {p[1]:7.1f}  depth {p[2]:6.1f} mm   step {step:4.0f} mm   ",
              end="", flush=True)
        k = read_key().lower()
        if k in ("\n", "\r"):
            print()
            return p
        if k == "q":
            print()
            return None
        if k in STEPS:
            step = STEPS[k]
        elif k in MOVES:
            target = p + step * np.array(MOVES[k])
            if target[2] > deepest:
                print("\n    (that's below where the board should be: not going lower)")
                continue
            try:
                mover.line_to(target)
            except Unsafe:
                # Usually the spot behind the arm, where the base reaches the end of its range:
                # swing round the other way, never lower than now (up through the park pose if needed).
                try:
                    print("\n    swinging round...", end="", flush=True)
                    mover.go_to(target, floor=max(p[2], target[2]) + 10)
                    print(" done")
                except Unsafe as e:
                    print(f"\n    can't go there: {e}")


def main():
    ap = argparse.ArgumentParser(description="Calibrate the board position")
    ap.add_argument("--height", type=float, default=430.0,
                    help="roughly how far the board is below the arm's base plate, mm (default 430)")
    args = ap.parse_args()
    H = args.height

    from .ros_arm import RosArm
    arm = RosArm()
    mover = Mover(arm, joint_speed=0.4, line_speed=40.0)
    started = False
    try:
        q = mover.refresh()
        try:
            moves = plan(q)
        except ValueError as e:
            sys.exit(f"Not moving: {e}")
        print(__doc__)
        input("Clear the pieces off the board (leave the board in place). Keep a hand near the 12 V switch.\n"
              "Press Enter to park the arm and start... ")
        started = True
        if not follow(arm, moves):                # the same safe route as autochess.park
            sys.exit("The arm didn't finish going to its home pose.")
        mover.refresh()
        arm.gripper(GRIPPER_CLOSED)          # closed fingers make a pointer
        start = np.array([120.0, 0.0, H - 150.0])
        mover.go_to(start, floor=H - 100)

        corners = {}
        for name, where in (("a1", "White's left corner square"), ("h1", "White's right corner square"),
                            ("a8", "Black's corner square on White's left side")):
            p = jog(mover, f"Touch the centre of {name} ({where}) with the fingertips, then Enter.", H + 20)
            if p is None:
                return
            corners[name] = p
            mover.line_to(p - [0, 0, 60])
        b = Board(corners["a1"], corners["h1"], corners["a8"], drop=corners["a1"])
        fs, rs = b.square_size()
        print(f"\nSquares: {fs:.1f} mm along the ranks, {rs:.1f} mm along the files.")

        h8 = b.square(chess.H8, 15)
        mover.go_to(b.square(chess.H8, 60), floor=b.floor(40))
        mover.line_to(h8)
        if input("Check: are the fingertips 15 mm above the centre of h8? [y/n] ").strip().lower() != "y":
            print("Then something's off. Run the calibration again, touching the square centres carefully.")
            return
        mover.line_to(b.square(chess.H8, 60))

        p = jog(mover, "Move the fingertips 5-10 cm above the bin for captured pieces (where it lets go), then Enter.",
                b.floor(-20))
        if p is None:
            return
        b.drop = p
        b.save()
        print("Saved data/board.json.")
    except Unsafe as e:
        print(f"\nStopped: {e}")
    finally:
        if started:
            go_home(arm)
        arm.close()


def go_home(arm):
    """However the calibration ends (finished, q, or an error), fold the arm back into its park pose."""
    print("Going back to the home pose...")
    try:
        q = arm.angles()
        if q is None or not follow(arm, plan(q)):
            print("Couldn't go home: run python3 -m autochess.park")
    except ValueError as e:
        print(f"Couldn't go home: {e}")


if __name__ == "__main__":
    main()

"""Take the fingertips to named squares and stop above each, to check where the arm thinks they are.
No pieces needed (clear the board):

  python3 -m autochess.visit e2 e4 a1 h8            stop 40 mm above each square, in order
  python3 -m autochess.visit a1 h1 a8 h8 --height 15   corners, 15 mm above the board
  python3 -m autochess.visit --show                 only print where the corners are; no arm needed

At each stop it says where the fingertips are and waits for Enter. If a stop is above the wrong
square, the corners were calibrated in the wrong order or the board was turned: check with --show
and calibrate again. If it's the right square but the wrong height, the board height is off.
"""
import argparse
import sys

import chess
import numpy as np

from .geometry import Board
from .motion import Unsafe
from .robot_arm import RealArm

MIN_HEIGHT = 5.0        # never closer to the board than this, mm


def describe_corners(geo):
    """Where each corner is, as the arm sees it: the base angle that points at it (0 is the way the arm
    faces when the base is at zero), how far out it is, and how far below the base plate."""
    lines = []
    for name, sq in (("a1", chess.A1), ("h1", chess.H1), ("a8", chess.A8), ("h8", chess.H8), ("e4", chess.E4)):
        x, y, z = geo.square(sq)
        lines.append(f"  {name}: base angle {np.degrees(np.arctan2(y, x)):+6.0f} deg, {np.hypot(x, y):4.0f} mm out, "
                     f"{z:4.0f} mm below the base plate")
    lines.append(f"  files run from a to h in the direction {np.degrees(np.arctan2(*(geo.h1 - geo.a1)[1::-1])):+.0f} deg, "
                 f"ranks from 1 to 8 toward {np.degrees(np.arctan2(*(geo.a8 - geo.a1)[1::-1])):+.0f} deg (arm frame)")
    return "\n".join(lines)


def visit(arm, squares, height, wait=input, log=print):
    """Go home, then to `height` mm above each square in turn, waiting at each. Ends parked."""
    arm.start()
    try:
        for sq in squares:
            name = chess.square_name(sq)
            arm.mover.go_to(arm._above(sq), floor=arm._floor())
            arm.mover.line_to(arm.geo.square(sq, height))
            arm.mover.arrive()
            x, y, z = arm.mover.where()
            log(f"[visit] over {name}: fingertips {height:.0f} mm above the board, {np.hypot(x, y):.0f} mm out, "
                f"base angle {np.degrees(arm.mover.q[0]):+.0f} deg")
            wait(f"        Is that above {name}, {height:.0f} mm up? Press Enter for the next... ")
            arm.mover.line_to(arm._above(sq))
    finally:
        try:
            arm.mover.park()
        except Unsafe as e:
            log(f"[visit] couldn't park: {e}")


def main():
    ap = argparse.ArgumentParser(description="Stop above squares to check the calibration")
    ap.add_argument("squares", nargs="*", help="squares like e2 a1 h8")
    ap.add_argument("--height", type=float, default=40.0, help="mm above the board to stop at (default 40)")
    ap.add_argument("--show", action="store_true", help="only print where the corners are")
    args = ap.parse_args()
    geo = Board.load()
    print("Calibrated board, in the arm's frame:\n" + describe_corners(geo))
    if args.show:
        return
    if not args.squares:
        ap.error("name some squares, e.g. e2 e4 a1 h8 (or --show)")
    if args.height < MIN_HEIGHT:
        ap.error(f"--height must be at least {MIN_HEIGHT:.0f} mm")
    try:
        squares = [chess.parse_square(s.lower()) for s in args.squares]
    except ValueError as e:
        sys.exit(str(e))
    from .ros_arm import RosArm
    ros = RosArm()
    arm = RealArm(ros, geo)
    try:
        input("\nBoard clear of pieces, hands clear, a hand near the 12 V switch. Press Enter... ")
        visit(arm, squares, args.height)
    except (ValueError, Unsafe) as e:
        print(f"Stopped: {e}")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        ros.close()


if __name__ == "__main__":
    main()

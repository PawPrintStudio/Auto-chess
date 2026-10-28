"""Teach the arm every square of the board, one at a time:  python3 -m autochess.calibrate_squares

The arm goes over each square, 15 mm above the board, and you say whether the fingertips are
centred on it:

  y   yes, that's right (it's remembered as checked)
  n   no: steer the fingertips onto the centre of the square, just touching the board, gripper
      straight down, then Enter (same keys as autochess.calibrate). The arm then goes back over the
      square so you can check it, and asks again.
  s   skip this square for now          q   stop (everything so far is kept)

Each answer is saved straight away in data/board.json, so you can stop and carry on later: squares
already confirmed are skipped. Squares you steer replace the blend of the four corners there.

  python3 -m autochess.calibrate_squares            all the squares, rank by rank
  python3 -m autochess.calibrate_squares e2 e4 g1   only these
  python3 -m autochess.calibrate_squares --redo     ask about every square again
  python3 -m autochess.calibrate_squares --clear    forget the squares taught this way (no arm needed)

Calibrating the four corners again (autochess.calibrate) starts from scratch: it forgets these.
"""
import argparse
import sys
import termios

import chess
import numpy as np

from .calibrate import go_home, jog, lift, read_key
from .geometry import GRIPPER_CLOSED, Board
from .motion import Mover, Unsafe
from .park import follow, plan

HOVER = 15.0            # mm above the board for the check
ABOVE = 60.0            # mm above the board while moving between squares
LOWEST_ALLOWED = 25.0   # mm: while steering, nothing may go deeper than this below where the board is thought to be


def snake_order():
    """Rank by rank, alternating direction, so the arm never has far to go to the next square."""
    out = []
    for rank in range(8):
        files = range(8) if rank % 2 == 0 else range(7, -1, -1)
        out += [chess.square(f, rank) for f in files]
    return out


def ask_key(question, keys="ynsq"):
    """One key, no Enter, ignoring keys typed while the arm was moving."""
    print(question, end="", flush=True)
    while True:
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
        k = read_key().lower()
        if k in keys:
            print(k)
            return k


def go_over(mover, b, sq, height=HOVER):
    """Over square sq at `height` mm: up first if the fingertips are low, then across, then straight down."""
    try:
        here = mover.where()
        if b.height_above(here) < ABOVE - 1:
            mover.line_to(here - [0.0, 0.0, ABOVE - b.height_above(here)])
    except Unsafe:
        pass                                       # go_to's own checks decide what is possible from here
    mover.go_to(b.square(sq, ABOVE), floor=b.floor(ABOVE - 20))
    mover.line_to(b.square(sq, height))
    mover.arrive()


def teach(mover, b, squares, answer=ask_key, steer=jog, save=None, log=print):
    """Walk through `squares`: check each, steer the fingertips onto it if it's wrong. Returns
    "done" or "quit". `save` (default b.save) is called after every answer."""
    save = save or b.save
    for n, sq in enumerate(squares, 1):
        name = chess.square_name(sq)
        while True:
            go_over(mover, b, sq)
            a = answer(f"[{n}/{len(squares)}] Are the fingertips centred on {name}, about {HOVER:.0f} mm up?  "
                       f"y = yes, n = no, s = skip, q = quit: ")
            if a == "q":
                return "quit"
            if a == "s":
                break
            if a == "y":
                b.checked.add(sq)
                save()
                break
            depth = float(b.square(sq)[2])
            p = steer(mover, f"Steer the fingertips onto the centre of {name}, just touching the board, "
                             f"gripper straight down, then Enter (q = cancel).", depth + LOWEST_ALLOWED, depth,
                      straight=True)
            if p is not None:
                b.squares[sq] = np.array(p, float)
                b.checked.discard(sq)
                save()
                log(f"    {name} saved. Going back over it to check.")
                lift(mover, p, up=ABOVE)
        try:
            mover.line_to(b.square(sq, ABOVE))
        except Unsafe:
            pass
    return "done"


def main():
    ap = argparse.ArgumentParser(description="Teach the arm every square, one at a time")
    ap.add_argument("squares", nargs="*", help="only these squares, e.g. e2 e4 (default: all)")
    ap.add_argument("--redo", action="store_true", help="ask about every square again, even those confirmed")
    ap.add_argument("--clear", action="store_true", help="forget the squares taught this way, and exit")
    args = ap.parse_args()
    b = Board.load()
    if args.clear:
        b.squares.clear()
        b.checked.clear()
        b.save()
        print("Forgot the squares taught one by one. The four-corner calibration is untouched.")
        return
    try:
        wanted = [chess.parse_square(s.lower()) for s in args.squares] or snake_order()
    except ValueError as e:
        sys.exit(str(e))
    if not args.redo and not args.squares:
        wanted = [s for s in wanted if s not in b.checked]
    if not wanted:
        sys.exit("Every square is already confirmed. (--redo asks about all of them again.)")
    print(__doc__)
    print(f"{len(wanted)} squares to go.")

    from .ros_arm import RosArm
    arm = RosArm()
    mover = Mover(arm, joint_speed=0.4, line_speed=40.0)
    try:
        q = mover.refresh()
        try:
            moves = plan(q)
        except ValueError as e:
            sys.exit(f"Not moving: {e}")
        input("Clear the pieces off the board and tape it down. Keep a hand near the 12 V switch.\n"
              "Press Enter to park the arm and start... ")
        if not follow(arm, moves):
            sys.exit("The arm didn't finish going to its home pose.")
        mover.refresh()
        arm.gripper(GRIPPER_CLOSED)                    # closed fingers make a pointer
        result = teach(mover, b, wanted)
        print("\nStopped; everything so far is saved." if result == "quit" else
              f"\nAll done. {len(b.squares)} squares were steered by hand, {len(b.checked)} confirmed.")
    except (ValueError, Unsafe) as e:
        print(f"Stopped: {e}")
    except KeyboardInterrupt:
        print("\nStopped; everything so far is saved.")
    finally:
        go_home(arm)
        arm.close()


if __name__ == "__main__":
    main()

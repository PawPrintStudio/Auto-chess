"""Teach the arm every square by grabbing:  python3 -m autochess.calibrate_squares

Set the pieces up in the starting position. For each piece in turn you steer the fingertips to
exactly where they should grab it (centred on the piece, gripper straight down, a little above the
board, not touching it), with the pieces all standing. The arm never goes down by itself:

  * The first square you steer all the way yourself, because until you've shown it one square it
    can't know how deep the board really is.
  * After that, the arm goes over each next square by itself, stops 20 mm above the top of the piece
    (clear of it, even if its idea of the board is still a little off) and you steer the last bit.
  * Then it lifts and comes back down to the spot you showed, so you can check it is the perfect grab:
        y  yes     n  no, steer it again     s  skip this square for now     q  stop

Same keys as autochess.calibrate: a/z base, s/x shoulder, d/c elbow, f/v wrist, 1 2 3 step size,
m switches to fingertip keys (w s a d across, r f up and down), Enter = this is the spot, q = cancel.

Every answer is saved at once in data/board.json, so you can stop and carry on later: squares
already confirmed are skipped. A taught square is exactly right; the squares around it follow it, so
the ones in the middle (no pieces to grab) come out right too.

  python3 -m autochess.calibrate_squares             the 32 pieces, rank by rank
  python3 -m autochess.calibrate_squares e2 g1       only these (an empty one needs --piece: put one on it)
  python3 -m autochess.calibrate_squares --redo      ask about every square again
  python3 -m autochess.calibrate_squares --clear     forget what was taught this way (no arm needed)

Calibrating the four corners again (autochess.calibrate) starts from scratch: it forgets these.
"""
import argparse
import sys
import termios

import chess

from .calibrate import go_home, jog, read_key
from .geometry import PIECE_HEIGHT, Board
from .motion import Mover, Unsafe
from .park import follow, plan
from .robot_arm import NAMES, clearance_floor

CLEAR_TOP = 20.0        # mm above the top of the piece where the arm stops by itself
LOWEST_ALLOWED = 3.0    # mm: while steering, the fingertips can't get closer to the estimated board than this


def snake_order(squares):
    """Rank by rank, alternating direction, so the arm never has far to go to the next square."""
    return sorted(squares, key=lambda s: (chess.square_rank(s),
                                          chess.square_file(s) * (1 if chess.square_rank(s) % 2 == 0 else -1)))


def ask_key(question, keys="ynsq"):
    """One key, no Enter, ignoring keys typed while the arm was moving."""
    print(question, end="", flush=True)
    while True:
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
        k = read_key().lower()
        if k in keys:
            print(k)
            return k


def rise(mover, b):
    """Straight up to the carrying height, if the fingertips are lower than that."""
    try:
        up = b.travel - b.height_above(mover.where())
        if up > 1.0:
            mover.line_to(mover.where() - [0.0, 0.0, up])
    except Unsafe:
        pass                                       # go_to's own checks decide what is possible from here


def approach(mover, b, sq, height):
    """Over square sq with the fingertips `height` mm above the board: straight up to the carrying height,
    across at that height (clear of the pieces), then straight down."""
    rise(mover, b)
    mover.go_to(b.square(sq, b.travel), floor=clearance_floor(b))
    mover.line_to(b.square(sq, height))
    mover.arrive()


def teach(mover, b, squares, piece_at, answer=ask_key, steer=jog, save=None, log=print):
    """Walk through `squares`: show the arm the perfect grab on each. `piece_at(sq)` is the piece type
    standing there. Returns "done" or "quit". `save` (default b.save) is called after every answer."""
    save = save or b.save
    for n, sq in enumerate(squares, 1):
        name, pt = chess.square_name(sq), piece_at(sq)
        grip = b.grip[pt]
        manual = not b.squares          # nothing taught yet: the board height isn't known, so no moving by itself
        while True:
            if not manual:
                try:
                    approach(mover, b, sq, PIECE_HEIGHT[pt] + CLEAR_TOP)
                except Unsafe as e:
                    log(f"    couldn't go over {name} by itself ({e}): steer it there yourself.")
                    manual = True
            depth = float(b.square(sq)[2])
            # (The first square gets slack: the board may be deeper than the calibration says.)
            limit = depth + (30.0 if not b.squares else -LOWEST_ALLOWED)
            p = steer(mover, f"[{n}/{len(squares)}] Steer the fingertips to the perfect grab on the {NAMES[pt]} on "
                             f"{name}: centred on it, gripper straight down, a little above the board, not touching "
                             f"it. Enter = this is it, q = cancel.", limit, depth, straight=True)
            if p is None:
                break
            b.set_square(sq, p + [0.0, 0.0, grip])         # the board is `grip` below the fingertips of a grab
            b.checked.discard(sq)
            save()
            log(f"    {name} saved. Lifting and coming back down to check it.")
            try:
                approach(mover, b, sq, PIECE_HEIGHT[pt] + CLEAR_TOP)
                mover.line_to(b.square(sq, grip))
                mover.arrive()
            except Unsafe as e:
                log(f"    couldn't come back to {name} by itself: {e}")
            a = answer(f"[{n}/{len(squares)}] Is that the perfect grab on the {NAMES[pt]} on {name}?  "
                       f"y = yes, n = steer it again, s = skip, q = quit: ")
            if a == "y":
                b.checked.add(sq)
                save()
                break
            if a == "q":
                rise(mover, b)
                return "quit"
            if a == "s":
                break
            manual = True                  # "n": carry on from where it is
    rise(mover, b)
    return "done"


def main():
    ap = argparse.ArgumentParser(description="Teach the arm every square by grabbing")
    ap.add_argument("squares", nargs="*", help="only these squares, e.g. e2 g1 (default: the 32 pieces)")
    ap.add_argument("--piece", default="p", help="piece you put on a square with no piece at the start (p n b r q k)")
    ap.add_argument("--redo", action="store_true", help="ask about every square again, even those confirmed")
    ap.add_argument("--clear", action="store_true", help="forget the squares taught this way, and exit")
    args = ap.parse_args()
    b = Board.load()
    if args.clear:
        b.clear_squares()
        b.save()
        print("Forgot the squares taught one by one. The four-corner calibration is untouched.")
        return
    start = chess.Board()
    try:
        picked = [chess.parse_square(s.lower()) for s in args.squares]
        stand_in = chess.PIECE_SYMBOLS.index(args.piece.lower())
    except ValueError as e:
        sys.exit(str(e))
    wanted = snake_order(picked or [s for s in chess.SQUARES if start.piece_at(s)])
    if not args.redo and not picked:
        wanted = [s for s in wanted if s not in b.checked]
    if not wanted:
        sys.exit("Every square is already confirmed. (--redo asks about all of them again.)")
    bare = [s for s in wanted if not start.piece_at(s)]

    def piece_at(sq):
        piece = start.piece_at(sq)
        return piece.piece_type if piece else stand_in

    print(__doc__)
    if b.squares and not args.squares:
        print(f"{len(b.squares)} squares are already taught (--clear forgets them).")
    print(f"{len(wanted)} squares to go.")

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
        extra = (f"Also put a {NAMES[stand_in]} on {', '.join(chess.square_name(s) for s in bare)}.\n" if bare else "")
        input("Pieces in the starting position, board taped down. " + extra +
              "Keep a hand near the 12 V switch.\nPress Enter to park the arm and start... ")
        started = True
        if not follow(arm, moves):
            sys.exit("The arm didn't finish going to its home pose.")
        mover.refresh()
        arm.gripper(b.gripper_open)                    # open as when playing, so you can see how it fits round the piece
        result = teach(mover, b, wanted, piece_at)
        print("\nStopped; everything so far is saved." if result == "quit" else
              f"\nAll done: {len(b.checked)} squares confirmed.")
    except (ValueError, Unsafe) as e:
        print(f"Stopped: {e}")
    except KeyboardInterrupt:
        print("\nStopped; everything so far is saved.")
    finally:
        if started:
            go_home(arm)
        arm.close()


if __name__ == "__main__":
    main()

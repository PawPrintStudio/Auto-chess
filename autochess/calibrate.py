"""Teach the arm where the board is:  python3 -m autochess.calibrate [--height 430]

You steer the fingertips to the centres of a1, h1, a8 and h8 (just touching the board, gripper
straight down), then to the spot where captured pieces are dropped. The result is saved in data/board.json.

Joint keys (the default): each press turns one motor a little.
  a / z   base        +/-        1 2 3   step 1, 3 or 10 degrees
  s / x   shoulder    +/-        m       switch to fingertip keys
  d / c   elbow       +/-        Enter   this is the spot
  f / v   wrist       +/-        q       quit without saving

Fingertip keys (after m): w / s and a / d move across, r / f up and down, 1 2 3 = 1, 5 or 20 mm.
Wait for each move to finish before pressing the next key.
"""
import argparse
import sys
import termios
import tty

import chess
import numpy as np

from .geometry import GRIPPER_CLOSED, Board
from .kinematics import ik
from .motion import Mover, Unsafe
from .park import follow, plan

STEPS = {"1": 1.0, "2": 5.0, "3": 20.0}                 # mm, fingertip keys
MOVES = {"w": (1, 0, 0), "s": (-1, 0, 0), "a": (0, 1, 0), "d": (0, -1, 0), "r": (0, 0, -1), "f": (0, 0, 1)}
JOINT_STEPS = {"1": 1.0, "2": 3.0, "3": 10.0}           # degrees, joint keys
JOINT_KEYS = {"a": (0, 1), "z": (0, -1), "s": (1, 1), "x": (1, -1),
              "d": (2, 1), "c": (2, -1), "f": (3, 1), "v": (3, -1)}


def read_key():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def ask(question):
    """Ask a question, ignoring any keys typed earlier (e.g. while the arm was still moving)."""
    termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    return input(question)


def yes_no(question):
    while True:
        answer = ask(question).strip().lower()
        if answer in ("y", "yes", "n", "no"):
            return answer.startswith("y")
        print("Please type y or n, then Enter.")


def jog(mover, prompt, deepest, board_depth, straight=False):
    """Let the user steer the arm; returns the fingertip point when they press Enter (None on q).
    Nothing goes deeper than `deepest` (mm below the plate). With straight=True, Enter with the
    gripper tilted more than MAX_TILT asks for it to be straightened first (Enter again overrides)."""
    joint_mode, step, jstep = True, 5.0, 3.0
    warned = False
    print(f"\n>>> {prompt}")
    while True:
        p, q = mover.where(), mover.q
        tilt = abs(np.degrees(sum(q[1:]) + np.pi / 2))
        if joint_mode:
            status = (f"base {np.degrees(q[0]):+4.0f} sh {np.degrees(q[1]):+4.0f} el {np.degrees(q[2]):+4.0f}"
                      f" wr {np.degrees(q[3]):+4.0f} | {board_depth - p[2]:4.0f} mm up, tilt {tilt:2.0f}"
                      f" | step {jstep:2.0f} deg ")
        else:
            status = f"X {p[0]:6.0f} Y {p[1]:6.0f} | {board_depth - p[2]:4.0f} mm up | step {step:2.0f} mm "
        print("\r    " + status, end="", flush=True)
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)    # keys pressed while it was moving
        k = read_key().lower()
        if k in ("\n", "\r"):
            if straight and tilt > MAX_TILT and not warned:
                key = "v" if sum(q[1:]) + np.pi / 2 > 0 else "f"      # the wrist key that turns it back to straight
                print(f"\n    The gripper is tilted {tilt:.0f} deg: press {key} (wrist) to straighten it, touch the square"
                      f" again, then Enter. (Enter again to use it as it is.)")
                warned = True
                continue
            print()
            return p
        warned = False
        if k == "q":
            print()
            return None
        if k == "m":
            joint_mode = not joint_mode
            print("\n    " + ("joint keys: a/z base, s/x shoulder, d/c elbow, f/v wrist" if joint_mode
                              else "fingertip keys: w/s a/d across, r/f up and down"))
        elif joint_mode and k in JOINT_STEPS:
            jstep = JOINT_STEPS[k]
        elif not joint_mode and k in STEPS:
            step = STEPS[k]
        elif joint_mode and k in JOINT_KEYS:
            j, sign = JOINT_KEYS[k]
            target = list(q)
            target[j] += sign * np.radians(jstep)
            try:
                mover.joint_move(tuple(target), floor=deepest, seconds=max(0.4, np.radians(jstep) / 0.4))
            except Unsafe as e:
                print(f"\n    not moving: {e}")
        elif not joint_mode and k in MOVES:
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


CORNERS = (("a1", "White's left corner square"), ("h1", "White's right corner square"),
           ("a8", "Black's corner square on White's left side"), ("h8", "Black's corner square on White's right side"))
MAX_TILT = 5.0            # degrees: touch the squares with the gripper about straight down
CARRY_WANTED = 145.0      # a piece held 42 mm up then clears the 80 mm king by 20 mm


def carry_height(board, best=CARRY_WANTED, lowest_ok=90.0):
    """The highest fingertip height (up to `best`) at which the arm reaches every square."""
    h = best
    while h >= lowest_ok:
        if all(ik(board.square(s, h)) is not None for s in chess.SQUARES):
            return h
        h -= 1.0
    raise Unsafe("the arm can't reach every square even 9 cm above the board: is the board under the arm?")


def main():
    ap = argparse.ArgumentParser(description="Calibrate the board position")
    ap.add_argument("--bin-only", action="store_true",
                    help="keep the saved board corners and only set the bin for captured pieces again")
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
        ask("Clear the pieces off the board (leave the board in place). Keep a hand near the 12 V switch.\n"
            "Press Enter to park the arm and start... ")
        started = True
        if not follow(arm, moves):                # the same safe route as autochess.park
            sys.exit("The arm didn't finish going to its home pose.")
        mover.refresh()
        arm.gripper(GRIPPER_CLOSED)          # closed fingers make a pointer
        start = np.array([120.0, 0.0, H - 150.0])
        mover.go_to(start, floor=H - 100)

        if args.bin_only:
            b = Board.load()
            mover.go_to(b.square(chess.E4, b.travel), floor=b.floor(b.travel - 10))
        else:
            corners = {}
            for name, where in CORNERS:
                p = jog(mover, f"Touch the centre of {name} ({where}) with the fingertips, then Enter.", H + 20, H,
                        straight=True)
                if p is None:
                    return
                corners[name] = p
                lift(mover, p)
            b = Board(corners["a1"], corners["h1"], corners["a8"], drop=corners["a1"], h8=corners["h8"])
            keep_grip_settings(b)
            check_board(mover, b)
        p = jog(mover, "Move the fingertips 5-10 cm above the bin for captured pieces (where it lets go), then Enter.\n"
                "    Put the bin right next to the middle of one side of the board, about 20 cm from the point under the arm.",
                b.floor(-20), b.floor(0))
        if p is None:
            return
        b.drop = p
        b.save()
        print("Saved data/board.json.")
    except Unsafe as e:
        print(f"\nStopped: {e}")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if started:
            go_home(arm)
        arm.close()


def lift(mover, p, up=60.0):
    """After touching a corner, lift the fingertips: straight up if possible, otherwise with a joint
    move that only goes up. If neither works, stay put: the keys can lift it."""
    for go in (lambda: mover.line_to(p - [0, 0, up]), lambda: mover.go_to(p - [0, 0, up], floor=p[2])):
        try:
            go()
            return
        except Unsafe:
            pass
    print("    (couldn't lift by itself from here: raise it with the keys)")


def keep_grip_settings(b):
    """A new calibration keeps the grip settings tuned with try_move (grip heights, holding margin)."""
    try:
        old = Board.load()
    except (FileNotFoundError, KeyError, ValueError):
        return
    b.grip, b.held_margin, b.gripper_open = old.grip, old.held_margin, old.gripper_open


def check_board(mover, b):
    """After the four corners: report the squares, pick the carrying height, and check a middle square."""
    fs, rs = b.square_size()
    print(f"\nSquares: {fs:.1f} mm along the ranks, {rs:.1f} mm along the files.")
    b.travel = carry_height(b)
    print(f"Carrying height: {b.travel:.0f} mm above the board (the highest that reaches every square).")
    if b.travel < CARRY_WANTED:
        print(f"  That's below {CARRY_WANTED:.0f} mm: a carried king or queen only just clears the king. "
              f"Raising the arm on the frame by about {(CARRY_WANTED - b.travel) * 1.6:.0f} mm would fix it.")

    mover.go_to(b.square(chess.E5, 60), floor=b.floor(40))
    mover.line_to(b.square(chess.E5, 15))
    if not yes_no("Check: are the fingertips 15 mm above the centre of e5? [y/n] "):
        raise Unsafe("the e5 check failed: run the calibration again, with the gripper straight down at each corner")
    mover.line_to(b.square(chess.E5, 60))


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

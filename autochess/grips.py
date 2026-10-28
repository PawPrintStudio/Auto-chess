"""Set the grip heights from the pieces' heights, without moving the arm:

  python3 -m autochess.grips                  show the grip heights and what carrying them needs
  python3 -m autochess.grips --top 14         propose gripping each piece with the fingertips 14 mm below its top
  python3 -m autochess.grips --top 14 --save  ... and keep that in data/board.json

A held piece hangs below the fingertips by the grip height, and its bottom must stay above the
tallest piece plus a margin while it's carried, so the carrying height (set by the calibration) limits
how high up a piece can be gripped: taller grips than that are lowered to fit, and it says so.
"""
import argparse

import chess

from .geometry import CLEARANCE, PIECE_HEIGHT, TALLEST, Board
from .robot_arm import NAMES

ORDER = [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]


def plan_grips(board, below_top):
    """{piece: (grip height, wanted height)}: the fingertips `below_top` mm under each piece's top, but
    never higher than the carrying height allows (and never below the board)."""
    out = {}
    for p in ORDER:
        want = PIECE_HEIGHT[p] - below_top
        out[p] = (max(0.0, min(want, board.max_grip())), want)
    return out


def show(board, grips):
    print(f"Carrying height {board.travel:.0f} mm: a held piece may hang up to {board.max_grip():.0f} mm below the "
          f"fingertips (the {TALLEST:.0f} mm king plus {CLEARANCE:.0f} mm).\n")
    print("  piece    height   fingertips at   below the top")
    for p in ORDER:
        grip, want = grips[p]
        note = f"   (wanted {want:.0f}: lowered to fit the carrying height)" if grip < want - 0.5 else ""
        print(f"  {NAMES[p]:<7} {PIECE_HEIGHT[p]:5.0f} mm   {grip:6.0f} mm   {PIECE_HEIGHT[p] - grip:6.0f} mm{note}")


def main():
    ap = argparse.ArgumentParser(description="Grip heights from the pieces' heights")
    ap.add_argument("--top", type=float, metavar="MM", help="close the fingertips this many mm below each piece's top")
    ap.add_argument("--save", action="store_true", help="keep the proposed grip heights in data/board.json")
    args = ap.parse_args()
    board = Board.load()
    if args.top is None:
        show(board, {p: (board.grip[p], board.grip[p]) for p in ORDER})
        if board.travel < board.needed_carry():
            print(f"\nThe highest grip needs a carrying height of {board.needed_carry():.0f} mm, more than the {board.travel:.0f} mm "
                  f"the arm has: lower the grips or raise the arm.")
        return
    grips = plan_grips(board, args.top)
    show(board, grips)
    if not args.save:
        print("\nNot saved. Add --save to keep these, then check one move with: "
              "python3 -m autochess.try_move e2e4 --hover 30")
        return
    for p, (grip, _) in grips.items():
        board.grip[p] = grip
    board.save()
    print("\nSaved data/board.json.")


if __name__ == "__main__":
    main()

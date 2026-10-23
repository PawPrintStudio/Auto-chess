"""Play a few moves with the real arm, from the starting position, to test gripping:

  python3 -m autochess.try_move e2e4              one move
  python3 -m autochess.try_move e2e4 e7e5 g1f3    several, in order
  python3 -m autochess.try_move g1f3 --grip n=30  try the knight gripped 30 mm above the board
  ... --save                                      keep the --grip heights in data/board.json

Set up the pieces in the starting position first. Moves must be legal from there.
"""
import argparse
import sys

import chess

from .geometry import Board
from .motion import Unsafe
from .robot_arm import RealArm


def main():
    ap = argparse.ArgumentParser(description="Test moves with the real arm")
    ap.add_argument("moves", nargs="+", help="moves like e2e4, from the starting position")
    ap.add_argument("--grip", action="append", default=[], metavar="PIECE=MM",
                    help="grip height for a piece (p n b r q k), e.g. --grip p=24")
    ap.add_argument("--save", action="store_true", help="save the --grip heights")
    args = ap.parse_args()

    geo = Board.load()
    for g in args.grip:
        sym, mm = g.split("=")
        geo.grip[chess.PIECE_SYMBOLS.index(sym.lower())] = float(mm)
    board = chess.Board()
    moves = []
    for uci in args.moves:
        m = chess.Move.from_uci(uci)
        if m not in board.legal_moves:
            sys.exit(f"{uci} isn't legal after {' '.join(x.uci() for x in moves) or 'the start'}")
        moves.append(m)
        board.push(m)
    board = chess.Board()

    from .ros_arm import RosArm
    ros = RosArm()
    arm = RealArm(ros, geo)
    try:
        input("Pieces in the starting position, hands clear, a hand near the 12 V switch. Press Enter... ")
        arm.start()
        for m in moves:
            print(f"Playing {board.san(m)}")
            arm.play(board, m)
            board.push(m)
        if args.save and args.grip:
            geo.save()
            print("Saved the grip heights.")
    except (ValueError, Unsafe) as e:
        print(f"Stopped: {e}")
    finally:
        ros.close()


if __name__ == "__main__":
    main()

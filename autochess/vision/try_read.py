"""Test the camera reading moves, with no arm and no screen:  python3 -m autochess.vision.try_read

You play both sides by hand. Put the pieces in the starting position, press Enter (it learns the
colours and where the board is), then make a move, press Enter, and it says which move it saw.
If it can't tell, it says why; fix the board or take your hand away and press Enter again.
Type q instead of Enter to stop.
"""
import argparse

import chess

from .camera import Camera
from .eyes import CameraEyes, VisionError
from .tracking import CameraCal


def main():
    ap = argparse.ArgumentParser(description="Play both sides by hand and let the camera read the moves")
    ap.add_argument("--device", type=int, default=0)
    args = ap.parse_args()
    cal = CameraCal.load()
    cam = Camera(args.device)
    eyes = CameraEyes(cam, cal)
    board = chess.Board()
    try:
        input("Pieces in the starting position, nothing over the board. Press Enter... ")
        try:
            eyes.begin_game(board)
        except VisionError as e:
            print(f"Can't start: {e}")
            return
        print("Learned the board and the piece colours.")
        while not board.is_game_over():
            problems = eyes.begin_turn(board)
            if problems:
                print(f"  (the board doesn't look right at {', '.join(problems)})")
            while True:
                side = "White" if board.turn == chess.WHITE else "Black"
                if input(f"{side}: make a move, then press Enter (q to stop)... ").strip().lower() == "q":
                    return
                move = eyes.read_move(board, timeout=6.0)
                if move is not None:
                    print(f"  I saw {board.san(move)}")
                    board.push(move)
                    break
                print("  I couldn't read a move (see the line above). Fix the board or move your hand, then Enter.")
        print("Game over:", board.result())
    finally:
        cam.close()


if __name__ == "__main__":
    main()

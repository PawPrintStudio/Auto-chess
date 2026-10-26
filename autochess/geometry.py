"""Where the board is, in the arm's frame (from calibration), and how to hold each piece.

data/board.json is written by `python3 -m autochess.calibrate`. It holds the fingertip positions
(X, Y, Z in mm, Z = depth below the plate) at the centres of a1, h1 and a8 touching the board, and
the point above the bin for captured pieces. Every other square follows from those three, even if
the board isn't square to the arm or isn't quite level.
"""
import json
from pathlib import Path

import chess
import numpy as np

BOARD_FILE = Path(__file__).resolve().parent.parent / "data" / "board.json"

TRAVEL = 145.0          # fingertip height above the board while moving between squares
                        # (a piece held 42 mm up still clears the 80 mm king by 20 mm)
# Fingertip height above the board when gripping each piece (the fingers close above this).
# Tune with: python3 -m autochess.try_move
GRIP = {chess.PAWN: 22.0, chess.ROOK: 25.0, chess.KNIGHT: 28.0, chess.BISHOP: 32.0,
        chess.QUEEN: 38.0, chess.KING: 42.0}
GRIPPER_OPEN = 0.0      # partly open (about 40 mm between the fingers), so they miss the neighbours
GRIPPER_CLOSED = -0.01
GRIP_EFFORT = 60.0
EMPTY_GRIP = -0.008     # fingers closed past this: nothing between them (until start() measures it)
HELD_MARGIN = 0.001     # fingers stopping 1 mm short of an empty close: they're holding a piece
                        # (try_move --held-margin; smaller for pieces barely wider than the closed gripper)


class Board:
    def __init__(self, a1, h1, a8, drop, grip=None, travel=TRAVEL, gripper_open=GRIPPER_OPEN,
                 held_margin=HELD_MARGIN):
        self.a1, self.h1, self.a8 = (np.array(p, float) for p in (a1, h1, a8))
        self.drop = np.array(drop, float)
        self.grip = dict(GRIP)
        self.grip.update({chess.PIECE_SYMBOLS.index(k): float(v) for k, v in (grip or {}).items()})
        self.travel, self.gripper_open, self.held_margin = travel, gripper_open, held_margin

    def square(self, sq, height=0.0):
        """Fingertip position over the centre of square sq, height mm above the board."""
        f, r = chess.square_file(sq), chess.square_rank(sq)
        p = self.a1 + (self.h1 - self.a1) * f / 7 + (self.a8 - self.a1) * r / 7
        return p - [0.0, 0.0, height]

    def floor(self, height):
        """Depth below the plate that keeps everything at least `height` above the whole board."""
        corners = [self.square(s) for s in (chess.A1, chess.H1, chess.A8, chess.H8)]
        return min(c[2] for c in corners) - height

    def square_size(self):
        return float(np.linalg.norm(self.h1 - self.a1) / 7), float(np.linalg.norm(self.a8 - self.a1) / 7)

    def save(self, path=None):
        path = path or BOARD_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"a1": self.a1.tolist(), "h1": self.h1.tolist(), "a8": self.a8.tolist(),
                "drop": self.drop.tolist(), "travel": self.travel, "gripper_open": self.gripper_open,
                "held_margin": self.held_margin,
                "grip": {chess.PIECE_SYMBOLS[p]: h for p, h in self.grip.items()}}
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path=None):
        path = path or BOARD_FILE
        if not path.exists():
            raise FileNotFoundError("the board isn't calibrated yet: python3 -m autochess.calibrate")
        d = json.loads(path.read_text())
        return cls(d["a1"], d["h1"], d["a8"], d["drop"], d.get("grip"), d.get("travel", TRAVEL),
                   d.get("gripper_open", GRIPPER_OPEN), d.get("held_margin", HELD_MARGIN))

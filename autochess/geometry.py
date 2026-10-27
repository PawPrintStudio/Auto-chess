"""Where the board is, in the arm's frame (from calibration), and how to hold each piece.

data/board.json is written by `python3 -m autochess.calibrate`. It holds the fingertip positions
(X, Y, Z in mm, Z = depth below the plate) at the centres of a1, h1, a8 and h8 touching the board,
and the point above the bin for captured pieces. Every other square is blended from those four
corners, so the board needn't be square to the arm or level, and small errors in the arm's
measurements largely cancel out. (Older calibrations without h8 assume a parallelogram.)
"""
import json
from pathlib import Path

import chess
import numpy as np

BOARD_FILE = Path(__file__).resolve().parent.parent / "data" / "board.json"

TALLEST = 80.0          # the king, mm: nothing may come lower than this over the board, plus a margin
CLEARANCE = 15.0        # that margin
TRAVEL = 145.0          # fingertip height above the board while moving between squares
                        # (a piece held 42 mm up still clears the 80 mm king by 20 mm)
# Fingertip height above the board when gripping each piece (the fingers close above this).
# Tune with: python3 -m autochess.try_move
GRIP = {chess.PAWN: 22.0, chess.ROOK: 25.0, chess.KNIGHT: 28.0, chess.BISHOP: 32.0,
        chess.QUEEN: 38.0, chess.KING: 42.0}
GRIPPER_OPEN = 0.0      # partly open (about 40 mm between the fingers), so they miss the neighbours
GRIPPER_CLOSED = -0.01
GRIPPER_FULL_OPEN = 0.019
RELEASE = 0.008         # letting go: open this much (per finger) wider than where the fingers stopped on the piece
GRIP_EFFORT = 60.0      # how hard the gripper squeezes; each piece type can have its own (try_move --effort)
EMPTY_GRIP = -0.008     # fingers closed past this: nothing between them (until start() measures it)
HELD_MARGIN = 0.001     # fingers stopping 1 mm short of an empty close: they're holding a piece
                        # (try_move --held-margin; smaller for pieces barely wider than the closed gripper)


class Board:
    def __init__(self, a1, h1, a8, drop, grip=None, travel=TRAVEL, gripper_open=GRIPPER_OPEN,
                 held_margin=HELD_MARGIN, h8=None, effort=None):
        self.a1, self.h1, self.a8 = (np.array(p, float) for p in (a1, h1, a8))
        self.h8 = np.array(h8, float) if h8 is not None else self.h1 + self.a8 - self.a1
        self.drop = np.array(drop, float)
        self.grip = dict(GRIP)
        self.grip.update({chess.PIECE_SYMBOLS.index(k): float(v) for k, v in (grip or {}).items()})
        self.effort = {p: GRIP_EFFORT for p in self.grip}
        self.effort.update({chess.PIECE_SYMBOLS.index(k): float(v) for k, v in (effort or {}).items()})
        self.travel, self.gripper_open, self.held_margin = travel, gripper_open, held_margin

    def at(self, u, v):
        """Board surface point at board coordinates (u, v) in squares: 0 = centre of a1, 7 = centre of
        the h-file / 8th rank. Blended from the four calibrated corners."""
        a, b = u / 7, v / 7
        return (1 - a) * (1 - b) * self.a1 + a * (1 - b) * self.h1 + (1 - a) * b * self.a8 + a * b * self.h8

    def square(self, sq, height=0.0):
        """Fingertip position over the centre of square sq, height mm above the board."""
        return self.at(chess.square_file(sq), chess.square_rank(sq)) - [0.0, 0.0, height]

    def _uv(self, point):
        """Board coordinates (u, v) of the point on the board right under `point`."""
        files, ranks = (self.h1 - self.a1) / 7, (self.a8 - self.a1) / 7
        m = np.array([files[:2], ranks[:2]]).T
        target = np.asarray(point, float)[:2]
        uv = np.linalg.solve(m, target - self.a1[:2])
        for _ in range(3):                       # refine for the blend between the four corners
            uv = uv + np.linalg.solve(m, target - self.at(*uv)[:2])
        return uv

    def height_above(self, point):
        """How far point (X, Y, Z) is above the board surface right under it (the calibrated surface,
        extended past the edges), mm. Follows a board that isn't level."""
        return float(self.at(*self._uv(point))[2] - point[2])

    def over_board(self, point, margin=25.0):
        """True if point is above the squares, or within `margin` mm of their edge."""
        u, v = self._uv(point)
        m = margin / min(self.square_size())
        return -0.5 - m <= u <= 7.5 + m and -0.5 - m <= v <= 7.5 + m

    def floor(self, height):
        """Depth below the plate that keeps everything at least `height` above the whole board."""
        corners = [self.square(s) for s in (chess.A1, chess.H1, chess.A8, chess.H8)]
        return min(c[2] for c in corners) - height

    def square_size(self):
        return float(np.linalg.norm(self.h1 - self.a1) / 7), float(np.linalg.norm(self.a8 - self.a1) / 7)

    def save(self, path=None):
        path = path or BOARD_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"a1": self.a1.tolist(), "h1": self.h1.tolist(), "a8": self.a8.tolist(), "h8": self.h8.tolist(),
                "drop": self.drop.tolist(), "travel": self.travel, "gripper_open": self.gripper_open,
                "held_margin": self.held_margin,
                "grip": {chess.PIECE_SYMBOLS[p]: h for p, h in self.grip.items()},
                "effort": {chess.PIECE_SYMBOLS[p]: e for p, e in self.effort.items()}}
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path=None):
        path = path or BOARD_FILE
        if not path.exists():
            raise FileNotFoundError("the board isn't calibrated yet: python3 -m autochess.calibrate")
        d = json.loads(path.read_text())
        return cls(d["a1"], d["h1"], d["a8"], d["drop"], d.get("grip"), d.get("travel", TRAVEL),
                   d.get("gripper_open", GRIPPER_OPEN), d.get("held_margin", HELD_MARGIN), d.get("h8"), d.get("effort"))

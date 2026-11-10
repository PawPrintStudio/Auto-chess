"""Reading the position from a picture of the board, and working out which move was just made.

The board is first straightened into a flat 8x8 picture (using where the markers say it is). Each
square is summarised by the colour of its middle: wood, or one of the two piece colours. The
colours are learned from the starting position at the start of every game, so it works with any
pieces whose two sides differ in colour from each other and from the board.

To read a move, every legal move is tried: which one leaves the board looking the way the picture
shows? (Only legal moves are considered, so a bad reading of one square can't invent a move.)
A promotion is read as a queen: the camera can't tell which piece the pawn became.
"""
from dataclasses import dataclass

import chess
import cv2
import numpy as np

S = 64                                   # pixels per square in the straightened picture
CHANGE_SCALE = 20.0                      # colour difference (Lab) that counts as a square having changed
LAB_WEIGHTS = np.array([0.5, 1.0, 1.0])  # lighting mostly moves L: count it half

_yy, _xx = np.mgrid[0:S, 0:S]
_DISC = (_xx - (S - 1) / 2) ** 2 + (_yy - (S - 1) / 2) ** 2 <= (0.3 * S) ** 2    # the middle of a square


def rectify(frame, b2p):
    """The board as a flat picture: rank 8 at the top, a-file on the left, S pixels a square."""
    T = np.array([[S, 0, 0.5 * S], [0, -S, 7.5 * S], [0, 0, 1.0]])
    return cv2.warpPerspective(frame, T @ np.linalg.inv(b2p), (8 * S, 8 * S), flags=cv2.INTER_AREA)


def square_features(rect):
    """(64, 3) Lab colour of the middle of every square, indexed like python-chess squares."""
    lab = cv2.cvtColor(rect.astype(np.float32) / 255.0, cv2.COLOR_BGR2Lab)
    out = np.zeros((64, 3))
    for sq in chess.SQUARES:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        patch = lab[(7 - r) * S:(8 - r) * S, f * S:(f + 1) * S][_DISC]
        out[sq] = np.median(patch, axis=0)
    return out


def expected_labels(board):
    """64 labels for a position: 0 empty, 1 a white piece, 2 a black piece."""
    out = np.zeros(64, int)
    for sq, piece in board.piece_map().items():
        out[sq] = 1 if piece.color == chess.WHITE else 2
    return out


def _dark(sq):
    return (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 0


class OccupancyModel:
    """The colours of dark wood, light wood, White's pieces and Black's pieces, learned from a picture
    of the starting position."""

    def __init__(self, wood_dark, wood_light, white, black):
        self.wood = {True: np.asarray(wood_dark, float), False: np.asarray(wood_light, float)}
        self.pieces = {1: np.asarray(white, float), 2: np.asarray(black, float)}

    @classmethod
    def learn(cls, feats):
        labels = expected_labels(chess.Board())
        wood = {d: feats[[s for s in chess.SQUARES if labels[s] == 0 and _dark(s) == d]].mean(axis=0)
                for d in (True, False)}
        return cls(wood[True], wood[False], feats[labels == 1].mean(axis=0), feats[labels == 2].mean(axis=0))

    def classify(self, feats):
        """64 labels (0 empty, 1 white piece, 2 black piece) for the colours seen."""
        out = np.zeros(64, int)
        for sq in chess.SQUARES:
            options = [(np.linalg.norm((feats[sq] - self.wood[_dark(sq)]) * LAB_WEIGHTS), 0),
                       (np.linalg.norm((feats[sq] - self.pieces[1]) * LAB_WEIGHTS), 1),
                       (np.linalg.norm((feats[sq] - self.pieces[2]) * LAB_WEIGHTS), 2)]
            out[sq] = min(options)[1]
        return out


@dataclass
class Reading:
    move: chess.Move = None
    agree: int = 0              # squares (of 64) that match the position after that move
    margin: float = 0.0         # how much better it is than the next best
    why: str = ""               # when there's no move: why not


def interpret(board, feats, before, model, min_agree=61, min_margin=0.5):
    """Which legal move turns `board` into what the picture (feats) shows? `before` is the picture's
    features from before the move: squares that changed colour break ties between moves that look alike."""
    obs = model.classify(feats)
    delta = feats - before
    delta = delta - np.median(delta, axis=0)               # a change of lighting moves every square alike
    change = np.clip(np.linalg.norm(delta * LAB_WEIGHTS, axis=1) / CHANGE_SCALE, 0.0, 1.0)
    now = expected_labels(board)
    unchanged = int((now == obs).sum())
    scored = []
    for m in board.legal_moves:
        if m.promotion and m.promotion != chess.QUEEN:      # the picture can't tell which piece: queen
            continue
        after = board.copy(stack=False)
        after.push(m)
        exp = expected_labels(after)
        agree = int((exp == obs).sum())
        moved = exp != now
        scored.append((agree + 0.05 * (change[moved].sum() - change[~moved].sum()), agree, m))
    if not scored:
        return Reading(why="there are no legal moves")
    scored.sort(key=lambda t: t[0], reverse=True)
    best = scored[0]
    margin = best[0] - scored[1][0] if len(scored) > 1 else 99.0
    bad = [chess.square_name(s) for s in np.nonzero(expected_labels(_after(board, best[2])) != obs)[0]][:6]
    if best[1] < min_agree:
        return Reading(None, best[1], margin, f"the picture doesn't match any move (differs at {', '.join(bad)}): "
                                              f"a hand or something else in the way?")
    if best[1] <= unchanged:
        return Reading(None, best[1], margin, "no move seen: the pieces look as they did")
    if margin < min_margin:
        return Reading(None, best[1], margin, f"can't tell {board.san(best[2])} from {board.san(scored[1][2])}")
    return Reading(best[2], best[1], margin)


def _after(board, move):
    b = board.copy(stack=False)
    b.push(move)
    return b

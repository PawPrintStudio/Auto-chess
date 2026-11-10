"""Draws synthetic camera pictures of a chess board with four markers, to test the vision code.

World coordinates are millimetres with the camera looking at the origin; the arm's frame is taken to
be the same, so the arm-frame position of a square is its world position. A board can be turned and
shifted (its markers move with it); the camera never moves.
"""
import chess
import cv2
import numpy as np

from autochess.vision import markers

SQ = 40.0                   # square size, mm
PPM = 2                     # texture pixels per mm
WORLD = 700.0               # side of the drawn world, mm
TEX = int(WORLD * PPM)
FRAME = (1920, 1080)
# world mm -> frame pixels: about 2.6 px/mm with a little tilt and perspective
H_CAM = np.array([[2.6, 0.04, 960.0], [-0.03, -2.5, 540.0], [1.5e-5, -2e-5, 1.0]])
TEX2WORLD = np.array([[1 / PPM, 0, -WORLD / 2], [0, 1 / PPM, -WORLD / 2], [0, 0, 1.0]])

TABLE, DARK, LIGHT = (140, 120, 40), (45, 85, 130), (110, 165, 205)          # BGR
PINK, GREEN, SKIN = (200, 165, 245), (75, 165, 135), (140, 170, 220)
RADII = {chess.PAWN: 11, chess.KNIGHT: 12, chess.BISHOP: 12, chess.ROOK: 12, chess.QUEEN: 14, chess.KING: 14.5}
MARKER_CENTRES = {0: (-35.0, -35.0), 1: (315.0, -35.0), 2: (-35.0, 315.0), 3: (315.0, 315.0)}   # board-local mm
MARKER_MM = 18.0
CORNER_LOCAL = {"a1": (0.0, 0.0), "h1": (280.0, 0.0), "a8": (0.0, 280.0), "h8": (280.0, 280.0)}


def local_to_world(pts, deg=0.0, shift=(0.0, 0.0)):
    """Board-local mm (a1 centre = 0, files along x, ranks along y) -> world mm."""
    pts = np.asarray(pts, float).reshape(-1, 2) - [140.0, 140.0]
    a = np.radians(deg)
    R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    return pts @ R.T + np.asarray(shift, float)


def world_to_frame(pts):
    pts = np.asarray(pts, float).reshape(-1, 2)
    v = np.c_[pts, np.ones(len(pts))] @ H_CAM.T
    return v[:, :2] / v[:, 2:3]


def _tex(pts):
    return ((np.asarray(pts, float) + WORLD / 2) * PPM)


def render(board=None, deg=0.0, shift=(0.0, 0.0), brightness=1.0, noise=2.0, seed=0, hand=None,
           marker_ids=markers.BOARD_IDS):
    """A picture of `board` (empty if None) with the given pose. hand=(x, y) pixel puts a hand there."""
    rng = np.random.default_rng(seed)
    tex = np.full((TEX, TEX, 3), TABLE, np.uint8)
    for sq in chess.SQUARES:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        quad = [(f * SQ - 20, r * SQ - 20), (f * SQ + 20, r * SQ - 20), (f * SQ + 20, r * SQ + 20),
                (f * SQ - 20, r * SQ + 20)]
        base = np.array(DARK if (f + r) % 2 == 0 else LIGHT, int) + rng.integers(-5, 6, 3)
        cv2.fillConvexPoly(tex, _tex(local_to_world(quad, deg, shift)).astype(np.int32), tuple(int(c) for c in base))
    if board is not None:
        for sq, piece in board.piece_map().items():
            c = _tex(local_to_world([(chess.square_file(sq) * SQ, chess.square_rank(sq) * SQ)], deg, shift))[0]
            cv2.circle(tex, (int(c[0]), int(c[1])), int(RADII[piece.piece_type] * PPM),
                       PINK if piece.color == chess.WHITE else GREEN, -1)
    side = int(MARKER_MM * PPM)                         # a multiple of 6: crisp cells
    side -= side % 6
    pad = side // 6
    for mid in marker_ids:
        tile = np.full((side + 2 * pad, side + 2 * pad), 255, np.uint8)
        tile[pad:pad + side, pad:pad + side] = markers.marker_image(mid, side)
        tile = cv2.cvtColor(tile, cv2.COLOR_GRAY2BGR)
        cx, cy = MARKER_CENTRES[mid]
        h = (side + 2 * pad) / PPM / 2
        # the world's y axis points up but a picture's points down: the tile's top-left goes to the +y side
        quad = [(cx - h, cy + h), (cx + h, cy + h), (cx + h, cy - h), (cx - h, cy - h)]
        src = np.float32([[0, 0], [tile.shape[1], 0], [tile.shape[1], tile.shape[0]], [0, tile.shape[0]]])
        M = cv2.getPerspectiveTransform(src, _tex(local_to_world(quad, deg, shift)).astype(np.float32))
        cv2.warpPerspective(tile, M, (TEX, TEX), dst=tex, flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_TRANSPARENT)
    frame = cv2.warpPerspective(tex, H_CAM @ TEX2WORLD, FRAME, flags=cv2.INTER_LINEAR, borderValue=TABLE)
    if hand is not None:
        cv2.ellipse(frame, hand, (200, 110), 20, 0, 360, SKIN, -1)
    out = frame.astype(np.float32) * brightness + rng.normal(0, noise, frame.shape)
    return np.clip(out, 0, 255).astype(np.uint8)


def truth_corners(deg=0.0, shift=(0.0, 0.0)):
    """Where a1, h1, a8, h8 really are in the world (= the arm's frame)."""
    return local_to_world(list(CORNER_LOCAL.values()), deg, shift)

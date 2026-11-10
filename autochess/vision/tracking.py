"""Finding the board in the camera picture, and from that where it is in the arm's frame.

How it works. The camera is clamped to the same frame as the arm, so the camera and the arm never
move relative to each other; only the board can move. Once, at calibration time, we record
  * where the four markers are in the picture, and
  * where the centres of a1, h1, a8 and h8 are in the picture (four clicks),
and, since the arm calibration (autochess.calibrate) already knows where those squares are in the
arm's frame, that fixes how picture positions turn into arm positions on the board's plane.
Later, whenever the markers are seen, the way they have moved in the picture says how the board
moved: every square's picture position follows, and so does its arm position. The board can be
nudged, turned or put back differently, and the arm still finds every square, without anyone
calibrating again.

Assumes the board stays on the same flat surface (its height doesn't change) and the camera isn't
moved. If either happens, redo the camera calibration.
"""
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from . import markers

CAMERA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "camera.json"
CORNER_NAMES = ("a1", "h1", "a8", "h8")
CORNER_UV = {"a1": (0.0, 0.0), "h1": (7.0, 0.0), "a8": (0.0, 7.0), "h8": (7.0, 7.0)}
MAX_SHIFT_MM = 30.0       # a bigger move than this isn't applied without asking: something is probably wrong
MAX_TURN_DEG = 6.0


class NotTracked(Exception):
    """The markers can't be used to find the board right now."""


def apply_h(H, pts):
    """Apply a 3x3 homography to (N, 2) points."""
    pts = np.asarray(pts, float).reshape(-1, 2)
    v = np.c_[pts, np.ones(len(pts))] @ np.asarray(H, float).T
    return v[:, :2] / v[:, 2:3]


@dataclass
class CameraCal:
    """What was true when the camera was calibrated."""
    markers: dict          # marker id -> (4, 2) corner pixels
    squares_px: dict       # "a1" / "h1" / "a8" / "h8" -> (x, y) pixel of that square's centre
    saved: str = ""

    def board_to_pixel(self):
        """3x3 matrix taking board coordinates (file, rank; 0 = the a1 / a-file centre) to pixels."""
        src = np.float32([CORNER_UV[n] for n in CORNER_NAMES])
        dst = np.float32([self.squares_px[n] for n in CORNER_NAMES])
        return cv2.getPerspectiveTransform(src, dst).astype(float)

    def save(self, path=None):
        path = path or CAMERA_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():                                   # never overwrite a calibration without keeping it
            backups = path.parent / "backups"
            backups.mkdir(exist_ok=True)
            shutil.copy2(path, backups / f"camera-{time.strftime('%Y%m%d-%H%M%S')}.json")
        path.write_text(json.dumps({
            "markers": {str(k): np.asarray(v, float).tolist() for k, v in self.markers.items()},
            "squares_px": {k: [float(x) for x in v] for k, v in self.squares_px.items()},
            "saved": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=2))

    @classmethod
    def load(cls, path=None):
        path = path or CAMERA_FILE
        if not path.exists():
            raise FileNotFoundError("the camera isn't calibrated yet: python3 -m autochess.vision.calibrate_camera")
        d = json.loads(path.read_text())
        return cls({int(k): np.array(v, float) for k, v in d["markers"].items()},
                   {k: np.array(v, float) for k, v in d["squares_px"].items()}, d.get("saved", ""))


class ArmMap:
    """Picture pixels on the board's plane -> arm-frame X, Y, Z (depth below the mount plate), fixed once
    the camera and the arm are calibrated against the same board."""

    def __init__(self, b2p_ref, geo):
        uv = [(f, r) for r in range(8) for f in range(8)]
        xyz = np.array([geo.at(f, r) for f, r in uv], float)
        px = apply_h(b2p_ref, uv)
        self.F, _ = cv2.findHomography(px, xyz[:, :2], 0)
        A = np.c_[xyz[:, 0], xyz[:, 1], np.ones(len(xyz))]
        self.plane = np.linalg.lstsq(A, xyz[:, 2], rcond=None)[0]     # z = a x + b y + c

    def to_arm(self, px):
        xy = apply_h(self.F, px)
        z = xy[:, 0] * self.plane[0] + xy[:, 1] * self.plane[1] + self.plane[2]
        return np.c_[xy, z]


@dataclass
class BoardView:
    """Where the board is in the picture right now."""
    b2p: np.ndarray        # board coordinates -> pixels
    ids: list              # the markers that were used
    rms: float             # how far, on average, the markers are from where the fit puts them (pixels)


@dataclass
class Report:
    applied: bool
    shift_mm: float
    turn_deg: float
    ids: list
    message: str


def rigid_shift(ref_xy, new_xy):
    """(translation mm, rotation degrees) that best carries the reference corners onto the new ones."""
    a, b = np.asarray(ref_xy, float), np.asarray(new_xy, float)
    ca, cb = a.mean(axis=0), b.mean(axis=0)
    u, _, vt = np.linalg.svd((a - ca).T @ (b - cb))
    R = vt.T @ u.T
    return float(np.linalg.norm(cb - ca)), float(np.degrees(np.arctan2(R[1, 0], R[0, 0])))


class BoardTracker:
    def __init__(self, cal, geo=None):
        self.cal, self.geo = cal, geo
        self.b2p_ref = cal.board_to_pixel()
        self.armmap = ArmMap(self.b2p_ref, geo) if geo is not None else None
        self.ref_corners = ({n: np.array(geo.at(*uv), float) for n, uv in CORNER_UV.items()}
                            if geo is not None else None)

    def view(self, frame):
        """Where the board is in this picture, from the markers. Raises NotTracked if it can't tell."""
        found = markers.detect(frame)
        ids = sorted(set(found) & set(self.cal.markers))
        if len(ids) < 2 or (len(ids) == 2 and set(ids) not in ({0, 3}, {1, 2})):
            raise NotTracked(f"I can see markers {ids or 'none'}: I need at least three of the four, or two on "
                             f"opposite corners (is something in the way, or a marker loose?)")
        src = np.vstack([self.cal.markers[i] for i in ids])
        dst = np.vstack([found[i] for i in ids])
        if len(src) > 8:
            H, _ = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
        else:
            H, _ = cv2.findHomography(src, dst, 0)
        if H is None:
            raise NotTracked("the markers don't fit together (one may be misread)")
        rms = float(np.sqrt(np.mean(np.sum((apply_h(H, src) - dst) ** 2, axis=1))))
        return BoardView(H @ self.b2p_ref, ids, rms)

    def new_corners(self, view):
        """{"a1": X, Y, Z, ...} in the arm's frame for the board as seen now."""
        px = apply_h(view.b2p, [CORNER_UV[n] for n in CORNER_NAMES])
        return dict(zip(CORNER_NAMES, self.armmap.to_arm(px)))

    def update_geo(self, view, force=False, max_shift=MAX_SHIFT_MM, max_turn=MAX_TURN_DEG):
        """Move the arm's board geometry (in place) to where the markers say the board is now."""
        if self.armmap is None:
            raise RuntimeError("tracking needs the arm's board calibration (data/board.json)")
        corners = self.new_corners(view)
        shift, turn = rigid_shift([self.ref_corners[n][:2] for n in CORNER_NAMES],
                                  [corners[n][:2] for n in CORNER_NAMES])
        text = f"the board is {shift:.1f} mm and {turn:+.1f} degrees from where it was calibrated"
        if (shift > max_shift or abs(turn) > max_turn) and not force:
            return Report(False, shift, turn, view.ids, text + ": more than I'll adjust for by myself")
        for name in CORNER_NAMES:
            getattr(self.geo, name)[:] = corners[name]
        return Report(True, shift, turn, view.ids, text)

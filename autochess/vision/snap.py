"""Take a picture with the camera and check what it sees:  python3 -m autochess.vision.snap

Saves data/snap.jpg with the markers outlined and, if the camera is calibrated, the board's squares
drawn on, and prints which markers it found. Send me that picture when something doesn't look right.
"""
import argparse
from pathlib import Path

import cv2
import numpy as np

from . import markers
from .camera import Camera
from .tracking import CORNER_UV, BoardTracker, CameraCal, NotTracked, apply_h

DEFAULT = Path(__file__).resolve().parent.parent.parent / "data" / "snap.jpg"


def annotate(frame, cal=None):
    """The picture with the markers outlined and (if calibrated) the board's grid and square names."""
    out = frame.copy()
    found = markers.detect(frame)
    for mid, pts in found.items():
        cv2.polylines(out, [pts.astype(np.int32)], True, (0, 255, 0), 2)
        cv2.putText(out, str(mid), tuple(pts[0].astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
    if cal is not None:
        try:
            view = BoardTracker(cal).view(frame)
        except NotTracked as e:
            cv2.putText(out, str(e)[:90], (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            return out, found
        for k in range(9):                        # the grid lines, at the edges of the squares
            for a, b in (((-0.5, k - 0.5), (7.5, k - 0.5)), ((k - 0.5, -0.5), (k - 0.5, 7.5))):
                p, q = apply_h(view.b2p, [a, b]).astype(int)
                cv2.line(out, tuple(p), tuple(q), (255, 0, 255), 1)
        for name, uv in CORNER_UV.items():
            p = apply_h(view.b2p, [uv])[0].astype(int)
            cv2.putText(out, name, (p[0] - 12, p[1] + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    return out, found


def main():
    ap = argparse.ArgumentParser(description="Take a picture and show what the camera sees")
    ap.add_argument("--device", type=int, default=0)
    ap.add_argument("--image", type=Path, help="use this picture instead of the camera")
    ap.add_argument("--out", type=Path, default=DEFAULT)
    args = ap.parse_args()
    if args.image:
        frame = cv2.imread(str(args.image))
    else:
        cam = Camera(args.device)
        frame = cam.still_frame()
        cam.close()
    try:
        cal = CameraCal.load()
    except FileNotFoundError:
        cal = None
    out, found = annotate(frame, cal)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.out), out)
    h, w = frame.shape[:2]
    print(f"Picture {w}x{h}. Markers found: {sorted(found) or 'none'}"
          + ("" if len(found) == 4 else "   <- all four (0, 1, 2, 3) need to be visible and flat"))
    for mid, pts in sorted(found.items()):
        side = np.mean([np.linalg.norm(pts[i] - pts[(i + 1) % 4]) for i in range(4)])
        print(f"  marker {mid}: centre ({pts[:, 0].mean():.0f}, {pts[:, 1].mean():.0f}), {side:.0f} px wide"
              + ("   (small: bring the camera closer or print them bigger)" if side < 25 else ""))
    print(f"Saved {args.out}" + ("" if cal else "   (the camera isn't calibrated yet, so no grid is drawn)"))


if __name__ == "__main__":
    main()

"""Teach the camera where the board is:  python3 -m autochess.vision.calibrate_camera

Do this once after the markers are taped on and the camera is fixed in place, with the board where
it will normally sit (and after the arm calibration, autochess.calibrate, which this builds on).
Pieces on or off the board doesn't matter, but nothing may hide a marker.

It takes a picture, finds the four markers, and shows the picture: click the CENTRE of the a1 square,
then h1, then a8, then h8 (the same corners as the arm calibration: a1 = White's left corner square,
h1 = White's right corner, a8 = Black's corner on White's left, h8 = the opposite one).
  u  undo the last click        Enter  accept (after four)        Esc  quit without saving
No screen on this computer? Give the four clicks as pixel positions:  --points "x,y x,y x,y x,y"
(take them from data/snap.jpg). Redo this if the camera is moved. If only the board moves, nothing
needs redoing: the markers show where it went.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from . import markers
from .camera import Camera
from .tracking import CORNER_NAMES, CameraCal

WINDOW = "click the CENTRE of a1, then h1, a8, h8   (u = undo, Enter = accept, Esc = quit)"


def click_points(frame, found):
    """Show the picture; return four (x, y) clicks in picture pixels, or None if the user quit."""
    h, w = frame.shape[:2]
    scale = min(1.0, 1400 / w, 800 / h)
    shown = cv2.resize(frame, (int(w * scale), int(h * scale)))
    for pts in found.values():
        cv2.polylines(shown, [(pts * scale).astype(np.int32)], True, (0, 255, 0), 2)
    clicks = []

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(clicks) < 4:
            clicks.append((x / scale, y / scale))

    cv2.namedWindow(WINDOW)
    cv2.setMouseCallback(WINDOW, on_mouse)
    while True:
        view = shown.copy()
        for name, (x, y) in zip(CORNER_NAMES, clicks):
            cv2.circle(view, (int(x * scale), int(y * scale)), 6, (0, 0, 255), 2)
            cv2.putText(view, name, (int(x * scale) + 8, int(y * scale) - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (0, 0, 255), 2)
        todo = CORNER_NAMES[len(clicks)] if len(clicks) < 4 else "Enter to accept"
        cv2.putText(view, f"next: {todo}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)
        cv2.imshow(WINDOW, view)
        key = cv2.waitKey(50) & 0xFF
        if key in (27, ord("q")):
            cv2.destroyAllWindows()
            return None
        if key == ord("u") and clicks:
            clicks.pop()
        if key in (10, 13) and len(clicks) == 4:
            cv2.destroyAllWindows()
            return clicks


def main():
    ap = argparse.ArgumentParser(description="Calibrate the camera against the board")
    ap.add_argument("--device", type=int, default=0)
    ap.add_argument("--image", type=Path, help="use this picture instead of the camera")
    ap.add_argument("--points", help='the four clicks as pixels: "x,y x,y x,y x,y" (a1 h1 a8 h8)')
    args = ap.parse_args()

    if args.image:
        frame = cv2.imread(str(args.image))
    else:
        cam = Camera(args.device)
        frame = cam.still_frame()
        cam.close()
    found = markers.detect(frame)
    if sorted(found) != [0, 1, 2, 3]:
        sys.exit(f"I found markers {sorted(found) or 'none'}: all four (0, 1, 2, 3) must be visible, flat and in "
                 f"focus. Run python3 -m autochess.vision.snap to see what the camera sees.")
    if args.points:
        clicks = [tuple(float(v) for v in p.split(",")) for p in args.points.split()]
        if len(clicks) != 4:
            sys.exit("--points needs four x,y pairs: a1 h1 a8 h8")
    else:
        try:
            clicks = click_points(frame, found)
        except cv2.error as e:
            sys.exit(f"can't open a window here ({e}). Use --points \"x,y x,y x,y x,y\" instead.")
        if clicks is None:
            sys.exit("Not saved.")
    cal = CameraCal(found, dict(zip(CORNER_NAMES, [np.array(c, float) for c in clicks])))
    cal.save()
    print("Saved data/camera.json. Check it: python3 -m autochess.vision.snap (the grid should sit on the squares).")


if __name__ == "__main__":
    main()

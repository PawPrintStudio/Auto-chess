"""The four printed markers (ArUco) on the board's corners, and how to find them in a picture.

They only have to stay put relative to the board: the camera compares where they are now with where
they were when the camera was calibrated, so their exact position and printed size don't matter.
Marker 0 goes near the a1 corner, 1 near h1, 2 near a8, 3 near h8.
"""
import cv2
import numpy as np

BOARD_IDS = (0, 1, 2, 3)
LABELS = {0: "a1 corner", 1: "h1 corner", 2: "a8 corner", 3: "h8 corner"}


def _dictionary():
    return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def marker_image(marker_id, side_px):
    """The marker as a picture (black border included), side_px wide."""
    if hasattr(cv2.aruco, "generateImageMarker"):
        return cv2.aruco.generateImageMarker(_dictionary(), marker_id, side_px)
    img = np.zeros((side_px, side_px), np.uint8)
    cv2.aruco.drawMarker(_dictionary(), marker_id, side_px, img, 1)
    return img


def detect(frame):
    """{marker id: (4, 2) corner pixels} for the board markers seen in the picture."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    if hasattr(cv2.aruco, "ArucoDetector"):
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        corners, ids, _ = cv2.aruco.ArucoDetector(_dictionary(), params).detectMarkers(gray)
    else:
        params = cv2.aruco.DetectorParameters_create()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        corners, ids, _ = cv2.aruco.detectMarkers(gray, _dictionary(), parameters=params)
    found = {}
    if ids is not None:
        for c, i in zip(corners, ids.flatten()):
            if int(i) in BOARD_IDS:
                found[int(i)] = c.reshape(4, 2).astype(np.float64)
    return found


def printable_sheet(size_mm=15.0, dpi=300):
    """A US Letter page with the four markers twice (a spare set), each with a white margin."""
    page = np.full((int(11 * dpi), int(8.5 * dpi)), 255, np.uint8)
    cell = max(1, round(size_mm / 25.4 * dpi / 6))
    side, margin = cell * 6, cell
    cv2.putText(page, "Auto-chess board markers: print at 100% (no 'fit to page'), cut out each square.",
                (int(0.6 * dpi), int(0.8 * dpi)), cv2.FONT_HERSHEY_SIMPLEX, dpi / 150, 0, max(2, dpi // 150))
    cv2.putText(page, f"Marker size {size_mm:g} mm. Tape one flat on the board near each corner, all four never "
                      f"moving relative to the board.", (int(0.6 * dpi), int(1.2 * dpi)),
                cv2.FONT_HERSHEY_SIMPLEX, dpi / 220, 0, max(1, dpi // 220))
    for row in range(2):
        y = int((1.8 + row * 2.6) * dpi)
        for k, mid in enumerate(BOARD_IDS):
            x = int((0.6 + k * 1.9) * dpi)
            tile = np.full((side + 2 * margin, side + 2 * margin), 255, np.uint8)
            tile[margin:margin + side, margin:margin + side] = marker_image(mid, side)
            page[y:y + tile.shape[0], x:x + tile.shape[1]] = tile
            cv2.rectangle(page, (x, y), (x + tile.shape[1] - 1, y + tile.shape[0] - 1), 170, 1)
            cv2.putText(page, f"{mid}: {LABELS[mid]}", (x, y + tile.shape[0] + int(0.3 * dpi)),
                        cv2.FONT_HERSHEY_SIMPLEX, dpi / 330, 0, max(1, dpi // 300))
    return page

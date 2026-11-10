"""Make the page of board markers to print:  python3 -m autochess.vision.make_markers [--size-mm 15]

Writes docs/markers.png (US Letter, 300 dpi). Print it at 100% (no "fit to page"), cut the markers out
(keep the white margin around each), and tape one flat on the board near each corner:
  0 near a1, 1 near h1, 2 near a8, 3 near h8.
They can be on the board's border, or on little cards fixed to its edge. What matters is that all four
stay put relative to the board, and stay flat and clean.
"""
import argparse
from pathlib import Path

import cv2

from .markers import printable_sheet

DEFAULT = Path(__file__).resolve().parent.parent.parent / "docs" / "markers.png"


def main():
    ap = argparse.ArgumentParser(description="Make the printable page of board markers")
    ap.add_argument("--size-mm", type=float, default=15.0, help="marker size on paper, mm (default 15)")
    ap.add_argument("--out", type=Path, default=DEFAULT)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.out), printable_sheet(args.size_mm))
    print(f"Wrote {args.out}: print it at 100% and tape one marker near each corner of the board.")


if __name__ == "__main__":
    main()

"""Make the page of board markers to print:  python3 -m autochess.vision.make_markers [--size-mm 15]

Writes docs/markers.pdf (and markers.png): US Letter, 300 dpi. Print it at 100% (no "fit to page"), cut the markers out
(keep the white margin around each), and tape one flat on the board near each corner:
  0 near a1, 1 near h1, 2 near a8, 3 near h8.
They can be on the board's border, or on little cards fixed to its edge. What matters is that all four
stay put relative to the board, and stay flat and clean.
"""
import argparse
import zlib
from pathlib import Path

import cv2

from .markers import printable_sheet

DEFAULT = Path(__file__).resolve().parent.parent.parent / "docs" / "markers.png"


def write_pdf(path, gray, width_in=8.5, height_in=11.0):
    """A one-page PDF of a grey-scale picture filling the page (US Letter by default), so printing it at
    100% gives the markers their real size. Written by hand: no extra library needed."""
    h, w = gray.shape
    page_w, page_h = int(width_in * 72), int(height_in * 72)
    data = zlib.compress(gray.tobytes(), 9)
    content = f"q {page_w} 0 0 {page_h} 0 0 cm /Im0 Do Q".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w} {page_h}] "
            f"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>".encode(),
            f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceGray "
            f"/BitsPerComponent 8 /Filter /FlateDecode /Length {len(data)} >>\nstream\n".encode() + data
            + b"\nendstream",
            f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    Path(path).write_bytes(bytes(out))


def main():
    ap = argparse.ArgumentParser(description="Make the printable page of board markers")
    ap.add_argument("--size-mm", type=float, default=15.0, help="marker size on paper, mm (default 15)")
    ap.add_argument("--out", type=Path, default=DEFAULT)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet = printable_sheet(args.size_mm)
    cv2.imwrite(str(args.out), sheet)
    pdf = args.out.with_suffix(".pdf")
    write_pdf(pdf, sheet)
    print(f"Wrote {pdf} (and {args.out.name}): print the PDF at 100% (Actual size, not 'Fit') and tape one "
          f"marker near each corner of the board.")


if __name__ == "__main__":
    main()

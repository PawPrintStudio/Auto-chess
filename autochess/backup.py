"""Keep copies of the board calibration (data/board.json):

  python3 -m autochess.backup                  save a copy now, and show what it holds
  python3 -m autochess.backup --label tuned    the same, with a word added to the file name
  python3 -m autochess.backup --list           the saved copies, newest first
  python3 -m autochess.backup --restore latest put a saved copy back (the current one is copied first)
  python3 -m autochess.backup --restore board-20261028-101500-tuned.json

Every calibration, every `--raised` shift and every `try_move --save` also copies the previous
board.json into data/backups/ by itself, so an overwrite can always be undone. The folder is
ignored by git: it belongs to this robot. To keep a copy somewhere else too, copy data/backups/ to
a USB stick or another computer (see the README).
"""
import argparse
import shutil
import sys
import time

import chess

from .geometry import BOARD_FILE, Board, backup, backup_dir, list_backups


def describe(path):
    """A few lines saying what a saved calibration holds."""
    b = Board.load(path)
    fs, rs = b.square_size()
    grips = ", ".join(f"{chess.piece_symbol(p)} {h:g}" for p, h in sorted(b.grip.items()))
    saved = time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))
    return (f"  saved {saved}\n  squares {fs:.1f} x {rs:.1f} mm, carrying height {b.travel:.0f} mm\n"
            f"  grip heights (mm above the board): {grips}\n"
            f"  holding margin {b.held_margin * 1000:.1f} mm, pad offset {b.pad_offset:g} mm")


def main():
    ap = argparse.ArgumentParser(description="Back up and restore the board calibration")
    ap.add_argument("--label", default="manual", help="a word added to the copy's file name")
    ap.add_argument("--list", action="store_true", help="list the saved copies")
    ap.add_argument("--restore", metavar="NAME", help="put a saved copy back: a file name, or 'latest'")
    args = ap.parse_args()

    if args.list:
        copies = list_backups()
        if not copies:
            print(f"No copies yet in {backup_dir()}")
        for c in copies:
            print(c.name)
        return
    if args.restore:
        copies = list_backups()
        names = {c.name: c for c in copies}
        pick = copies[0] if args.restore == "latest" and copies else names.get(args.restore.split("/")[-1])
        if pick is None:
            sys.exit(f"No saved copy called {args.restore}. See: python3 -m autochess.backup --list")
        backup(label="before-restore")
        shutil.copy2(pick, BOARD_FILE)
        print(f"Restored {pick.name}:\n{describe(BOARD_FILE)}")
        return
    if not BOARD_FILE.exists():
        sys.exit(f"Nothing to back up: {BOARD_FILE} doesn't exist (calibrate first).")
    copy = backup(label=args.label)
    print(f"Saved {copy}\n{describe(copy)}")


if __name__ == "__main__":
    main()

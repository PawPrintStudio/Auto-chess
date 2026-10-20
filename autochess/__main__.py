"""Start Auto-chess:  python3 -m autochess [--pretend] [--fullscreen]"""
import argparse
import tkinter as tk

from .engine import Engine
from .gui import App
from .pretend import ClickEyes, PretendArm


def main():
    ap = argparse.ArgumentParser(description="Auto-chess")
    ap.add_argument("--pretend", action="store_true",
                    help="no arm or camera: the arm's moves are printed, you click your moves on the screen")
    ap.add_argument("--fullscreen", action="store_true", help="fill the screen (Esc leaves full screen)")
    args = ap.parse_args()

    if not args.pretend:
        raise SystemExit("The real arm and camera aren't connected yet: run with --pretend for now.")
    arm, eyes = PretendArm(), ClickEyes()

    engine = Engine()
    root = tk.Tk()
    if args.fullscreen:
        root.attributes("-fullscreen", True)
        root.bind("<Escape>", lambda e: root.attributes("-fullscreen", False))
    App(root, engine, arm, eyes, clickable=isinstance(eyes, ClickEyes))
    try:
        root.mainloop()
    finally:
        engine.close()


if __name__ == "__main__":
    main()

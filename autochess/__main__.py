"""Start Auto-chess:  python3 -m autochess [--pretend] [--fullscreen]

With the real arm (the default), start the arm bringup first and calibrate the board once
(python3 -m autochess.calibrate). The camera isn't connected yet, so in human games you move
your piece on the board and also click it on the screen.
"""
import argparse
import sys
import tkinter as tk

from .engine import Engine
from .gui import App
from .pretend import ClickEyes, PretendArm


def main():
    ap = argparse.ArgumentParser(description="Auto-chess")
    ap.add_argument("--pretend", action="store_true",
                    help="no arm: the arm's moves are printed, you click your moves on the screen")
    ap.add_argument("--fullscreen", action="store_true", help="fill the screen (Esc leaves full screen)")
    args = ap.parse_args()

    eyes = ClickEyes()
    ros = None
    if args.pretend:
        arm = PretendArm()
    else:
        from .geometry import Board
        from .motion import Unsafe
        from .robot_arm import RealArm
        from .ros_arm import RosArm
        try:
            geo = Board.load()
        except FileNotFoundError as e:
            sys.exit(str(e))
        ros = RosArm()
        arm = RealArm(ros, geo)
        input("Clear the board of hands, keep a hand near the 12 V switch. Press Enter to park the arm... ")
        try:
            arm.start()
        except (ValueError, Unsafe) as e:
            ros.close()
            sys.exit(f"Not moving: {e}")

    engine = Engine()
    root = tk.Tk()
    if args.fullscreen:
        root.attributes("-fullscreen", True)
        root.bind("<Escape>", lambda e: root.attributes("-fullscreen", False))
    App(root, engine, arm, eyes, clickable=True)
    try:
        root.mainloop()
    finally:
        engine.close()
        if ros:
            ros.close()


if __name__ == "__main__":
    main()

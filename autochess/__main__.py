"""Start Auto-chess:  python3 -m autochess [--pretend] [--camera] [--fullscreen]

With the real arm (the default), start the arm bringup first and calibrate the board once
(python3 -m autochess.calibrate). Without --camera, in human games you move your piece on the board
and also click it on the screen. With --camera, you only move the piece and press Done: the camera
reads your move, and finds the board again at the start of every game (see the README).
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
                    help="no arm: the arm's moves are printed (with --camera you can still test reading moves)")
    ap.add_argument("--camera", action="store_true",
                    help="read the human's moves with the camera instead of clicking them on the screen")
    ap.add_argument("--camera-device", type=int, default=0, help="the camera's number (default 0 = /dev/video0)")
    ap.add_argument("--fullscreen", action="store_true", help="fill the screen (Esc leaves full screen)")
    args = ap.parse_args()

    eyes, clickable, camera, ros, geo = ClickEyes(), True, None, None, None
    if args.camera:
        from .geometry import Board
        from .vision.camera import Camera
        from .vision.eyes import CameraEyes
        from .vision.tracking import CameraCal
        try:
            cal = CameraCal.load()
        except FileNotFoundError as e:
            sys.exit(str(e))
        try:
            geo = Board.load()                    # lets the camera re-aim the arm's board; optional in --pretend
        except FileNotFoundError:
            if not args.pretend:
                sys.exit("the board isn't calibrated yet: python3 -m autochess.calibrate")
        try:
            camera = Camera(args.camera_device)
        except RuntimeError as e:
            sys.exit(str(e))
        eyes, clickable = CameraEyes(camera, cal, geo), False

    if args.pretend:
        arm = PretendArm()
    else:
        from .geometry import Board
        from .motion import Unsafe
        from .robot_arm import RealArm
        from .ros_arm import RosArm
        try:
            geo = geo or Board.load()
        except FileNotFoundError as e:
            sys.exit(str(e))
        ros = RosArm()
        arm = RealArm(ros, geo)                   # shares geo with the camera: its board position follows the markers
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
    App(root, engine, arm, eyes, clickable=clickable)
    try:
        root.mainloop()
    finally:
        engine.close()
        if camera:
            camera.close()
        if ros:
            ros.close()


if __name__ == "__main__":
    main()

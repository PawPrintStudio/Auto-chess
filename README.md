# Auto-chess

A chess-playing robot arm. An OpenMANIPULATOR-X arm, driven by an NVIDIA Jetson Orin NX with
ROS 2 Humble, plays chess against a person on a real board: a camera watches the board, a chess
engine picks the reply, and the arm moves the pieces.

It runs on the same Jetson and the same arm as
[Robo](https://github.com/aditya-baniya-ai/Open_manipulator_x), the Ingram Hall Makerspace robot
(Texas State University). Everything this project inherits from Robo (hardware, Jetson setup,
arm coordinates, safety rules) is written down in [docs/robo_handoff.md](docs/robo_handoff.md).

> **Status:** just started. Nothing runs yet. This README is updated as each part is built.

---

## Hardware

| Part | Details |
|---|---|
| Arm | OpenMANIPULATOR-X, 5 DYNAMIXEL XM430-W350-T servos (IDs 11–15), 12 V |
| Controller board | OpenCR 1.0 with ROBOTIS `usb_to_dxl` firmware, on `/dev/ttyACM0` |
| Computer | NVIDIA Jetson Orin NX 16GB, Ubuntu 22.04, JetPack 6, Python 3.10 |
| Camera | Logitech BRIO (`/dev/video0`), to be mounted above the board |
| Board | to be decided: at most 23 mm squares (184 mm board), placed 70 mm in front of the base |

## Setting up

### 1. The Jetson

Set up the Jetson exactly as Robo's README Part 1 describes (ROS 2 Humble, the ROBOTIS workspace
in `~/colcon_ws`, the base-servo gains, the 25 W power mode and the Python version pins). Details
are in [docs/robo_handoff.md](docs/robo_handoff.md), section 4. If the Jetson already runs Robo,
nothing needs installing again.

### 2. Get this repository

```bash
cd ~/Documents
git clone https://github.com/PawPrintStudio/Auto-chess.git
```

### 3. Before running anything, stop Robo

Only one program can use the arm and the camera at a time.

```bash
~/Documents/Open_manipulator_x/launch/autostart.sh off
~/Documents/Open_manipulator_x/launch/stop.sh
```

More steps will be added here as the project is built.

## Plan

1. Choose the board and pieces so the gripper can hold them (the gripper can't close below about 20 mm).
2. Arm moves: pick a piece from a square and put it on another, in simulation first.
3. Board vision: overhead camera, 4-corner calibration, spot the human's move by comparing the board before and after.
4. Chess brain: Stockfish with `python-chess`.
5. Put it together into one game loop, with a launch and a stop script.
6. Extras: spoken moves, sounds for check and checkmate.

## Safety

- Only one program may use the arm at a time, and only one may use the camera.
- With the 12 V off the arm slumps: hold it upright when powering on, and hold it when stopping.
- Test new moves in the simulation (RViz) before running them on the real arm.

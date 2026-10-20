# Auto-chess

A chess-playing robot arm. An OpenMANIPULATOR-X arm, hanging upside down above a real chess
board and driven by an NVIDIA Jetson Orin NX with ROS 2 Humble, plays chess: a camera watches
the board, Stockfish picks the moves, and the arm moves the pieces.

Two ways to play:

- **Robot vs robot:** the arm plays both White and Black, one move each, at a difficulty you pick for each side.
- **Human vs robot:** a visitor types their name, picks a difficulty (Beginner, Easy, Medium, Hard), a time (10, 15, 30 or 60 minutes per side, never less than 10) and a colour (White, Black or Random), then plays the robot.

It runs on the same Jetson and the same arm as
[Robo](https://github.com/aditya-baniya-ai/Open_manipulator_x), the Ingram Hall Makerspace robot
(Texas State University). Everything this project inherits from Robo (hardware, Jetson setup,
arm coordinates, safety rules) is written down in [docs/robo_handoff.md](docs/robo_handoff.md).

> **Status:** the chess core and the screen are done and work with a pretend arm (you click your
> moves on the screen). Still to come: the arm, the camera, and the launch scripts.

---

## Hardware

| Part | Details |
|---|---|
| Arm | OpenMANIPULATOR-X, 5 DYNAMIXEL XM430-W350-T servos (IDs 11–15), 12 V |
| Mount | upside down on a frame, base plate about 400–425 mm above the centre of the board |
| Controller board | OpenCR 1.0 with ROBOTIS `usb_to_dxl` firmware, on `/dev/ttyACM0` |
| Computer | NVIDIA Jetson Orin NX 16GB, Ubuntu 22.04, JetPack 6, Python 3.10 |
| Camera | looking down at the board |
| Board | wooden board, 40 mm squares (320 mm playing area); tallest piece (king) 80 mm |

Why upside down: on the table the arm can't reach the far rows of a 40 mm board. Hanging
400–425 mm above the board centre, it reaches every square (gripper tilted up to 20–30°).

## Setting up

### 1. The Jetson

Set up the Jetson exactly as Robo's README Part 1 describes (ROS 2 Humble, the ROBOTIS workspace
in `~/colcon_ws`, the base-servo gains, the 25 W power mode and the Python version pins). Details
are in [docs/robo_handoff.md](docs/robo_handoff.md), section 4. If the Jetson already runs Robo,
none of that needs installing again.

Then add Stockfish and the chess package (keeping NumPy below 2):

```bash
sudo apt install stockfish
pip3 install --user "chess==1.11.2" "numpy<2"
```

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

### Working on a Mac (no arm needed)

The code is written and tested on a Mac with a pretend arm, then pulled onto the Jetson.

```bash
brew install stockfish
cd Auto-chess
python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

## Running it

For now only the pretend mode works: the arm's moves are printed in the terminal, and you make
your moves by clicking a piece and then its square on the screen.

```bash
python3 -m autochess --pretend               # on the Jetson (or .venv/bin/python on a Mac)
python3 -m autochess --pretend --fullscreen  # fill the screen; Esc leaves full screen
```

- **Play the robot:** type your name, pick a difficulty, your colour and the time, then Start.
  Make your move and press **Done** (or Enter or Space) to stop your clock. Resign at any time.
- **Watch robot vs robot:** pick a difficulty for White and for Black, and the time, then Start.
  Stop game ends it early.
- The robot's clock only counts its thinking time, not the time the arm spends moving.
- Finished games are saved in `data/results.jsonl` (not in git). The start screen shows a
  leaderboard of wins against the robot for each difficulty.

## How the code is organised

| File | What it does |
|---|---|
| `autochess/engine.py` | Stockfish with four levels: Beginner, Easy, Medium, Hard (skill level and thinking time) |
| `autochess/clock.py` | Chess clock: 10/15/30/60-minute presets, never under 10; only thinking time counts, not arm movement |
| `autochess/game.py` | One game: whose turn, the robot's moves, the human's Done button, resigning, checkmate, draws, running out of time |
| `autochess/gui.py` | The screen: start screen (mode, name, difficulty, colour, time, leaderboard) and game screen (board, clocks, moves, Done, Resign) |
| `autochess/results.py` | Saves each finished game and builds the leaderboard |
| `autochess/__main__.py` | Starts it all: `python3 -m autochess` |
| `autochess/pretend.py` | A pretend arm and pretend eyes, so everything runs without the robot |
| `tests/` | Tests (`python -m pytest -q`) |

## Plan

1. ~~Chess core: Stockfish levels, clock, game loop.~~ Done.
2. ~~Screen: start screen, game screen, saved results and a leaderboard.~~ Done.
3. Arm: board positions for the hanging arm, pick and place, captures, castling, en passant, promotion. Simulation first.
4. Camera: 4-corner board calibration, spotting the human's move by comparing the board before and after.
5. Put it together on the Jetson, with a launch and a stop script.

## Safety

- Only one program may use the arm at a time, and only one may use the camera.
- With the 12 V off the arm slumps: hold it when powering on and when stopping. Hanging upside down, it falls *toward the board*, so keep hands and pieces clear.
- Test new moves in the simulation (RViz) before running them on the real arm.

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

> **Status:** the chess core, the screen and the arm are written. Robot vs robot runs on the real
> arm with no camera needed; in human games you also click your move on the screen until the camera
> step is done. Tested with a fake arm on a Mac; **not yet run on the real arm.** Still to come: the
> camera, and the launch and stop scripts.

---

## Hardware

| Part | Details |
|---|---|
| Arm | OpenMANIPULATOR-X, 5 DYNAMIXEL XM430-W350-T servos (IDs 11–15), 12 V |
| Fingertips | 3D-printed extensions, **40 mm** longer than the stock fingers, so the fingertips reach between the pieces without touching their neighbours. The code uses 190 mm from the wrist to the fingertips (`FINGERS` in `autochess/kinematics.py`; the stock fingers were ~150) |
| Mount | upside down from an aluminium-extrusion frame: the bottom of the base plate about **480 mm** above the top of the board (430 mm with the stock fingers; the 40 mm longer fingertips need the arm about 5 cm higher to carry pieces over the king), the base axis within about 2 cm of the board centre |
| Controller board | OpenCR 1.0 with ROBOTIS `usb_to_dxl` firmware, on `/dev/ttyACM0` |
| Computer | NVIDIA Jetson Orin NX 16GB, Ubuntu 22.04, JetPack 6, Python 3.10 |
| Camera | Logitech BRIO, to look down at the board (not used yet) |
| Board | wooden board, 305 × 305 mm, squares about 38–40 mm; tallest piece (king) 80 mm |
| Bin | a small box right next to the middle of one side of the board, about 20–22 cm from the point under the base, for captured pieces (further out, the arm lets go above it and the piece drops in) |

Why upside down: standing on the table, the arm can't reach the far rows of this board. Hanging
about 48 cm above the board centre, it reaches every square (gripper tilted up to 30°). The base turns
through its full range (±179°, more than Robo's ±160°), so leave enough slack in its cables for a
full turn. Directly behind the arm the two ends of that range meet: moves that cross there swing
the base round the long way, slowly and at a safe height.

## Setting up

### 1. The Jetson

Set up the Jetson exactly as Robo's README Part 1 describes (ROS 2 Humble, the ROBOTIS workspace
in `~/colcon_ws`, the base-servo gains, the 25 W power mode and the Python version pins). Details
are in [docs/robo_handoff.md](docs/robo_handoff.md), section 4. If the Jetson already runs Robo,
none of that needs installing again.

### 2. Get this repository and install what Auto-chess adds

```bash
cd ~/Documents
git clone https://github.com/PawPrintStudio/Auto-chess.git
cd Auto-chess
./setup/jetson_setup.sh
```

The setup script needs internet once. It installs Stockfish, Tkinter, the chess-piece font,
`python-chess` (with `--no-deps`, so it never upgrades NumPy or OpenCV) and pytest. It only adds
things, so Robo keeps working, and it's safe to run again. At the end it runs the check below.

If apt says a release file is **"not valid yet"**, the Jetson's clock is wrong (the script checks
this first). Set it, then run the script again:

```bash
sudo timedatectl set-ntp true
sudo date -s "$(curl -sI http://google.com | grep -i '^date:' | cut -d' ' -f2-)"
```

### 3. Check everything is installed

```bash
python3 -m autochess.check
```

It checks Python, the packages and their version pins, Stockfish (all four levels), a full
robot-vs-robot game with the pretend arm, ROS 2 Humble, the ROBOTIS packages, the base-servo gains
and the `dialout` group. **FAIL** lines must be fixed. **WARN** lines are fine until the robot is
set up: the arm port (`/dev/ttyACM0`), the camera, the power mode, and whether Robo is running.

### 4. Before running anything, stop Robo

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

With the real arm (after the steps in [Playing with the real arm](#playing-with-the-real-arm)):

```bash
python3 -m autochess                # the real arm
python3 -m autochess --fullscreen   # fill the screen; Esc leaves full screen
```

Without the arm, the pretend mode prints the arm's moves in the terminal instead:

```bash
python3 -m autochess --pretend      # on the Jetson (or .venv/bin/python on a Mac)
```

Until the camera is connected, in human games you move your piece on the board **and** click it
on the screen (the piece, then its square), then press Done.

- **Play the robot:** type your name, pick a difficulty, your colour and the time, then Start.
  Make your move and press **Done** (or Enter or Space) to stop your clock. Resign at any time.
- **Watch robot vs robot:** pick a difficulty for White and for Black, and the time, then Start.
  Stop game ends it early.
- The robot's clock only counts its thinking time, not the time the arm spends moving.
- Finished games are saved in `data/results.jsonl` (not in git). The start screen shows a
  leaderboard of wins against the robot for each difficulty.

## Playing with the real arm

Do these in order the first time. Afterwards, only steps 1–3 and 7 are needed.

**1. Before switching on**
- Stop Robo and keep its autostart off (see Setting up, step 4). Never use Robo's panel or
  gestures on the hanging arm: they assume it stands on a table.
- Check the base's cables have slack for a full turn (±179°).
- Nothing on or near the board except what you're testing. Keep hands clear while it moves.

**2. Switch on and start the arm**

Let the arm hang straight down, switch on the 12 V, then:

```bash
ros2 launch open_manipulator_x_bringup hardware.launch.py port_name:=/dev/ttyACM0
```

Leave that running. Use a second terminal for everything below, from `~/Documents/Auto-chess`.

**3. Park it**

```bash
python3 -m autochess.park
```

The park pose folds the arm up under the beam: about 19 cm above the board (the king is 8 cm),
sticking out only about 14 cm, and at least 7 cm clear of the mount plate. (ROBOTIS's "home", all
joints at 0, isn't used: hanging, it sticks the forearm out sideways about 30 cm.) Before moving it
checks the arm's angles are sensible (a limp arm hangs just past the elbow limit, which is
allowed), that the move stays clear of the plate, and that the arm never goes lower on the way.
If moving all the joints together would dip lower (for example when the arm is bent with the
gripper near the table), it moves one joint at a time in the safest order instead. If even that
isn't safe (the arm stretched far out, say), it searches for a chain of small one-joint moves
that is (this takes a few seconds). It prints the moves, asks, and moves slowly.

**4. Calibrate the board (once, and again if the board or the frame moves)**

Take the pieces off, leave the board where it will stay (mark or fix its position), and put the
bin for captured pieces right next to the middle of one side, about 20–22 cm from the point under
the arm. A new calibration keeps the grip settings you tuned with `try_move`. Each corner is saved as soon as you
confirm it: if a calibration stops part way, the next one offers to keep those corners and ask only
for the rest (as long as neither the board nor the arm has moved). The corners are written to
`data/board.json` straight after the fourth, before the e5 check and the bin. To move only the bin
later: `python3 -m autochess.calibrate --bin-only`. If you raise or lower the arm **straight up or down** on
the frame, you don't have to touch the corners again: measure how far it moved and run
`python3 -m autochess.calibrate --raised 35` (35 mm up; use a negative number for down). It shifts
the saved calibration and reports the new carrying height, without moving the arm. Then:

```bash
python3 -m autochess.calibrate --height 430
```

`--height` is roughly the distance from the board up to the base plate. You steer the arm with the
keyboard, one motor at a time (wait for each move to finish before the next key):

| Keys | Motor | | Keys | |
|---|---|---|---|---|
| `a` / `z` | base +/- | | `1` `2` `3` | steps of 1, 3 or 10 degrees |
| `s` / `x` | shoulder +/- | | `Enter` | this is the spot |
| `d` / `c` | elbow +/- | | `q` | quit without saving |
| `f` / `v` | wrist +/- | | `m` | switch to fingertip keys (`w s a d` across, `r f` up and down) |

The line on screen shows each motor's angle, roughly how high the fingertips are above the board,
and how far the gripper is tilted from straight down (keep it near 0 when you touch a square).
Touch the centres of **a1** (White's left corner), **h1** (White's right corner), **a8** (Black's
corner on White's left) and **h8** (Black's corner on White's right) with the closed fingertips, the
gripper **straight down** (if it's tilted more than 5°, it tells you which wrist key straightens it),
then go 5–10 cm above the bin. Every other square
is blended from those four corners. It also picks the carrying height: the highest (up to 145 mm) at which the arm
reaches every square. If that's under 145 mm, the arm hangs a bit low: it says how much to raise it.
It then shows you e5, in the middle, to check. However it ends (finished,
`q`, or an error), the arm goes back to its home pose by itself. The result is saved in
`data/board.json` (not in git: it belongs to this robot).

**Fitting the 40 mm fingertip extensions** (or any other change to the fingers)

The corners and the bin are saved as points in space, so they stay valid when the fingers change,
as long as the arm hasn't moved. What changes is how far down the arm reaches, and so how high it
can carry pieces: with the extensions and the arm at its old height, the carrying height drops by
about 4 cm (to under 9 cm: below the tallest pieces). So:

1. Update the code (`FINGERS` and the park pose already are) before moving the arm: the old park pose
   would fold the longer fingers into the mount plate.
2. Raise the arm **5 cm** straight up on the frame (without turning it), then run
   `python3 -m autochess.calibrate --raised 50` (no arm movement, no corners to touch). It reports the
   new carrying height; aim for 12 cm or more (the highest it will pick is 14.5 cm).
3. Check it with `python3 -m autochess.try_move e2e4`, then re-tune the grip heights (step 5): the fingertips
   are now the ends of the extensions.
4. If the fingertips end up hovering or pressing on the board, the extensions aren't exactly 40 mm
   longer: change `FINGERS` or touch the four corners again (`python3 -m autochess.calibrate --height 480`).

**5. Test single moves and tune the grip**

Set up the pieces in the starting position, then for example:

```bash
python3 -m autochess.try_move e2e4
python3 -m autochess.try_move g1f3 --grip n=30           # try the knight gripped 30 mm up
python3 -m autochess.try_move g1f3 --grip n=30 --save    # keep that height
```

Each piece type is gripped at its own height above the board (pawn 22, rook 25, knight 28,
bishop 32, queen 38, king 42 mm to start with). The gripper opens only part way (about 40 mm),
so it doesn't knock the neighbouring pieces. When the arm starts, it closes the gripper once on
nothing to learn where empty fingers end up; later, fingers that stop at least 1 mm short of
that are holding a piece. Each close prints the finger position, e.g.
`[arm] gripper closed to -0.0052 on the pawn (holding it)`.

**Gripping near the top of the pieces.** With the 40 mm extensions the fingertips can close high up on a
piece, so the arm doesn't have to go far down. `python3 -m autochess.grips` shows the grip heights,
and `python3 -m autochess.grips --top 14` proposes closing the fingertips 14 mm below each piece's
top (heights from `PIECE_HEIGHT` in `geometry.py`: pawn 40, rook 43, knight 51, bishop 60, queen 72,
king 80 mm); add `--save` to keep it. A piece gripped high hangs low below the fingertips when carried
(its bottom must stay 15 mm above the 80 mm king), so the carrying height limits the grip: the tall
pieces are lowered to fit, and each 1 cm the arm is raised on the frame allows about 1 cm higher grips.
Check with `try_move e2e4 --hover 30` before the first real grab.

Each piece type also has its own squeeze (default 60 for all). If a tall piece (bishop, queen,
king) slips while being carried, give it more: `python3 -m autochess.try_move d2d4 d7d5 d1d3 --effort q=80 --save`.

**6. If something goes wrong**

While carrying, the arm keeps its elbow and wrist above the tallest piece (the 80 mm king) plus
15 mm, and the fingertips that much higher again as the held piece hangs below them. It measures
this from the board surface right under it, so a board that isn't quite level is fine.

Before the gripper closes on a piece or lets go of one, the arm checks that its joints really
reached the pose it was sent to (within about 3°, waiting up to 2 s for them to settle). The
controller says "done" even when a joint stalls short, for example an elbow against its limit,
and a piece let go from the wrong place lands on the wrong square. If a joint is still off, the
gripper isn't touched, and the arm handles it like a failed move (below), saying which joint is off.

In robot-vs-robot games, if Stockfish's choice needs a square (or the bin) the arm can't reach, the
arm plays the best of the engine's top 8 moves that it can reach instead.

If the gripper closes on nothing (twice), or a square can't be reached, the arm puts back
anything it's holding, parks, and the screen tells you what to do by hand ("Please move the
knight from g1 to f3, and press Done"). The game then carries on. For a promotion, it takes the
pawn away and asks you to put the new queen on the board.

**7. Play**

```bash
python3 -m autochess
```

It asks before parking the arm, then opens the screen. Choose **Watch robot vs robot** for the arm
to play itself, or **Play the robot**.

Every time someone presses **Start**, the arm first goes to its home (park) pose from wherever it
is, by the same safe route as `autochess.park` (the screen says so), so a game always starts from
the same place even if the arm was moved by hand. If it can't get there safely, the game doesn't
start and the screen says why.

**Switching off:** the arm goes limp and swings down. Park it first, then hold it while you
switch off the 12 V.

## How the code is organised

| File | What it does |
|---|---|
| `autochess/engine.py` | Stockfish with four levels: Beginner, Easy, Medium, Hard (skill level and thinking time) |
| `autochess/clock.py` | Chess clock: 10/15/30/60-minute presets, never under 10; only thinking time counts, not arm movement |
| `autochess/game.py` | One game: whose turn, the robot's moves, the human's Done button, resigning, checkmate, draws, running out of time |
| `autochess/gui.py` | The screen: start screen (mode, name, difficulty, colour, time, leaderboard) and game screen (board, clocks, moves, Done, Resign) |
| `autochess/results.py` | Saves each finished game and builds the leaderboard |
| `autochess/__main__.py` | Starts it all: `python3 -m autochess` |
| `autochess/check.py` | Checks every dependency: `python3 -m autochess.check` |
| `setup/jetson_setup.sh` | Installs what Auto-chess adds on the Jetson |
| `autochess/kinematics.py` | Geometry of the hanging arm: forward and inverse kinematics, the park pose, checks that the arm stays clear of the mount and keeps its elbow above the gripper |
| `autochess/ros_arm.py` | Talks to the ROBOTIS arm and gripper controllers through ROS 2 |
| `autochess/park.py` | Folds the arm into the park pose: `python3 -m autochess.park` |
| `autochess/motion.py` | Safe moves: joint moves that never dip over the board, straight lines up and down, parking |
| `autochess/geometry.py` | Where every square is (from the calibration), grip heights for each piece |
| `autochess/calibrate.py` | Keyboard calibration of the board: `python3 -m autochess.calibrate` |
| `autochess/robot_arm.py` | Turns a chess move into arm steps (captures, castling, en passant, promotion) and asks for help if one fails |
| `autochess/try_move.py` | Plays test moves with the real arm and tunes grip heights: `python3 -m autochess.try_move` |
| `autochess/pretend.py` | A pretend arm and pretend eyes, so everything runs without the robot |
| `tests/` | Tests (`python -m pytest -q`) |

## Plan

1. ~~Chess core: Stockfish levels, clock, game loop.~~ Done.
2. ~~Screen: start screen, game screen, saved results and a leaderboard.~~ Done.
3. ~~Arm: park pose, calibration, pick and place, captures, castling, en passant, promotion.~~ Written; first real-arm test next.
4. Camera: 4-corner board calibration, spotting the human's move by comparing the board before and after.
5. Put it together on the Jetson, with a launch and a stop script.

## Safety

- Only one program may use the arm at a time, and only one may use the camera.
- With the 12 V off the arm slumps: hold it when powering on and when stopping. Hanging upside down, it falls *toward the board*, so keep hands and pieces clear.
- Every command that moves the arm asks first. Keep a hand near the 12 V switch the first few times.
- The simulation (RViz with fake hardware, see Robo's handoff notes) can be used to watch new moves first, but it shows the arm the right way up.

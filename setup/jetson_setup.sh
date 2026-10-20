#!/usr/bin/env bash
# Install what Auto-chess needs on the Jetson, on top of Robo's setup (ROS 2 Humble, ~/colcon_ws,
# pinned Python packages). It only adds things: nothing Robo uses is upgraded or removed.
# Safe to run again. Needs internet once; the game itself runs offline.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== System packages (Stockfish, Tkinter, chess-piece font) =="
sudo apt-get update
sudo apt-get install -y stockfish python3-tk fonts-dejavu-core git

echo "== Python packages (user site, no dependency upgrades) =="
# python-chess has no dependencies; --no-deps makes sure pip never touches NumPy, OpenCV etc.
pip3 install --user --no-deps "chess==1.11.2"
# pytest for the tests (optional). Pinned, and its own small dependencies only.
pip3 install --user "pytest==8.3.5" || echo "(pytest didn't install: the tests are optional)"

echo "== Check =="
python3 -m autochess.check

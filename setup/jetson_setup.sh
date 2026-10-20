#!/usr/bin/env bash
# Install what Auto-chess needs on the Jetson, on top of Robo's setup (ROS 2 Humble, ~/colcon_ws,
# pinned Python packages). It only adds things: nothing Robo uses is upgraded or removed.
# Safe to run again. Needs internet once; the game itself runs offline.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== Clock =="
# A wrong clock makes apt and HTTPS refuse everything ("not valid yet"). Compare with a web server.
web=$(curl -sI --max-time 10 http://google.com | grep -i '^date:' | cut -d' ' -f2- | tr -d '\r' || true)
if [ -n "$web" ]; then
    off=$(( $(date +%s) - $(date -d "$web" +%s) ))
    if [ "${off#-}" -gt 300 ]; then
        echo "The Jetson's clock is off by $(( off / 60 )) minutes. Fix it, then run this again:"
        echo "  sudo timedatectl set-ntp true"
        echo "  sudo date -s \"\$(curl -sI http://google.com | grep -i '^date:' | cut -d' ' -f2-)\""
        exit 1
    fi
    echo "ok"
else
    echo "(couldn't reach the internet to check the clock; carrying on)"
fi

echo "== System packages (Stockfish, Tkinter, chess-piece font) =="
# One broken extra repository (Docker, Kitware...) shouldn't stop the install.
sudo apt-get update || echo "(some package lists didn't update; trying the install anyway)"
sudo apt-get install -y stockfish python3-tk fonts-dejavu-core git

echo "== Python packages (user site, no dependency upgrades) =="
# python-chess has no dependencies; --no-deps makes sure pip never touches NumPy, OpenCV etc.
pip3 install --user --no-deps "chess==1.11.2"
# pytest for the tests (optional). Pinned, and its own small dependencies only.
pip3 install --user "pytest==8.3.5" || echo "(pytest didn't install: the tests are optional)"

echo "== Check =="
python3 -m autochess.check

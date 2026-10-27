"""Stockfish with four named difficulty levels."""
import os
import shutil
import threading
from dataclasses import dataclass

import chess
import chess.engine


@dataclass(frozen=True)
class Level:
    name: str
    skill: int              # Stockfish "Skill Level", 0 (weakest) to 20
    think: float            # seconds per move
    depth: int | None = None


LEVELS = {
    "Beginner": Level("Beginner", skill=0, think=0.05, depth=1),
    "Easy": Level("Easy", skill=3, think=0.1, depth=4),
    "Medium": Level("Medium", skill=8, think=0.3),
    "Hard": Level("Hard", skill=20, think=1.0),
}
LEVEL_NAMES = list(LEVELS)
FALLBACK_LINES = 8      # how many of the engine's best moves to look through for one the arm can play


def find_stockfish():
    """Stockfish from $STOCKFISH, the PATH, or where apt puts it on Ubuntu."""
    for path in (os.environ.get("STOCKFISH"), shutil.which("stockfish"), "/usr/games/stockfish"):
        if path and os.path.exists(path):
            return path
    raise FileNotFoundError("Stockfish not found: sudo apt install stockfish (Jetson) or brew install stockfish (Mac)")


class Engine:
    """One Stockfish process; each call says which level to play at."""

    def __init__(self, path=None, levels=LEVELS):
        self.levels = levels
        self._sf = chess.engine.SimpleEngine.popen_uci(path or find_stockfish())
        self._lock = threading.Lock()

    def choose(self, board, level, max_think=None, playable=None):
        """Pick a move for the side to move. max_think caps the time (for a low clock).
        playable(move) says whether the arm can make a move: if the first choice isn't playable, the
        best playable one among the engine's top FALLBACK_LINES moves is played instead (if none is,
        the first choice stands and the arm asks for help)."""
        lv = self.levels[level] if isinstance(level, str) else level
        think = lv.think if max_think is None else max(0.01, min(lv.think, max_think))
        with self._lock:
            self._sf.configure({"Skill Level": lv.skill})
            result = self._sf.play(board, chess.engine.Limit(time=think, depth=lv.depth))
            if playable is None or playable(result.move):
                return result.move
            lines = self._sf.analyse(board, chess.engine.Limit(time=think, depth=lv.depth), multipv=FALLBACK_LINES)
        for info in lines:                      # best first
            pv = info.get("pv")
            if pv and playable(pv[0]):
                return pv[0]
        return result.move

    def close(self):
        with self._lock:
            self._sf.quit()

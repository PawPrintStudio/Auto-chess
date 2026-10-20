"""Pretend arm and eyes, so the game and the GUI run on any computer."""
import threading
import time


class PretendArm:
    """Prints the move instead of playing it, and takes a moment like the real arm."""

    def __init__(self, seconds=0.5, log=print):
        self.seconds, self.log = seconds, log

    def play(self, board, move):
        self.log(f"[pretend arm] {board.san(move)} ({move.uci()})")
        time.sleep(self.seconds)


class ClickEyes:
    """The human's move comes from clicks on the screen instead of the camera."""

    def __init__(self):
        self._move = None
        self._lock = threading.Lock()

    def set_move(self, move):
        with self._lock:
            self._move = move

    def read_move(self, board):
        with self._lock:
            move, self._move = self._move, None
        return move


class ScriptedEyes:
    """Returns moves from a list, for tests."""

    def __init__(self, moves):
        self.moves = list(moves)

    def read_move(self, board):
        return self.moves.pop(0) if self.moves else None

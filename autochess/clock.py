"""A two-sided chess clock. Only one side's time runs at once, or none (while the arm moves)."""
import threading
import time

import chess

TIME_PRESETS = [10, 15, 30, 60]   # minutes per side
MIN_MINUTES = 10


class ChessClock:
    def __init__(self, minutes, now=time.monotonic):
        if minutes < MIN_MINUTES:
            raise ValueError(f"games are at least {MIN_MINUTES} minutes")
        self._now = now
        self._left = {chess.WHITE: minutes * 60.0, chess.BLACK: minutes * 60.0}
        self._running = None          # chess.WHITE, chess.BLACK or None
        self._since = 0.0
        self._lock = threading.Lock()

    def _settle(self):
        if self._running is not None:
            t = self._now()
            self._left[self._running] -= t - self._since
            self._since = t

    def run(self, side):
        """Start this side's time (stopping the other's)."""
        with self._lock:
            self._settle()
            self._running = side
            self._since = self._now()

    def pause(self):
        with self._lock:
            self._settle()
            self._running = None

    @property
    def running(self):
        return self._running

    def left(self, side):
        """Seconds left for a side, never below 0."""
        with self._lock:
            self._settle()
            return max(0.0, self._left[side])

    def flagged(self, side):
        return self.left(side) <= 0.0


def fmt(seconds):
    """Clock display, e.g. 9:05 or 0:42."""
    s = int(seconds + 0.999)
    return f"{s // 60}:{s % 60:02d}"

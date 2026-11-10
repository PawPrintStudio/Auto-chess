"""The camera as the game's eyes: the game asks it to look at the start of each game (find the board,
learn the colours), at the start of each human turn (take the "before" picture, check the robot's last
move), and when the human presses Done (which move was made?).

The game talks to its eyes through three optional calls, so the click-the-screen stand-in
(pretend.ClickEyes) and this class are interchangeable:
  begin_game(board)   raises VisionError if the camera can't be used
  begin_turn(board)   returns the squares that don't look as they should (may be empty)
  read_move(board)    the move just made, or None
"""
import time

import chess
import numpy as np

from .reading import OccupancyModel, expected_labels, interpret, rectify, square_features
from .tracking import BoardTracker, NotTracked


class VisionError(Exception):
    """The camera can't be used for this game."""


class CameraEyes:
    def __init__(self, camera, cal, geo=None, log=print):
        self.camera, self.log = camera, log
        self.tracker = BoardTracker(cal, geo)
        self.geo = geo
        self.model = None           # OccupancyModel, learned in begin_game
        self.before = None          # square colours at the start of the human's turn

    # ---- looking ----
    def _look(self):
        """One fresh picture: where the board is in it, and the colour of every square."""
        frame = self.camera.still_frame()
        try:
            view = self.tracker.view(frame)
        except NotTracked as e:
            raise VisionError(str(e)) from e
        return view, square_features(rectify(frame, view.b2p))

    def track(self, force=False):
        """Find the board with the markers and move the arm's idea of where it is (in place) to match."""
        frame = self.camera.still_frame()
        try:
            view = self.tracker.view(frame)
        except NotTracked as e:
            raise VisionError(str(e)) from e
        if self.geo is None:
            return None
        report = self.tracker.update_geo(view, force=force)
        self.log(f"[camera] markers {report.ids}: {report.message}" + ("" if report.applied else " (NOT applied)"))
        return report

    # ---- the game's three calls ----
    def begin_game(self, board):
        """Start of a game: pieces in the starting position. Finds the board, and learns the colours."""
        if board.board_fen() != chess.STARTING_BOARD_FEN:
            raise VisionError("the camera can only start a game from the starting position")
        report = self.track()
        if report is not None and not report.applied:
            raise VisionError(f"{report.message}. Put the board back, or recalibrate.")
        _, feats = self._look()
        model = OccupancyModel.learn(feats)
        bad = np.nonzero(model.classify(feats) != expected_labels(board))[0]
        if len(bad) > 2:
            raise VisionError("the pieces don't look like the starting position at "
                              + ", ".join(chess.square_name(s) for s in bad[:8]))
        self.model, self.before = model, feats
        self.log("[camera] learned the board and the piece colours")

    def begin_turn(self, board):
        """Take the picture the next move will be compared with. Returns the squares that don't look as
        they should after the last move (the robot's, say), so the screen can say so."""
        if self.model is None:
            return []
        _, feats = self._look()
        self.before = feats
        bad = np.nonzero(self.model.classify(feats) != expected_labels(board))[0]
        return [chess.square_name(s) for s in bad] if 0 < len(bad) <= 6 else []

    def read_move(self, board, timeout=8.0, poll=0.5):
        """The move just made, or None. Keeps looking for a few seconds: a hand still over the board,
        or pieces still being set down, look like no move at all."""
        if self.model is None or self.before is None:
            raise VisionError("the camera isn't ready: begin_game and begin_turn first")
        end = time.time() + timeout
        while True:
            try:
                _, feats = self._look()
                reading = interpret(board, feats, self.before, self.model)
            except VisionError as e:
                reading = None
                why = str(e)
            else:
                if reading.move is not None:
                    self.log(f"[camera] saw {board.san(reading.move)} ({reading.agree}/64 squares agree)")
                    return reading.move
                why = reading.why
            if time.time() >= end:
                self.log(f"[camera] no move: {why}")
                return None
            time.sleep(poll)

    def check(self, board):
        """Squares that don't look as the position says they should (for the debugging tools)."""
        _, feats = self._look()
        bad = np.nonzero(self.model.classify(feats) != expected_labels(board))[0]
        return [chess.square_name(s) for s in bad]

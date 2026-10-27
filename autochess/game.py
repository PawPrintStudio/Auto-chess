"""One game of chess: robot vs robot, or human vs robot.

The game runs in its own thread and reports what happens through on_event(kind, data):
  "preparing" the arm is going to its home pose     {}
  "turn"      a side is to move                    {side, player}
  "thinking"  the robot is choosing a move         {side}
  "arm"       the arm is playing the robot's move  {side, move, san}
  "moved"     a move was made                      {side, move, san}
  "bad_move"  no legal move seen after Done        {side}
  "help"      the arm needs a person; Done when done {text}
  "game_over" the game ended                       {result, reason}

The arm and the eyes (camera) are passed in, so the same game runs with the real arm and
camera on the Jetson or with pretend ones anywhere:
  arm.play(board, move)   plays move on the real board (board is the position before it)
  eyes.read_move(board)   the move the human just made, or None
If the arm has a `prepare()` method, the game calls it first, to send the arm to its home pose;
if that fails the game ends before it starts. If the arm has an `ask` attribute, the game sets it to a function the arm calls when it needs a
person to finish a move by hand: it shows the text and waits for Done.
"""
import threading
import time
from dataclasses import dataclass

import chess

from .clock import ChessClock

REASONS = {
    chess.Termination.CHECKMATE: "checkmate",
    chess.Termination.STALEMATE: "stalemate",
    chess.Termination.INSUFFICIENT_MATERIAL: "not enough pieces to mate",
    chess.Termination.SEVENTYFIVE_MOVES: "75-move rule",
    chess.Termination.FIVEFOLD_REPETITION: "fivefold repetition",
    chess.Termination.FIFTY_MOVES: "50-move rule",
    chess.Termination.THREEFOLD_REPETITION: "threefold repetition",
}


@dataclass
class Player:
    kind: str                # "human" or "robot"
    name: str
    level: str | None = None  # robot only: a name from engine.LEVELS


def side_name(side):
    return "White" if side == chess.WHITE else "Black"


class Game:
    def __init__(self, white, black, minutes, engine, arm, eyes=None, on_event=None, now=time.monotonic):
        self.board = chess.Board()
        self.players = {chess.WHITE: white, chess.BLACK: black}
        self.clock = ChessClock(minutes, now)
        self.minutes = minutes
        self.engine, self.arm, self.eyes = engine, arm, eyes
        self._on_event = on_event or (lambda kind, data: None)
        self._done = threading.Event()
        self._stop = threading.Event()
        self._resigned = None
        self._thread = None
        self.result = None    # "1-0", "0-1", "1/2-1/2" or "*" (stopped)
        self.reason = None
        if hasattr(arm, "ask"):
            arm.ask = self._ask_help

    # ---- called from the GUI ----
    def start(self):
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def press_done(self):
        """The human has finished their move (the clock button)."""
        self._done.set()

    def resign(self, side):
        self._resigned = side

    def stop(self):
        """End the game without a result."""
        self._stop.set()

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)

    # ---- the game ----
    def run(self):
        try:
            if hasattr(self.arm, "prepare"):
                self._emit("preparing")
                try:
                    self.arm.prepare()
                except Exception as e:      # the arm refused or failed to move: don't start
                    self._finish("*", f"The arm couldn't get to its home pose: {e}")
                    return
            while self.result is None:
                if self._interrupted():
                    break
                side = self.board.turn
                player = self.players[side]
                self._emit("turn", side=side, player=player)
                move = self._robot_turn(side, player) if player.kind == "robot" else self._human_turn(side)
                if move is None:
                    break
                san = self.board.san(move)
                self.board.push(move)
                self._emit("moved", side=side, move=move, san=san)
                outcome = self.board.outcome(claim_draw=True)
                if outcome:
                    self._finish(outcome.result(), REASONS.get(outcome.termination, outcome.termination.name.lower()))
        finally:
            self.clock.pause()
            if self.result is None:
                self._finish("*", "stopped")
            self._emit("game_over", result=self.result, reason=self.reason)

    def _robot_turn(self, side, player):
        self.clock.run(side)
        self._emit("thinking", side=side)
        can_play = getattr(self.arm, "can_play", None)       # an arm that knows what it can reach
        move = self.engine.choose(self.board, player.level, max_think=self.clock.left(side) / 30,
                                  playable=(lambda m: can_play(self.board, m)) if can_play else None)
        self.clock.pause()          # the arm's movement doesn't count
        if self.clock.flagged(side):
            self._lose_on_time(side)
            return None
        if self._interrupted():
            return None
        self._emit("arm", side=side, move=move, san=self.board.san(move))
        self.arm.play(self.board, move)
        return move

    def _human_turn(self, side):
        self._done.clear()
        self.clock.run(side)
        while True:
            if self._interrupted():
                return None
            if self.clock.flagged(side):
                self._lose_on_time(side)
                return None
            if not self._done.wait(0.05):
                continue
            self._done.clear()
            self.clock.pause()
            move = self.eyes.read_move(self.board) if self.eyes else None
            if move is not None and move in self.board.legal_moves:
                return move
            self._emit("bad_move", side=side)
            self.clock.run(side)

    def _ask_help(self, text):
        """The arm needs a person: show text and wait for Done (or for the game to be stopped)."""
        self._done.clear()
        self._emit("help", text=text)
        while not self._stop.is_set() and not self._done.wait(0.05):
            pass
        self._done.clear()

    def _interrupted(self):
        """True (and the result set) if the game was stopped or someone resigned."""
        if self._stop.is_set():
            return True
        if self._resigned is not None and self.result is None:
            self._finish("0-1" if self._resigned == chess.WHITE else "1-0", f"{side_name(self._resigned)} resigned")
        return self.result is not None

    def _lose_on_time(self, side):
        if self.board.has_insufficient_material(not side):
            self._finish("1/2-1/2", f"{side_name(side)} ran out of time, but the other side can't mate")
        else:
            self._finish("0-1" if side == chess.WHITE else "1-0", f"{side_name(side)} ran out of time")

    def _finish(self, result, reason):
        self.result, self.reason = result, reason

    def _emit(self, kind, **data):
        self._on_event(kind, data)

    def winner_name(self):
        if self.result == "1-0":
            return self.players[chess.WHITE].name
        if self.result == "0-1":
            return self.players[chess.BLACK].name
        return None

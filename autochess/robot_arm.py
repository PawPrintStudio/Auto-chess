"""The real arm playing moves on the real board.

A chess move becomes physical steps (plan_steps), which the arm carries out one by one. If a step
fails (a piece wasn't gripped, or a square is out of reach), the arm parks and asks a person to do
the rest of the move by hand, then carries on with the game.
"""
import chess
import numpy as np

from .geometry import CLEARANCE, EMPTY_GRIP, GRIP_EFFORT, GRIPPER_CLOSED, TALLEST
from .kinematics import ik, joint_points
from .motion import Mover, Unsafe
from .park import follow, plan

NAMES = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook",
         chess.QUEEN: "queen", chess.KING: "king"}


class Missed(Exception):
    """The gripper closed on nothing."""


def plan_steps(board, move):
    """[(kind, square, piece)] for a move, where kind is "take", "put", "bin" or "ask".
    "take" picks the piece up, "put" puts the held piece down, "bin" drops it in the bin for
    captured pieces, "ask" needs a person (promotion: the arm can't fetch a spare queen)."""
    mover = board.piece_at(move.from_square)
    steps = []
    if board.is_en_passant(move):
        captured = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
        steps += [("take", captured, chess.PAWN), ("bin", None, chess.PAWN)]
    elif board.is_capture(move):
        steps += [("take", move.to_square, board.piece_type_at(move.to_square)),
                  ("bin", None, board.piece_type_at(move.to_square))]
    if board.is_castling(move):
        rank = chess.square_rank(move.from_square)
        kingside = chess.square_file(move.to_square) > chess.square_file(move.from_square)
        rook_from = chess.square(7 if kingside else 0, rank)
        rook_to = chess.square(5 if kingside else 3, rank)
        steps += [("take", move.from_square, chess.KING), ("put", move.to_square, chess.KING),
                  ("take", rook_from, chess.ROOK), ("put", rook_to, chess.ROOK)]
    elif move.promotion:
        steps += [("take", move.from_square, chess.PAWN), ("bin", None, chess.PAWN),
                  ("ask", move.to_square, move.promotion)]
    else:
        steps += [("take", move.from_square, mover.piece_type), ("put", move.to_square, mover.piece_type)]
    return steps


def describe(steps, color):
    """What a person should do by hand to finish these steps."""
    side = "white" if color == chess.WHITE else "black"
    parts, held = [], None
    for kind, sq, piece in steps:
        if kind == "take":
            held = (sq, piece)
        elif kind == "put":
            parts.append(f"move the {NAMES[piece]} from {chess.square_name(held[0])} to {chess.square_name(sq)}"
                         if held else f"put the {NAMES[piece]} on {chess.square_name(sq)}")
            held = None
        elif kind == "bin":
            parts.append(f"take the {NAMES[piece]} off {chess.square_name(held[0])}" if held
                         else f"put the {NAMES[piece]} I'm holding aside")
            held = None
        elif kind == "ask":
            parts.append(f"put a {side} {NAMES[piece]} on {chess.square_name(sq)}")
    return "Please " + ", then ".join(parts) + ", and press Done."


class RealArm:
    def __init__(self, ros_arm, geo, log=print):
        self.ros, self.geo, self.log = ros_arm, geo, log
        self.mover = Mover(ros_arm)
        self.ask = None             # set by the game: ask(text) shows text and waits for Done
        self.holding, self.held = False, None    # held: (square it came from, piece)
        self.empty_limit = EMPTY_GRIP             # learned in start()

    def start(self):
        """Go to the home (park) pose from wherever the arm is now, by the same safe route as
        autochess.park, and open the gripper. Raises ValueError/Unsafe if it can't do so safely."""
        self.mover.refresh()                           # the arm may have been moved by hand
        moves = plan(self.mover.q)
        if not follow(self.ros, moves):
            raise Unsafe("the arm didn't finish going to its home pose")
        if moves:
            self.mover.q = tuple(moves[-1][0])
        # Close once on nothing to learn where empty fingers end up: closing on a piece stops short of that.
        empty = self.ros.gripper(GRIPPER_CLOSED, GRIP_EFFORT)
        self.empty_limit = (empty + self.geo.held_margin) if empty is not None else EMPTY_GRIP
        self.log(f"[arm] empty gripper closes to {empty if empty is not None else float('nan'):+.4f};"
                 f" holding a piece = stops above {self.empty_limit:+.4f}")
        self.ros.gripper(self.geo.gripper_open)
        self.holding = False

    prepare = start             # the game calls this at the start of every game

    def play(self, board, move):
        steps = plan_steps(board, move)
        for i, (kind, sq, piece) in enumerate(steps):
            try:
                if kind == "ask":
                    self._park_and_ask(steps[i:], board.turn)
                    return
                getattr(self, "_" + kind)(sq, piece)
            except (Unsafe, Missed) as e:
                self.log(f"[arm] {kind} {chess.square_name(sq) if sq is not None else ''}: {e}")
                start, note = i, ""
                if self.holding:
                    # Still holding a piece: put it back where it came from, and hand over that whole step.
                    start = max(j for j in range(i + 1) if steps[j][0] == "take")
                    try:
                        self._put(*self.held)
                    except Unsafe:
                        self.ros.gripper(self.geo.gripper_open)
                        self.holding = False
                        note = f"I dropped the {NAMES[self.held[1]]}: put it back on {chess.square_name(self.held[0])}. "
                self._park_and_ask(steps[start:], board.turn, failed=True, note=note)
                return
        self.mover.park()

    # ---- steps ----
    def _above(self, sq):
        return self.geo.square(sq, self.geo.travel)

    def _floor(self):
        """Over the board, nothing may hit the pieces standing on it (up to the 80 mm king): the elbow
        and wrist stay above the king plus a margin, and the fingertips also above whatever hangs
        below them (the held piece's grip height). The board needn't be level."""
        body = TALLEST + CLEARANCE
        tip = body + (self.geo.grip[self.held[1]] if self.holding and self.held else 0.0)

        def clear(point, least):         # only over the board (and just past its edge) are there pieces
            return not self.geo.over_board(point) or self.geo.height_above(point) >= least

        def high_enough(q4):
            elbow, wrist, fingers = joint_points(q4)
            return clear(elbow, body) and clear(wrist, body) and clear(fingers, tip)
        return high_enough

    def _take(self, sq, piece):
        self.mover.go_to(self._above(sq), floor=self._floor())
        self.ros.gripper(self.geo.gripper_open)
        for attempt in range(2):
            self.mover.line_to(self.geo.square(sq, self.geo.grip[piece]))
            got = self.ros.gripper(GRIPPER_CLOSED, GRIP_EFFORT)
            self.log(f"[arm] gripper closed to {got if got is not None else float('nan'):+.4f} on the {NAMES[piece]}"
                     f" ({'holding it' if got is not None and got > self.empty_limit else 'nothing there'})")
            if got is not None and got > self.empty_limit:
                self.holding, self.held = True, (sq, piece)
                self.mover.line_to(self._above(sq))
                return
            self.ros.gripper(self.geo.gripper_open)
            self.mover.line_to(self.geo.square(sq, self.geo.grip[piece] + 20))
        self.mover.line_to(self._above(sq))
        raise Missed(f"couldn't grip the {NAMES[piece]}")

    def _put(self, sq, piece):
        self.mover.go_to(self._above(sq), floor=self._floor())
        self.mover.line_to(self.geo.square(sq, self.geo.grip[piece] + 2))
        self.ros.gripper(self.geo.gripper_open)
        self.holding = False
        self.mover.line_to(self._above(sq))

    def _bin(self, sq, piece):
        drop = self.geo.drop
        above = np.array(drop, float)
        above[2] = min(drop[2], self.geo.floor(self.geo.travel))
        # The bin is low and far out, sometimes reachable only with the arm leaning back over the top.
        # Pick that pose first and reach the point above it the same way, so the arm doesn't flip.
        # Nothing is under the bin, so a joint move down to it is fine.
        q_drop = ik(drop, near=self.mover.q)
        q_up = ik(above, near=q_drop, smooth=True) if q_drop is not None else None
        if q_up is None:
            raise Unsafe("can't reach the bin")
        self.mover.go_to_q(q_up, floor=self._floor())
        try:
            self.mover.joint_move(q_drop, floor=drop[2] + 5)
            lowered = True
        except Unsafe:
            lowered = False          # can't get down to it safely from here: let go above it, it falls in
            self.log("[arm] letting go above the bin instead")
        self.ros.gripper(self.geo.gripper_open)
        self.holding = False
        if lowered:
            self.mover.joint_move(q_up)

    def _park_and_ask(self, steps, color, failed=False, note=""):
        try:
            self.mover.park()
        except Unsafe as e:
            self.log(f"[arm] couldn't park: {e}")
        text = ("I couldn't finish my move. " if failed else "") + note + describe(steps, color)
        if self.ask:
            self.ask(text)
        else:
            input(text + " ")

import chess
import numpy as np
import pytest

from autochess.geometry import GRIPPER_CLOSED, Board
from autochess.kinematics import HANGING, fingertip, ik
from autochess.robot_arm import RealArm, describe, plan_steps

H, SQ = 430.0, 38.0
HALF = 3.5 * SQ


def my_board():
    # Board centred under the arm, 38 mm squares; let go over the bin just off the side, 90 mm up.
    return Board(a1=(-HALF, -HALF, H), h1=(HALF, -HALF, H), a8=(-HALF, HALF, H), drop=(0.0, -205.0, H - 90))


class FakeRos:
    def __init__(self, grips=None):
        self.q = (0.0, *HANGING)
        self.grips = list(grips or [])     # gripper results when closing; default: a piece is held
        self.closes = 0
        self.points = []

    def angles(self):
        return self.q

    def move(self, q4, seconds):
        return self.move_path([q4], [seconds])

    def move_path(self, points, times):
        assert all(b > a for a, b in zip(times, times[1:]))
        self.points += [fingertip(q) for q in points]
        self.q = tuple(points[-1])
        return True

    def gripper(self, position, effort=100.0):
        if position == GRIPPER_CLOSED:
            self.closes += 1
            return self.grips.pop(0) if self.grips else 0.004
        return position


def test_square_positions():
    b = my_board()
    assert b.square(chess.A1) == pytest.approx((-HALF, -HALF, H))
    assert b.square(chess.H8) == pytest.approx((HALF, HALF, H))
    assert b.square(chess.E4, 20) == pytest.approx((0.5 * SQ, -0.5 * SQ, H - 20))
    assert b.square_size() == pytest.approx((SQ, SQ))


def test_every_square_reachable_at_grip_and_travel_heights():
    b = my_board()
    for sq in chess.SQUARES:
        for h in (20.0, 42.0, b.travel):
            assert ik(b.square(sq, h)) is not None, (chess.square_name(sq), h)
    assert ik(b.drop) is not None


def test_plan_steps():
    board = chess.Board()
    assert plan_steps(board, chess.Move.from_uci("e2e4")) == [("take", chess.E2, chess.PAWN),
                                                             ("put", chess.E4, chess.PAWN)]
    board = chess.Board("r3k2r/8/8/3pP3/8/8/8/R3K2R w KQkq d6 0 1")
    ep = plan_steps(board, chess.Move.from_uci("e5d6"))
    assert ep[:2] == [("take", chess.D5, chess.PAWN), ("bin", None, chess.PAWN)]
    castle = plan_steps(board, chess.Move.from_uci("e1g1"))
    assert castle == [("take", chess.E1, chess.KING), ("put", chess.G1, chess.KING),
                      ("take", chess.H1, chess.ROOK), ("put", chess.F1, chess.ROOK)]
    long = plan_steps(board, chess.Move.from_uci("e1c1"))
    assert long[2:] == [("take", chess.A1, chess.ROOK), ("put", chess.D1, chess.ROOK)]
    board = chess.Board("1n6/P7/8/8/8/8/8/k6K w - - 0 1")
    promo = plan_steps(board, chess.Move.from_uci("a7b8q"))
    assert promo == [("take", chess.B8, chess.KNIGHT), ("bin", None, chess.KNIGHT),
                     ("take", chess.A7, chess.PAWN), ("bin", None, chess.PAWN),
                     ("ask", chess.B8, chess.QUEEN)]
    assert describe(promo[-1:], chess.WHITE) == "Please put a white queen on b8, and press Done."


def test_a_move_goes_down_grips_and_never_dips_while_travelling():
    ros = FakeRos()
    arm = RealArm(ros, my_board(), log=print)
    arm.ask = pytest.fail                                # nothing here should need a person
    arm.start()
    board = chess.Board("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1")
    arm.play(board, chess.Move.from_uci("e4d5"))        # a capture: d5 to the bin, then e4 to d5
    assert ros.closes == 2
    lows = [H - p[2] for p in ros.points]
    assert min(lows) == pytest.approx(min(arm.geo.grip[chess.PAWN], H - arm.geo.drop[2]), abs=1)


def test_missed_grip_asks_for_help_and_carries_on():
    ros = FakeRos(grips=[GRIPPER_CLOSED, GRIPPER_CLOSED])  # closes on nothing, twice
    asked = []
    arm = RealArm(ros, my_board(), log=lambda s: None)
    arm.ask = asked.append
    arm.start()
    arm.play(chess.Board(), chess.Move.from_uci("g1f3"))
    assert asked == ["I couldn't finish my move. Please move the knight from g1 to f3, and press Done."]
    assert not arm.holding


def test_whole_robot_game_with_the_arm():
    import shutil
    from autochess.engine import Engine, Level
    from autochess.game import Game, Player
    if not shutil.which("stockfish"):
        pytest.skip("Stockfish not installed")
    e = Engine(levels={"Fast": Level("Fast", 0, 0.01, 1)})
    try:
        arm = RealArm(FakeRos(), my_board(), log=lambda s: None)
        arm.start()
        g = Game(Player("robot", "A", "Fast"), Player("robot", "B", "Fast"), 10, e, arm)
        asks, moves = [], []
        arm.ask = asks.append                     # only promotions should need a person

        def on_event(kind, data):
            if kind == "moved":
                moves.append(data["san"])
                if len(moves) >= 30:
                    g.stop()
        g._on_event = on_event
        g.run()
    finally:
        e.close()
    assert len(moves) >= 30 or g.result != "*"
    assert all(a.startswith("Please put a") for a in asks), asks

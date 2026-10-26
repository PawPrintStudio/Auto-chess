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
            if fingertip(self.q)[2] < H - 100:      # up high (start() learning the empty close): nothing there
                return GRIPPER_CLOSED
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
    assert ros.closes == 3                             # the empty test close, then two pieces
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


def test_every_game_starts_by_going_home():
    import shutil
    from autochess.engine import Engine, Level
    from autochess.game import Game, Player
    from autochess.kinematics import PARK
    if not shutil.which("stockfish"):
        pytest.skip("Stockfish not installed")
    e = Engine(levels={"Fast": Level("Fast", 0, 0.01, 1)})
    try:
        ros = FakeRos()
        ros.q = (1.40, -0.22, -1.27, -1.10)           # left bent, as seen on the real arm
        arm = RealArm(ros, my_board(), log=lambda s: None)
        g = Game(Player("robot", "A", "Fast"), Player("robot", "B", "Fast"), 10, e, arm)
        events = []

        def on_event(kind, data):
            events.append((kind, ros.q))
            if kind == "turn":
                g.stop()
        g._on_event = on_event
        g.run()
    finally:
        e.close()
    assert events[0][0] == "preparing"
    kind, q_at_first_turn = events[1]
    assert kind == "turn" and q_at_first_turn[1:] == pytest.approx(PARK)


def test_game_does_not_start_if_the_arm_cannot_get_home():
    from autochess.game import Game, Player
    ros = FakeRos()
    ros.q = (0.0, 0.0, -1.9, 0.0)                     # slumped past the elbow limit
    g = Game(Player("robot", "A", "Fast"), Player("robot", "B", "Fast"), 10, None,
             RealArm(ros, my_board(), log=lambda s: None))
    g.run()
    assert g.result == "*" and "home pose" in g.reason and g.board.move_stack == []


def test_crossing_behind_the_arm_swings_round_and_stays_level():
    from autochess.kinematics import joints_xyz
    from autochess.motion import Mover, Unsafe
    ros = FakeRos()
    ros.q = ik((-230.0, -8.0, 320.0))          # just short of the line straight behind the arm
    m = Mover(ros)
    m.refresh()
    with pytest.raises(Unsafe):
        m.line_to((-230.0, 5.0, 320.0))         # a small step can't cross it...
    m.go_to((-230.0, 5.0, 320.0), floor=330.0)   # ...so it swings round the long way
    assert m.q[0] > 3.0 and m.where() == pytest.approx((-230.0, 5.0, 320.0), abs=0.5)
    assert max(p[1] for p in joints_xyz(m.q[1:])) <= 330.0


def test_calibration_saves_and_loads(tmp_path):
    b = my_board()
    b.travel = 125.0
    b.grip[chess.PAWN] = 24.0
    path = tmp_path / "board.json"
    b.save(path)
    c = Board.load(path)
    assert c.square(chess.E4, 10) == pytest.approx(b.square(chess.E4, 10))
    assert c.drop == pytest.approx(b.drop) and c.travel == 125.0
    assert c.grip[chess.PAWN] == 24.0 and c.grip[chess.KING] == b.grip[chess.KING]


@pytest.mark.parametrize("drop", [(-284.26, 3.61, 328.95), (-215.0, -39.0, 330.0)])   # the real bin; a closer one
def test_tilted_low_board_like_the_real_one(drop):
    # The real calibration: the board ~39-40 cm below the plate, the a8 side 15 mm lower, 42 mm squares,
    # and the grip settings tuned on the real pieces.
    b = Board([145.95, -170.75, 391.12], [-148.63, -186.99, 388.08], [131.64, 125.02, 405.43], drop,
              travel=125.0, grip={"p": 8, "r": 11, "n": 14, "b": 18, "q": 24, "k": 28})
    assert b.height_above(b.square(chess.E7, 30)) == pytest.approx(30)
    assert b.over_board(b.square(chess.H8)) and not b.over_board(b.drop)
    arm = RealArm(FakeRos(), b, log=lambda s: None)
    arm.ask = pytest.fail                         # nothing here should need a person
    arm.start()
    board = chess.Board()
    # The test opening (both bishops, both knights, castling, the queen), then three captures.
    for uci in "e2e4 e7e5 g1f3 b8c6 f1c4 f8c5 e1g1 g8f6 d1e2 f6e4 e2e4 d7d5 c4d5 d8d5".split():
        m = chess.Move.from_uci(uci)
        arm.play(board, m)
        board.push(m)


def test_calibration_progress_survives_a_stop(tmp_path, monkeypatch):
    import autochess.calibrate as cal
    monkeypatch.setattr(cal, "PROGRESS_FILE", tmp_path / "calibration_progress.json")
    assert cal.load_progress() == {}
    cal.save_progress({"a1": np.array([1.0, 2.0, 3.0]), "h1": np.array([4.0, 5.0, 6.0])})
    done = cal.load_progress()
    assert list(done) == ["a1", "h1"] and done["h1"] == pytest.approx([4.0, 5.0, 6.0])

import chess
import numpy as np
import pytest

from autochess.geometry import GRIPPER_CLOSED, Board
from autochess.kinematics import HANGING, fingertip, ik
from autochess.robot_arm import RealArm, describe, plan_steps

H, SQ = 480.0, 38.0                # the arm hangs 480 mm above the board: 430 + 50 for the 40 mm fingertip extensions
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
    # The real calibration (made with the stock fingers): the board ~39-40 cm below the plate, the a8 side
    # 15 mm lower, 42 mm squares, and the grip settings tuned on the real pieces. The 40 mm fingertip
    # extensions need the arm raised 5 cm: everything 50 mm further below it (calibrate --raised 50).
    b = Board([145.95, -170.75, 441.12], [-148.63, -186.99, 438.08], [131.64, 125.02, 455.43],
              (drop[0], drop[1], drop[2] + 50), travel=125.0, grip={"p": 8, "r": 11, "n": 14, "b": 18, "q": 24, "k": 28})
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


def test_letting_go_opens_wider_than_the_piece_and_retries_if_stuck():
    from autochess.geometry import GRIPPER_FULL_OPEN, RELEASE

    class StickyRos(FakeRos):
        def __init__(self):
            super().__init__()
            self.opens = []

        def gripper(self, position, effort=100.0):
            if position == GRIPPER_CLOSED:
                return super().gripper(position, effort)
            self.opens.append(position)
            # the first release sticks (fingers stay on the knight), the next one works
            if len(self.opens) == 3:
                return 0.004
            return position

    ros = StickyRos()
    arm = RealArm(ros, my_board(), log=lambda s: None)
    arm.ask = pytest.fail
    arm.start()
    arm.play(chess.Board(), chess.Move.from_uci("g1f3"))
    # opens: start(), part-open before grabbing, then the release (wider than where it gripped: 0.004 + RELEASE)
    assert ros.opens[2] == pytest.approx(0.004 + RELEASE)
    assert ros.opens[3] == GRIPPER_FULL_OPEN          # it stuck, so it opened all the way
    assert not arm.holding


def test_arm_that_stalls_short_never_closes_or_opens_the_gripper_there(monkeypatch):
    class StallRos(FakeRos):
        """Any move down onto the board leaves the elbow 0.2 rad (11°) short, as if against its limit."""
        def move_path(self, points, times):
            super().move_path(points, times)
            if fingertip(self.q)[2] > H - 60:
                self.q = (self.q[0], self.q[1], self.q[2] + 0.2, self.q[3])
            return True

    ros = StallRos()
    asked = []
    logs = []
    arm = RealArm(ros, my_board(), log=logs.append)
    arm.ask = asked.append
    arm.start()
    monkeypatch.setattr("autochess.motion.ARRIVE_TIMEOUT", 0.0)     # don't sit waiting in the test
    arm.play(chess.Board(), chess.Move.from_uci("g1f3"))
    assert ros.closes == 1                                   # only start()'s empty close: it never grabbed
    assert asked and asked[0].startswith("I couldn't finish my move. Please move the knight from g1 to f3")
    assert any("stopped short" in m and "elbow" in m for m in logs), logs


def test_arrive_waits_for_the_joints_to_settle():
    from autochess.motion import Mover, Unsafe

    class Settling(FakeRos):
        def __init__(self):
            super().__init__()
            self.reads = 0

        def angles(self):
            self.reads += 1
            q = self.q
            return q if self.reads > 3 else (q[0], q[1], q[2] + 0.2, q[3])      # off for the first reads

    ros = Settling()
    m = Mover(ros)
    m.refresh()
    m.q = (0.0, *HANGING)
    ros.reads = 0
    m.arrive(timeout=2.0)                                    # settles on the 4th read
    assert ros.reads == 4
    ros.reads = -10 ** 6
    with pytest.raises(Unsafe, match="elbow"):
        m.arrive(timeout=0.1)


def test_each_piece_has_its_own_grip_strength(tmp_path):
    efforts = []

    class Ros(FakeRos):
        def gripper(self, position, effort=100.0):
            if position == GRIPPER_CLOSED:
                efforts.append(effort)
            return super().gripper(position, effort)

    geo = my_board()
    geo.effort[chess.KNIGHT] = 80.0
    arm = RealArm(Ros(), geo, log=lambda s: None)
    arm.ask = pytest.fail
    arm.start()
    arm.play(chess.Board(), chess.Move.from_uci("g1f3"))
    assert efforts[-1] == 80.0 and efforts[0] == 60.0         # the knight squeezes at 80; the empty test close at the default
    geo.save(tmp_path / "board.json")
    back = Board.load(tmp_path / "board.json")
    assert back.effort[chess.KNIGHT] == 80.0 and back.effort[chess.PAWN] == 60.0


def test_arm_knows_which_moves_it_can_play():
    geo = my_board()
    arm = RealArm(FakeRos(), geo, log=lambda s: None)
    capture = chess.Board("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1")
    assert arm.can_play(capture, chess.Move.from_uci("e4d5"))
    geo.drop = np.array([0.0, -900.0, H - 90])               # a bin far out of reach
    arm = RealArm(FakeRos(), geo, log=lambda s: None)
    assert not arm.can_play(capture, chess.Move.from_uci("e4d5"))
    assert arm.can_play(capture, chess.Move.from_uci("e4e5"))


def test_engine_falls_back_to_a_move_the_arm_can_play():
    import chess.engine
    from autochess.engine import Engine, Level

    board = chess.Board()
    first, second, third = (chess.Move.from_uci(m) for m in ("e2e4", "d2d4", "g1f3"))

    class FakeStockfish:
        def configure(self, options):
            pass

        def play(self, b, limit):
            return chess.engine.PlayResult(first, None)

        def analyse(self, b, limit, multipv):
            return [{"pv": [m]} for m in (first, second, third)]

    e = Engine.__new__(Engine)
    e.levels, e._sf = {"L": Level("L", 0, 0.01, 1)}, FakeStockfish()
    import threading
    e._lock = threading.Lock()
    assert e.choose(board, "L") == first                                      # nothing to check: the engine's pick
    assert e.choose(board, "L", playable=lambda m: m == first) == first       # playable: kept
    assert e.choose(board, "L", playable=lambda m: m == third) == third       # skips the unplayable ones
    assert e.choose(board, "L", playable=lambda m: False) == first            # none playable: the arm will ask


def test_grips_follow_the_pieces_heights_but_never_exceed_what_carrying_allows():
    from autochess.grips import plan_grips

    b = my_board()
    b.travel = 170.0                                   # room to carry a piece hanging 75 mm below the fingertips
    grips = {p: g for p, (g, _) in plan_grips(b, 14).items()}
    assert grips == {chess.PAWN: 26, chess.ROOK: 29, chess.KNIGHT: 37, chess.BISHOP: 46, chess.QUEEN: 58, chess.KING: 66}
    b.travel = 136.0                                   # only 41 mm may hang below: the tall pieces are lowered to fit
    grips = {p: g for p, (g, _) in plan_grips(b, 14).items()}
    assert grips[chess.PAWN] == 26 and grips[chess.KNIGHT] == 37
    assert grips[chess.BISHOP] == grips[chess.QUEEN] == grips[chess.KING] == 41


def test_carrying_height_follows_the_highest_grip():
    from autochess.calibrate import carry_height, carry_wanted

    b = my_board()
    assert b.needed_carry() == 80 + 15 + b.grip[chess.KING]
    assert carry_wanted(b) == 145.0                    # stock grip heights: the old target
    b.grip[chess.KING] = 66.0
    assert b.needed_carry() == 161 and carry_wanted(b) == 166.0
    assert carry_height(b) == pytest.approx(166.0)      # the test board (arm 480 mm up) reaches every square there


def test_visit_stops_above_each_square_at_the_height_and_ends_parked():
    from autochess.visit import describe_corners, visit

    ros = FakeRos()
    geo = my_board()
    arm = RealArm(ros, geo, log=lambda s: None)
    stops, logs = [], []

    def wait(text):
        stops.append((H - fingertip(ros.q)[2], text))

    visit(arm, [chess.E2, chess.A1, chess.H8], 40.0, wait=wait, log=logs.append)
    assert [round(h) for h, _ in stops] == [40, 40, 40]
    assert "e2" in stops[0][1] and "a1" in stops[1][1]
    assert np.allclose(fingertip(ros.q)[:2], (0, 0), atol=200) and not arm.holding
    assert len(logs) == 3 and "over e2" in logs[0]
    assert "a1: base angle" in describe_corners(geo) and "files run from" in describe_corners(geo)

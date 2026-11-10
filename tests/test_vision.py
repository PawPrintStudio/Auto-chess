import random

import chess
import numpy as np
import pytest

from autochess.geometry import Board
from autochess.vision import markers
from autochess.vision.camera import ImageCamera
from autochess.vision.eyes import CameraEyes, VisionError
from autochess.vision.reading import (OccupancyModel, expected_labels, interpret, rectify, square_features)
from autochess.vision.tracking import (CORNER_NAMES, BoardTracker, CameraCal, NotTracked, rigid_shift)
from tests import vision_sim as sim


def make_geo():
    """The arm's idea of the board: the sim's world is the arm's frame, 400 mm below the plate."""
    return Board(a1=(-140, -140, 400), h1=(140, -140, 400), a8=(-140, 140, 400), h8=(140, 140, 400),
                 drop=(0, -300, 400))


def make_cal():
    """The camera calibration as the user would make it: markers seen, then four clicks on square centres."""
    found = markers.detect(sim.render(None, seed=99))
    assert sorted(found) == [0, 1, 2, 3]
    clicks = sim.world_to_frame(sim.truth_corners())
    return CameraCal(found, {n: p + np.random.default_rng(4).normal(0, 0.4, 2) for n, p in zip(CORNER_NAMES, clicks)})


def features(tracker, frame):
    return square_features(rectify(frame, tracker.view(frame).b2p))


def test_all_four_markers_are_found():
    found = markers.detect(sim.render(chess.Board()))
    assert sorted(found) == [0, 1, 2, 3]
    assert markers.detect(sim.render(chess.Board(), marker_ids=(0,))).keys() == {0}


def test_the_printable_sheet_has_markers_the_camera_can_read():
    sheet = markers.printable_sheet()
    assert sheet.shape == (3300, 2550)
    top = sheet[: sheet.shape[0] // 2]
    assert sorted(markers.detect(top)) == [0, 1, 2, 3]


def test_the_board_is_found_again_after_it_moves():
    geo, tracker = make_geo(), BoardTracker(make_cal(), make_geo())
    tracker.geo = geo
    frame = sim.render(chess.Board(), deg=3.0, shift=(12.0, -7.0), seed=5)
    report = tracker.update_geo(tracker.view(frame))
    assert report.applied and report.ids == [0, 1, 2, 3]
    assert report.shift_mm == pytest.approx(np.hypot(12, 7), abs=0.5)
    assert report.turn_deg == pytest.approx(3.0, abs=0.2)
    for name, truth in zip(CORNER_NAMES, sim.truth_corners(3.0, (12.0, -7.0))):
        assert getattr(geo, name)[:2] == pytest.approx(truth, abs=0.7), name     # well under a millimetre
        assert getattr(geo, name)[2] == pytest.approx(400.0, abs=0.5)


def test_the_board_is_found_with_one_marker_hidden():
    tracker = BoardTracker(make_cal(), make_geo())
    frame = sim.render(chess.Board(), deg=-2.0, shift=(-9.0, 6.0), marker_ids=(0, 1, 3))
    view = tracker.view(frame)
    assert view.ids == [0, 1, 3]
    for name, truth in zip(CORNER_NAMES, sim.truth_corners(-2.0, (-9.0, 6.0))):
        assert tracker.new_corners(view)[name][:2] == pytest.approx(truth, abs=2.0)   # a little worse with three


def test_too_few_markers_is_refused():
    tracker = BoardTracker(make_cal(), make_geo())
    with pytest.raises(NotTracked):
        tracker.view(sim.render(chess.Board(), marker_ids=(0, 1)))      # two on the same side: can't tell
    tracker.view(sim.render(chess.Board(), marker_ids=(0, 3)))          # opposite corners: enough


def test_a_big_move_is_not_applied_without_asking():
    geo = make_geo()
    tracker = BoardTracker(make_cal(), geo)
    before = geo.a1.copy()
    report = tracker.update_geo(tracker.view(sim.render(chess.Board(), shift=(50.0, 0.0))))
    assert not report.applied and "more than I'll adjust" in report.message
    assert np.allclose(geo.a1, before)
    assert tracker.update_geo(tracker.view(sim.render(chess.Board(), shift=(50.0, 0.0))), force=True).applied


def test_rigid_shift():
    ref = np.array([[0, 0], [280, 0], [0, 280], [280, 280]], float)
    a = np.radians(5)
    new = ref @ np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]]).T + [10, 20]
    shift, turn = rigid_shift(ref, new)
    assert turn == pytest.approx(5.0, abs=1e-6)
    assert shift == pytest.approx(np.linalg.norm(new.mean(axis=0) - ref.mean(axis=0)))


def test_the_camera_calibration_is_saved_and_loaded(tmp_path):
    cal = make_cal()
    path = tmp_path / "camera.json"
    cal.save(path)
    cal.save(path)                                     # the old one is kept
    assert len(list((tmp_path / "backups").glob("camera-*.json"))) == 1
    again = CameraCal.load(path)
    assert sorted(again.markers) == [0, 1, 2, 3]
    assert again.board_to_pixel() == pytest.approx(cal.board_to_pixel())


def test_colours_are_learned_from_the_start_position():
    tracker = BoardTracker(make_cal())
    feats = features(tracker, sim.render(chess.Board(), seed=1))
    model = OccupancyModel.learn(feats)
    assert (model.classify(feats) == expected_labels(chess.Board())).all()
    # a different game position, a different lighting: still read correctly
    b = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
    seen = model.classify(features(tracker, sim.render(b, seed=2, brightness=1.08)))
    assert (seen == expected_labels(b)).all()


def test_reads_every_kind_of_move():
    tracker = BoardTracker(make_cal())
    model = OccupancyModel.learn(features(tracker, sim.render(chess.Board(), seed=1)))
    cases = [
        ("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2", "e4d5"),                  # capture
        ("r3k2r/pppq1ppp/2npbn2/2b1p3/2B1P3/2NPBN2/PPPQ1PPP/R3K2R w KQkq - 0 1", "e1g1"),           # castles short
        ("r3k2r/pppq1ppp/2npbn2/2b1p3/2B1P3/2NPBN2/PPPQ1PPP/R3K2R w KQkq - 0 1", "e1c1"),           # castles long
        ("r3k2r/pppq1ppp/2npbn2/2b1p3/2B1P3/2NPBN2/PPPQ1PPP/R3K2R b KQkq - 0 1", "e8g8"),           # black castles
        ("rnbqkbnr/ppp1pppp/8/8/3pP3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 3", "d4e3"),                    # en passant
        ("8/P6k/8/8/8/8/8/K7 w - - 0 1", "a7a8q"),                                                   # promotes
        ("8/P6k/8/8/8/8/8/K7 w - - 0 1", "a7a8n"),                                                   # under-promotion: read as a queen
        ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "g1f3"),                       # plain move
    ]
    for fen, uci in cases:
        board, move = chess.Board(fen), chess.Move.from_uci(uci)
        after = board.copy()
        after.push(move)
        reading = interpret(board, features(tracker, sim.render(after, seed=11, brightness=1.05)),
                            features(tracker, sim.render(board, seed=10)), model)
        want = chess.Move(move.from_square, move.to_square, chess.QUEEN if move.promotion else None)
        assert reading.move == want, (fen, uci, reading)


def test_reads_a_whole_random_game():
    tracker = BoardTracker(make_cal())
    model = OccupancyModel.learn(features(tracker, sim.render(chess.Board(), seed=1)))
    rng, board, wrong, plies = random.Random(3), chess.Board(), [], 0
    before = features(tracker, sim.render(board, seed=0))
    while plies < 70 and not board.is_game_over():
        move = rng.choice([m for m in board.legal_moves if not m.promotion or m.promotion == chess.QUEEN])
        after = board.copy()
        after.push(move)
        feats = features(tracker, sim.render(after, seed=plies + 1, brightness=1.0 + 0.02 * (plies % 5)))
        reading = interpret(board, feats, before, model)
        if reading.move != move:
            wrong.append((plies, board.san(move), reading.why or reading.move))
        board, before, plies = after, feats, plies + 1
    assert not wrong, wrong


def test_a_hand_over_the_board_is_never_read_as_a_wrong_move():
    tracker = BoardTracker(make_cal())
    model = OccupancyModel.learn(features(tracker, sim.render(chess.Board(), seed=1)))
    board = chess.Board()
    after = board.copy()
    after.push_uci("e2e4")
    before = features(tracker, sim.render(board, seed=3))
    # a hand (coloured much like wood, so it hides pieces and squares alike) over the middle, over the pieces,
    # over the move itself: whatever it hides, the answer is "no move", never a different move
    for hand in [(960, 540), (960, 900), (1000, 640), (700, 300)]:
        reading = interpret(board, features(tracker, sim.render(after, seed=2, hand=hand)), before, model)
        assert reading.move in (None, chess.Move.from_uci("e2e4")), (hand, reading)
    nothing = interpret(board, features(tracker, sim.render(board, seed=4)), before, model)
    assert nothing.move is None and "no move seen" in nothing.why


def test_eyes_wait_for_the_hand_to_leave_then_read_the_move():
    cal, geo = make_cal(), make_geo()
    board = chess.Board()
    after = board.copy()
    after.push_uci("g1f3")
    frames = [sim.render(board, seed=1)] * 3 + [sim.render(after, seed=5, hand=(900, 500))] * 2 + [
        sim.render(after, seed=6, brightness=1.03)]
    eyes = CameraEyes(ImageCamera(frames), cal, geo, log=lambda s: None)
    eyes.begin_game(board)                                  # track + learn: two pictures
    assert eyes.begin_turn(board) == []                     # the third
    move = eyes.read_move(board, timeout=5.0, poll=0.01)
    assert move == chess.Move.from_uci("g1f3")


def test_eyes_say_which_squares_look_wrong_and_refuse_a_bad_start():
    cal = make_cal()
    board = chess.Board()
    start = sim.render(board, seed=1)
    eyes = CameraEyes(ImageCamera([start, start, start]), cal, make_geo(), log=lambda s: None)
    eyes.begin_game(board)
    # the robot's last move left d5 as it should be, but a knight is missing from g8
    wrong = chess.Board()
    wrong.remove_piece_at(chess.G8)
    eyes.camera = ImageCamera([sim.render(wrong, seed=2)])
    assert eyes.begin_turn(board) == ["g8"]
    # a start with half the pieces missing can't be used
    half = chess.Board()
    for sq in (chess.A2, chess.B2, chess.C2, chess.D2, chess.A7, chess.B7):
        half.remove_piece_at(sq)
    eyes2 = CameraEyes(ImageCamera([sim.render(half, seed=3)]), cal, make_geo(), log=lambda s: None)
    with pytest.raises(VisionError, match="starting position"):
        eyes2.begin_game(board)
    with pytest.raises(VisionError, match="at least three"):
        CameraEyes(ImageCamera([sim.render(board, marker_ids=(0, 1))]), cal, make_geo(),
                   log=lambda s: None).begin_game(board)


def test_a_whole_game_with_the_camera_as_the_eyes():
    """The human's moves come from the camera: a pretend arm plays the robot's, and a sim camera looks at
    whatever the 'physical' board holds. Includes a robot move the arm 'fumbles' (one piece left misplaced)."""
    import queue
    import shutil

    from autochess.engine import Engine, Level
    from autochess.game import Game, Player
    from autochess.pretend import PretendArm
    if not shutil.which("stockfish"):
        pytest.skip("Stockfish not installed")
    physical = chess.Board()                                   # what is really on the table
    n = [0]

    def picture():
        n[0] += 1
        return sim.render(physical, seed=n[0])

    class Arm(PretendArm):
        def play(self, board, move):
            physical.push(move)                                # the arm moves the real piece

    engine = Engine(levels={"Fast": Level("Fast", 0, 0.01, 1)})
    events = queue.Queue()
    try:
        eyes = CameraEyes(ImageCamera(picture), make_cal(), make_geo(), log=lambda s: None)
        game = Game(Player("human", "Ana"), Player("robot", "Robo", "Fast"), 10, engine, Arm(0, lambda s: None), eyes,
                    on_event=lambda kind, data: events.put((kind, data)))
        game.start()
        seen = []
        for san in ("e2e4", "g1f3", "f1c4"):                   # the human's three moves, read by the camera
            while True:
                kind, data = events.get(timeout=20)
                seen.append(kind)
                if kind == "turn" and data["player"].kind == "human":
                    break
            physical.push(chess.Move.from_uci(san))            # the human moves a piece...
            game.press_done()                                  # ...and presses Done
            while True:
                kind, data = events.get(timeout=20)
                seen.append(kind)
                if kind == "moved" and data["side"] == chess.WHITE:
                    assert data["move"] == chess.Move.from_uci(san)
                    break
        game.stop()
        game.join(10)
    finally:
        engine.close()
    assert seen[0] == "looking" and "reading" in seen and "warning" not in seen
    assert game.board.move_stack[0::2] == [chess.Move.from_uci(m) for m in ("e2e4", "g1f3", "f1c4")]


def test_the_camera_tools_work_end_to_end(tmp_path, monkeypatch, capsys):
    """make_markers -> calibrate_camera (--points) -> snap -> try_read, all on synthetic pictures."""
    import builtins

    import cv2

    import autochess.vision.calibrate_camera as calibrate_camera
    import autochess.vision.make_markers as make_markers
    import autochess.vision.snap as snap
    import autochess.vision.tracking as tracking
    import autochess.vision.try_read as try_read

    sheet = tmp_path / "markers.png"
    monkeypatch.setattr("sys.argv", ["make_markers", "--out", str(sheet)])
    make_markers.main()
    assert sorted(markers.detect(cv2.imread(str(sheet))[: 3300 // 2])) == [0, 1, 2, 3]    # the printable page is readable

    monkeypatch.setattr(tracking, "CAMERA_FILE", tmp_path / "camera.json")
    monkeypatch.setattr(calibrate_camera, "CameraCal", tracking.CameraCal)
    picture = tmp_path / "empty.jpg"
    cv2.imwrite(str(picture), sim.render(None, seed=7))
    clicks = " ".join(f"{x:.1f},{y:.1f}" for x, y in sim.world_to_frame(sim.truth_corners()))
    monkeypatch.setattr("sys.argv", ["calibrate_camera", "--image", str(picture), "--points", clicks])
    calibrate_camera.main()
    cal = tracking.CameraCal.load(tmp_path / "camera.json")
    assert sorted(cal.markers) == [0, 1, 2, 3]

    out = tmp_path / "snap.jpg"
    monkeypatch.setattr(snap.CameraCal, "load", classmethod(lambda cls, path=None: cal))
    monkeypatch.setattr("sys.argv", ["snap", "--image", str(picture), "--out", str(out)])
    snap.main()
    assert out.exists() and "Markers found: [0, 1, 2, 3]" in capsys.readouterr().out

    physical = chess.Board()
    seed = [100]

    def picture_now():
        seed[0] += 1
        return sim.render(physical, seed=seed[0])
    monkeypatch.setattr(try_read, "Camera", lambda device=0: ImageCamera(picture_now))
    monkeypatch.setattr(try_read.CameraCal, "load", classmethod(lambda cls, path=None: cal))
    actions = iter([lambda: None, lambda: physical.push_uci("e2e4"), lambda: physical.push_uci("c7c5"),
                    lambda: physical.push_uci("g1f3"), "q"])

    def fake_input(prompt=""):
        act = next(actions)
        if act == "q":
            return "q"
        act()
        return ""
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr("sys.argv", ["try_read"])
    try_read.main()
    said = capsys.readouterr().out
    assert "I saw e4" in said and "I saw c5" in said and "I saw Nf3" in said

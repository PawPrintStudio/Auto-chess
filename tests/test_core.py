import queue
import shutil

import chess
import pytest

from autochess.clock import ChessClock, fmt
from autochess.engine import LEVEL_NAMES, Engine, Level
from autochess.game import Game, Player
from autochess.pretend import PretendArm, ScriptedEyes

needs_stockfish = pytest.mark.skipif(not shutil.which("stockfish"), reason="Stockfish not installed")
FAST = {"Fast": Level("Fast", skill=0, think=0.01, depth=1)}


class FakeTime:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_clock_runs_one_side_at_a_time():
    t = FakeTime()
    c = ChessClock(10, now=t)
    c.run(chess.WHITE)
    t.t = 5
    c.run(chess.BLACK)
    t.t = 7
    c.pause()
    t.t = 100            # paused: nothing counts
    assert c.left(chess.WHITE) == 595
    assert c.left(chess.BLACK) == 598
    assert fmt(c.left(chess.WHITE)) == "9:55"


def test_clock_refuses_short_games():
    with pytest.raises(ValueError):
        ChessClock(5)


def test_clock_flag():
    t = FakeTime()
    c = ChessClock(10, now=t)
    c.run(chess.WHITE)
    t.t = 601
    assert c.flagged(chess.WHITE) and not c.flagged(chess.BLACK)


@needs_stockfish
def test_every_level_plays_a_legal_move():
    e = Engine()
    try:
        board = chess.Board()
        for name in LEVEL_NAMES:
            assert e.choose(board, name, max_think=0.05) in board.legal_moves
    finally:
        e.close()


@pytest.fixture
def fast_engine():
    if not shutil.which("stockfish"):
        pytest.skip("Stockfish not installed")
    e = Engine(levels=FAST)
    yield e
    e.close()


def run_with_events(game):
    events = queue.Queue()
    game._on_event = lambda kind, data: events.put((kind, data))
    game.start()
    return events


def wait_for(events, kind, timeout=10):
    while True:
        k, data = events.get(timeout=timeout)
        if k == kind:
            return data


def test_robot_plays_itself_to_the_end(fast_engine):
    arm = PretendArm(seconds=0, log=lambda s: None)
    g = Game(Player("robot", "Robo A", "Fast"), Player("robot", "Robo B", "Fast"), 10, fast_engine, arm)
    g.run()
    assert g.result in ("1-0", "0-1", "1/2-1/2")
    assert g.board.is_game_over(claim_draw=True)


def test_human_move_after_done_and_bad_move_retry(fast_engine):
    eyes = ScriptedEyes([None, chess.Move.from_uci("e2e4")])
    g = Game(Player("human", "Ana"), Player("robot", "Robo", "Fast"), 10, fast_engine,
             PretendArm(0, lambda s: None), eyes)
    ev = run_with_events(g)
    wait_for(ev, "turn")
    g.press_done()
    wait_for(ev, "bad_move")                     # nothing legal seen: try again
    g.press_done()
    assert wait_for(ev, "moved")["san"] == "e4"
    wait_for(ev, "moved")                        # the robot's reply
    g.resign(chess.WHITE)
    over = wait_for(ev, "game_over")
    assert over["result"] == "0-1" and "resigned" in over["reason"]


def test_human_runs_out_of_time(fast_engine):
    t = FakeTime()
    g = Game(Player("human", "Ana"), Player("robot", "Robo", "Fast"), 10, fast_engine,
             PretendArm(0, lambda s: None), ScriptedEyes([]), now=t)
    ev = run_with_events(g)
    wait_for(ev, "turn")
    t.t = 10 * 60 + 1
    over = wait_for(ev, "game_over")
    assert over["result"] == "0-1" and "time" in over["reason"]


def test_stop_ends_without_result(fast_engine):
    g = Game(Player("human", "Ana"), Player("robot", "Robo", "Fast"), 10, fast_engine,
             PretendArm(0, lambda s: None), ScriptedEyes([]))
    ev = run_with_events(g)
    wait_for(ev, "turn")
    g.stop()
    assert wait_for(ev, "game_over")["result"] == "*"

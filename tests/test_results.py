import json

from autochess import results


def rec(white, wk, wl, black, bk, bl, result):
    return {"white": white, "white_kind": wk, "white_level": wl,
            "black": black, "black_kind": bk, "black_level": bl, "result": result}


def test_leaderboard_counts_human_wins_per_level():
    records = [
        rec("Ana", "human", None, "Robo", "robot", "Easy", "1-0"),
        rec("Robo", "robot", "Easy", "ana ", "human", None, "0-1"),     # same person, other colour
        rec("Ben", "human", None, "Robo", "robot", "Easy", "1-0"),
        rec("Ben", "human", None, "Robo", "robot", "Hard", "0-1"),      # a loss: not counted
        rec("Cy", "human", None, "Robo", "robot", "Hard", "1/2-1/2"),   # a draw: not counted
        rec("Robo A", "robot", "Hard", "Robo B", "robot", "Easy", "1-0"),  # robot vs robot: not counted
    ]
    board = results.leaderboard(records)
    assert board == {"Easy": [("Ana", 2), ("Ben", 1)]}


def test_load_skips_broken_lines(tmp_path):
    p = tmp_path / "results.jsonl"
    p.write_text(json.dumps({"result": "1-0"}) + "\n{broken\n")
    assert results.load(p) == [{"result": "1-0"}]

"""Saved games (one JSON line each in data/results.jsonl) and the leaderboard."""
import json
import time
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "data" / "results.jsonl"


def save(game, path=None):
    import chess
    path = path or RESULTS
    w, b = game.players[chess.WHITE], game.players[chess.BLACK]
    record = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "white": w.name, "white_kind": w.kind, "white_level": w.level,
        "black": b.name, "black_kind": b.kind, "black_level": b.level,
        "minutes": game.minutes,
        "result": game.result, "reason": game.reason,
        "moves": [m.uci() for m in game.board.move_stack],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def load(path=None):
    path = path or RESULTS
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass    # a half-written line from a crash
    return records


def leaderboard(records, top=5):
    """{level: [(name, wins), ...]}: humans who beat the robot, most wins first."""
    wins = {}       # level -> {lowercase name: [display name, wins]}
    for r in records:
        for me, them, won in (("white", "black", "1-0"), ("black", "white", "0-1")):
            if r.get(f"{me}_kind") == "human" and r.get(f"{them}_kind") == "robot" and r.get("result") == won:
                name = r[me].strip()
                entry = wins.setdefault(r[f"{them}_level"], {}).setdefault(name.lower(), [name, 0])
                entry[1] += 1
    return {level: sorted((tuple(e) for e in names.values()), key=lambda e: (-e[1], e[0].lower()))[:top]
            for level, names in wins.items()}

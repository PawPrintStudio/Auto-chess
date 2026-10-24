"""Fold the hanging arm up into its park pose, clear of the pieces:  python3 -m autochess.park

Checks first that the arm reports sensible angles and that the whole move stays clear of the
mount plate and never goes lower than where the arm already is, then asks before moving.
"""
import argparse
import itertools
import sys

import numpy as np

from .kinematics import LIMITS, PARK, START_SLACK, clear_of_mount, lowest, within_limits

SPEED = 0.3          # rad/s for the joint that moves furthest: slow on purpose
MIN_SECONDS = 6.0    # for a move of all joints together
JOINT_NAMES = ["shoulder", "elbow", "wrist"]


def _worst(path):
    """Deepest point (mm below the plate) along a path of (shoulder, elbow, wrist), or None if any
    part of it comes too close to the mount."""
    worst = 0.0
    for a, b in zip(path, path[1:]):
        for f in np.linspace(0, 1, 40):
            q = a + (b - a) * f
            if not clear_of_mount(q):
                return None
            worst = max(worst, lowest(q))
    return worst


def _fold(current, allowed):
    """Joint moves folding the arm from current into the park pose without going deeper than allowed:
    all joints together, or one joint at a time in the safest order. None if there's no such way."""
    base = float(np.clip(current[0], *LIMITS[0]))
    a, park = np.array(current[1:], float), np.array(PARK)
    routes = [[a, park]]
    for order in itertools.permutations(range(3)):
        path, q = [a], a.copy()
        for j in order:
            q = q.copy()
            q[j] = park[j]
            path.append(q)
        routes.append(path)
    for path in routes:
        worst = _worst(path)
        if worst is not None and worst <= allowed:
            moves, prev = [], np.array([current[0], *a])
            for q in path[1:]:
                q4 = np.array([base, *q])
                t = float(np.max(np.abs(q4 - prev))) / SPEED
                changed = [JOINT_NAMES[j] for j in range(3) if abs(q[j] - prev[j + 1]) > 1e-6]
                label = "all joints together" if len(changed) > 1 else f"{changed[0]} only"
                moves.append((tuple(float(x) for x in q4), max(MIN_SECONDS if len(path) == 2 else 2.0, t), label))
                prev = q4
            return moves
    return None


def _grid_ok(allowed, step):
    """For a grid of (shoulder, elbow, wrist) angles: which arm shapes are inside the limits, clear of
    the mount and no deeper than allowed. Returns (axes, ok array)."""
    axes = [np.arange(lo + 0.02, hi - 0.02 + 1e-9, step) for lo, hi in LIMITS[1:]]
    q2, q3, q4 = np.meshgrid(*axes, indexing="ij")
    ok = np.zeros(q2.shape, bool)
    for idx in np.ndindex(q2.shape):
        q = (q2[idx], q3[idx], q4[idx])
        ok[idx] = lowest(q) <= allowed and clear_of_mount(q)
    return axes, ok


def _search(current, allowed, step=0.08):
    """Search the grid of arm shapes for a chain of small moves from current to the park pose that
    never goes deeper than allowed or near the mount. Returns joint moves, or None."""
    import heapq
    axes, ok = _grid_ok(allowed, step)
    def nearest(q):
        return tuple(int(np.argmin(np.abs(ax - v))) for ax, v in zip(axes, q))
    goal = nearest(PARK)
    # Start from the nearest allowed grid shape the arm can reach directly from where it is
    # (the grid point closest to it may be a few mm too deep).
    here, c = np.array(current[1:], float), nearest(current[1:])
    start = None
    offsets = [tuple(x - 2 for x in d) for d in np.ndindex(5, 5, 5)]
    cands = [tuple(c[j] + d[j] for j in range(3)) for d in offsets]
    cands = [n for n in cands if all(0 <= n[j] < ok.shape[j] for j in range(3)) and ok[n]]
    for n in sorted(cands, key=lambda n: np.abs(np.array([axes[j][n[j]] for j in range(3)]) - here).sum()):
        worst = _worst([here, np.array([axes[j][n[j]] for j in range(3)])])
        if worst is not None and worst <= allowed:
            start = n
            break
    if start is None or not ok[goal]:
        return None
    dist, prev, heap = {start: 0.0}, {}, [(0.0, start)]
    while heap:
        d, node = heapq.heappop(heap)
        if node == goal:
            break
        if d > dist[node]:
            continue
        for j in range(3):
            for dj in (-1, 1):
                nxt = list(node)
                nxt[j] += dj
                nxt = tuple(nxt)
                if not 0 <= nxt[j] < ok.shape[j] or not ok[nxt]:
                    continue
                nd = d + 1.0
                if nd < dist.get(nxt, 1e9):
                    dist[nxt], prev[nxt] = nd, node
                    heapq.heappush(heap, (nd, nxt))
    if goal not in dist:
        return None
    cells = [goal]
    while cells[-1] != start:
        cells.append(prev[cells[-1]])
    cells.reverse()
    # Keep only the corners (where the moving joint changes), then end exactly at PARK.
    pts = [np.array([axes[j][c[j]] for j in range(3)]) for c in cells]
    corners = [pts[0]]
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        if np.argmax(np.abs(b - a)) != np.argmax(np.abs(c - b)):
            corners.append(b)
    corners += [pts[-1], np.array(PARK)]
    base = float(np.clip(current[0], *LIMITS[0]))
    moves, prev_q = [], np.array(current, float)
    for c in [np.array(current[1:])] + corners[1:]:
        q4 = np.array([base, *c])
        if np.max(np.abs(q4 - prev_q)) < 1e-9:
            continue
        moves.append((tuple(float(x) for x in q4), max(0.5, float(np.max(np.abs(q4 - prev_q))) / SPEED),
                      "step by step"))
        prev_q = q4
    path = [np.array(current[1:])] + [np.array(m[0][1:]) for m in moves]
    worst = _worst(path)
    return moves if worst is not None and worst <= allowed else None


def plan(current):
    """[(q4, seconds, label), ...]: the moves that get the arm to the park pose from the current angles,
    never closer to the mount than allowed and never lower than the arm already is. If folding
    straight from here isn't safe (e.g. the arm is stretched far out), it searches for a chain of
    small one-joint moves that is. Raises ValueError saying why not if there's no safe way."""
    if not within_limits(current, slack=START_SLACK):
        raise ValueError("the arm is past its joint limits (it may have slumped). Hold it, power it off, "
                         "let it hang straight down, then try again.")
    if np.max(np.abs(np.array(current[1:]) - np.array(PARK))) < 0.02:
        return []                                   # already there
    # 10 mm of slack: swinging out of a limp, straight-down hang dips a few mm (the upper arm's offset)
    allowed = lowest(current[1:]) + 10
    moves = _fold(current, allowed)
    if moves is not None:
        return moves
    moves = _search(current, allowed)
    if moves is not None:
        return moves
    raise ValueError("there's no way to the park pose from here that stays clear of the mount plate and "
                     "never goes lower. Hold the arm, power it off, let it hang straight down, then try again.")


def follow(arm, moves):
    """Send the moves to the arm as one smooth trajectory and wait. True if it got there."""
    if not moves:
        return True
    times = np.cumsum([s for _, s, _ in moves])
    return arm.move_path([q for q, _, _ in moves], [float(t) for t in times])


def main():
    ap = argparse.ArgumentParser(description="Fold the hanging arm into its park pose")
    ap.add_argument("--yes", action="store_true", help="don't ask before moving")
    args = ap.parse_args()

    from .ros_arm import RosArm
    arm = RosArm()
    try:
        current = arm.angles()
        if current is None:
            sys.exit("No joint angles from the arm. Is the arm bringup running? (see README)")
        print("Now:  " + "  ".join(f"{a:+.2f}" for a in current) + "   (base, shoulder, elbow, wrist, rad)")
        print("Working out a safe way home (can take a few seconds)...")
        try:
            moves = plan(current)
        except ValueError as e:
            sys.exit(f"Not moving: {e}")
        steps = []                              # group the pull-in waypoints into one line of output
        for q4, seconds, label in moves:
            if steps and steps[-1][2] == label == "step by step":
                steps[-1] = (q4, steps[-1][1] + seconds, label)
            else:
                steps.append((q4, seconds, label))
        for i, (q4, seconds, label) in enumerate(steps, 1):
            print(f"Move {i}: " + "  ".join(f"{a:+.2f}" for a in q4) + f"   ({label}, {seconds:.0f} s)")
        if not args.yes and moves:
            input("Keep a hand near the arm and the 12 V switch. Press Enter to move (Ctrl+C to cancel)... ")
        if not follow(arm, moves):
            sys.exit("The move didn't finish: check the arm and the bringup terminal.")
        print("Parked." if moves else "Already parked.")
    finally:
        arm.close()


if __name__ == "__main__":
    main()

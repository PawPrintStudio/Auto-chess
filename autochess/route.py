"""Find a safe chain of joint moves between two arm poses.

A straight joint-space move between two poses can swing the arm through the board or the pieces even
when both ends are fine, and the fall-back through the park pose can too. This searches for a chain of
small one-joint moves (the base turns first) in which every pose along the way is acceptable to a
caller-supplied test, and the arm stays clear of the mount plate and inside its joint limits.
"""
import heapq
import time

import numpy as np

from .kinematics import clear_of_mount, within_limits

STEP = np.radians(5.0)      # grid step of the search
MAX_SECONDS = 15.0          # give up after this long
SPEED = 0.35                # rad/s for the joint that moves furthest


class NoRoute(Exception):
    """No safe chain of moves was found."""


def _segment_ok(ok_pose, base, a, b, samples=8):
    if not within_limits((0.0, *b)):
        return False
    for f in np.linspace(0, 1, samples)[1:]:
        q = a + (b - a) * f
        if not (clear_of_mount(q) and ok_pose((base, *q))):
            return False
    return True


def find(q_now, q_goal, ok_pose, max_seconds=MAX_SECONDS):
    """[(q4, seconds, label)] from pose q_now to pose q_goal (each: base, shoulder, elbow, wrist), every
    pose on the way satisfying ok_pose(q4). Raises NoRoute."""
    q_now, q_goal = np.array(q_now, float), np.array(q_goal, float)
    base = float(q_goal[0])
    start, goal = q_now[1:], q_goal[1:]
    if not all(clear_of_mount(start) and ok_pose((a, *start)) for a in np.linspace(q_now[0], base, 12)):
        raise NoRoute("the base can't turn from here without the arm coming too close to the board")
    key = lambda q: tuple(np.round(q / STEP).astype(int))
    goal_key = np.array(key(goal))
    s_key = key(start)
    nodes, best, prev = {s_key: start}, {s_key: 0}, {}
    heap = [(0, s_key)]
    end, t0 = None, time.time()
    while heap and time.time() - t0 < max_seconds:
        _, k = heapq.heappop(heap)
        if np.max(np.abs(np.array(k) - goal_key)) <= 1:
            end = k
            break
        q = nodes[k]
        for j in range(3):
            for s in (-1, 1):
                n = q.copy()
                n[j] += s * STEP
                nk = key(n)
                if nk in best and best[nk] <= best[k] + 1:
                    continue
                if _segment_ok(ok_pose, base, q, n):
                    best[nk] = best[k] + 1
                    nodes[nk], prev[nk] = n, k
                    heapq.heappush(heap, (best[nk] + np.sum(np.abs(np.array(nk) - goal_key)), nk))
    if end is None:
        raise NoRoute("no way found that keeps the arm clear of the board")
    chain = [end]
    while chain[-1] != s_key:
        chain.append(prev[chain[-1]])
    pts = [nodes[k] for k in reversed(chain)] + [goal]
    corners = [pts[0]]                      # keep only the corners, where the moving joint changes
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        if not np.allclose(np.sign(np.round(b - a, 6)), np.sign(np.round(c - b, 6))):
            corners.append(b)
    corners.append(pts[-1])
    route = [np.array([q_now[0], *start]), np.array([base, *start])] + [np.array([base, *c]) for c in corners[1:]]
    for a, b in zip(route[1:], route[2:]):  # check the joint moves again, finely (the base turn was checked above)
        if not _segment_ok(ok_pose, base, a[1:], b[1:], samples=40):
            raise NoRoute("the route doesn't stay clear enough of the board")
    moves, prev_q = [], q_now
    for label, p in [("turn", route[1])] + [("move", r) for r in route[2:]]:
        moves.append((tuple(float(x) for x in p), max(0.6, float(np.max(np.abs(p - prev_q))) / SPEED), label))
        prev_q = p
    return moves

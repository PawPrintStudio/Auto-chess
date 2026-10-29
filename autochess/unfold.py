"""A safe way from the folded (home) pose to over a square with the gripper pointing down, staying high.

The arm folds up for parking with its gripper pointing sideways. Before the gripper points roughly
down, the fingertip keys of the calibration can't be used, and the joint keys can't be trusted: many
of the ways of unfolding swing the gripper through the board (or the pieces, if the arm's idea of the
board is off). This finds a route that keeps the elbow, wrist and fingertips well above the board all
the way, clear of the mount plate, and ends over the square (see route.find).
"""
import numpy as np

from .kinematics import DOWN, clear_of_mount, ik, joint_points
from .motion import Unsafe
from .route import NoRoute, find

CLEARANCE = 170.0       # mm: fingertips, wrist and elbow stay at least this far above the calibrated board (the
                        # 80 mm king plus a margin for the calibration being wrong about the board's depth)
NEAR_TARGET = 120.0     # mm: within this of the target square (sideways) the fingertips may come lower


def _high_enough(board, target, finish, clearance, q4):
    """Elbow, wrist and fingertips all `clearance` above the board where they're over it; only the
    fingertips may be lower, down to about `finish`, and only near the target square."""
    elbow, wrist, tip = joint_points(q4)
    for p in (elbow, wrist):
        if board.over_board(p, margin=60.0) and board.height_above(p) < clearance:
            return False
    if board.over_board(tip, margin=60.0):
        near = np.linalg.norm(tip[:2] - target[:2]) < NEAR_TARGET
        if board.height_above(tip) < (min(clearance, finish - 35.0) if near else clearance):
            return False
    return True


def plan(q_now, board, sq, clearance=CLEARANCE):
    """[(q4, seconds, label)]: moves from the pose q_now (base, shoulder, elbow, wrist) to over square
    `sq` with the gripper pointing down and the fingertips as high as the arm can hold them there (so
    high above the board whatever the calibration says about its depth). Raises Unsafe if there's no safe way."""
    q_now = np.array(q_now, float)
    for height in np.arange(300.0, 40.0 - 1e-6, -5.0):
        goal = ik(board.square(sq, height), near=q_now)
        if goal is not None and abs(sum(goal[1:]) - DOWN) <= np.radians(25):
            break
    else:
        raise Unsafe("can't find a pose over that square with the gripper pointing down")
    target = board.square(sq)
    try:
        return find(q_now, goal, lambda q4: _high_enough(board, target, height, clearance, q4))
    except NoRoute as e:
        raise Unsafe(str(e))

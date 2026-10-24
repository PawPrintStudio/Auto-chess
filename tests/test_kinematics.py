import numpy as np
import pytest

from autochess.kinematics import HANGING, PARK, clear_of_mount, joints_xyz, lowest, path_clear, within_limits
from autochess.park import plan



def test_home_is_an_L_and_hanging_is_straight_down():
    *_, tip = joints_xyz((0.0, 0.0, 0.0), fingers=150)
    assert tip == pytest.approx((24 + 124 + 150, 76.5 + 128))          # forearm and gripper sideways
    *_, tip = joints_xyz(HANGING, fingers=150)
    assert tip[1] == pytest.approx(76.5 + 128 + 124 + 150, abs=1)     # the whole arm straight down


@pytest.mark.parametrize("fingers", [126, 150])
def test_park_is_folded_up_and_clear(fingers):
    assert within_limits((0.0, *PARK))
    assert clear_of_mount(PARK, fingers)
    assert lowest(PARK, fingers) < 240            # ~195 mm above the board at a 430 mm mount
    assert path_clear(HANGING, PARK, fingers)
    assert path_clear((0.0, 0.0, 0.0), PARK, fingers)


def test_plan_from_hanging_straight_down():
    [(target, seconds, _)] = plan((0.3, *HANGING))   # one move, all joints together
    assert target == pytest.approx((0.3, *PARK))  # the base doesn't turn
    assert 6 <= seconds <= 10


def test_plan_from_a_bent_arm_goes_one_joint_at_a_time():
    # Seen on the real arm: moving all joints together from here would dip ~4 cm lower.
    now = (1.40, -0.22, -1.27, -1.10)
    moves = plan(now)
    assert len(moves) == 3
    assert moves[-1][0] == pytest.approx((1.40, *PARK))
    start, path = lowest(now[1:]), [np.array(now[1:])] + [np.array(q[1:]) for q, _, _ in moves]
    for a, b in zip(path, path[1:]):
        assert sum(abs(b - a) > 1e-9) == 1           # one joint per move
        assert all(lowest(a + (b - a) * f) <= start + 10 for f in np.linspace(0, 1, 30))


def test_plan_refuses_a_slumped_arm():
    with pytest.raises(ValueError, match="limits"):
        plan((0.0, 0.0, -1.8, 0.0))


def test_folding_into_the_plate_is_caught():
    assert not clear_of_mount((-1.5, 1.4, 1.9))   # wrist curled back up into the base


@pytest.mark.parametrize("tip", [(-230.0, -15.0, 320.0), (-230.0, 5.0, 320.0), (200.0, 90.0, 330.0)])
def test_plan_from_stretched_far_out_finds_a_way(tip):
    # Seen on the real arm: quitting calibration with the arm stretched 23 cm out behind it.
    from autochess.kinematics import fingertip, ik
    now = ik(tip)
    moves = plan(now)
    assert moves[-1][0][1:] == pytest.approx(PARK)
    start = lowest(now[1:])
    qs = [np.array(now)] + [np.array(q) for q, _, _ in moves]
    for a, b in zip(qs, qs[1:]):
        assert all(lowest((a + (b - a) * f)[1:]) <= start + 10 for f in np.linspace(0, 1, 20))

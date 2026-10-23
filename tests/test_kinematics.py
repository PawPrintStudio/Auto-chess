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
    target, seconds = plan((0.3, *HANGING))
    assert target == (0.3, *PARK)                 # the base doesn't turn
    assert 6 <= seconds <= 10


def test_plan_refuses_a_slumped_arm():
    with pytest.raises(ValueError, match="limits"):
        plan((0.0, 0.0, -1.8, 0.0))


def test_folding_into_the_plate_is_caught():
    assert not clear_of_mount((-1.5, 1.4, 1.9))   # wrist curled back up into the base

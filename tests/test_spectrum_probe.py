import argparse

import pytest

from tools.replay_spectrum_probe import _bins, _profiles


def test_isolated_bin_profiles_are_strict_one_hot_level_six() -> None:
    profiles = _profiles(_bins("0,8,16,24,31"))

    assert list(profiles) == ["bin 0", "bin 8", "bin 16", "bin 24", "bin 31"]
    for name, levels in profiles.items():
        index = int(name.removeprefix("bin "))
        assert len(levels) == 32
        assert levels[index] == 6
        assert sum(levels) == 6


@pytest.mark.parametrize("value", ["", "-1", "32", "1,1", "one"])
def test_bin_parser_rejects_invalid_or_repeated_bins(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _bins(value)


def test_band_profiles_move_captured_width_shape() -> None:
    profiles = _profiles(None, _bins("0,8,16,28"))

    assert list(profiles) == ["band 0-3", "band 8-11", "band 16-19", "band 28-31"]
    for name, levels in profiles.items():
        start = int(name.removeprefix("band ").split("-", 1)[0])
        assert levels[start : start + 4] == (1, 6, 6, 1)
        assert sum(levels) == 14

    with pytest.raises(argparse.ArgumentTypeError):
        _profiles(None, (29,))

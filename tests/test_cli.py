"""Focused contract tests for the safe global-colour CLI demo."""

import json

import pytest

from attack_shark_x68he.cli import _key_colors, _row_colors, run_global_demo
from attack_shark_x68he.errors import ProtocolError


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class FakeDevice:
    def __init__(self, fail_at=None):
        self.fail_at = fail_at
        self.colors = []
        self.acquired = 0
        self.released = 0

    def acquire_global_stream(self):
        self.acquired += 1
        return {"mode": "previous", "color": [12, 34, 56]}

    def set_global_color(self, rgb):
        if self.fail_at is not None and len(self.colors) == self.fail_at:
            raise RuntimeError("simulated HID write failure")
        self.colors.append(tuple(rgb))

    def release_global_stream(self):
        self.released += 1


def test_demo_is_deterministic_and_returns_json_summary():
    clock = FakeClock()
    device = FakeDevice()

    summary = run_global_demo(
        device,
        fps=4,
        duration=0.5,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    assert device.acquired == 1
    assert device.released == 1
    assert len(device.colors) == 2
    assert len(set(device.colors)) == 2
    assert all(
        len(color) == 3 and all(0 <= value <= 255 for value in color) for color in device.colors
    )
    assert summary["frames_sent"] == 2
    assert summary["fps"] == 4
    assert summary["duration_seconds"] == 0.5
    json.dumps(summary)


def test_demo_releases_global_stream_when_write_fails():
    clock = FakeClock()
    device = FakeDevice(fail_at=1)

    with pytest.raises(RuntimeError, match="simulated HID write failure"):
        run_global_demo(
            device,
            fps=4,
            duration=1.0,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

    assert device.acquired == 1
    assert device.released == 1


def test_custom_key_assignments_are_parsed_and_duplicates_rejected():
    assert _key_colors(["escape=#ff0000", "a=#00ff00"]) == {
        "escape": "#ff0000",
        "a": "#00ff00",
    }
    with pytest.raises(ProtocolError):
        _key_colors(["escape=#ff0000", "escape=#00ff00"])
    with pytest.raises(ProtocolError):
        _key_colors(["missing-separator"])


def test_custom_row_assignments_expand_to_physical_keys():
    colors = _row_colors(["0=#ff0000", "4=#0000ff"])
    assert colors["escape"] == "#ff0000"
    assert colors["delete"] == "#ff0000"
    assert colors["space"] == "#0000ff"
    assert colors["arrow_right"] == "#0000ff"
    assert "a" not in colors
    with pytest.raises(ProtocolError):
        _row_colors(["5=#ffffff"])

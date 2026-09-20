import pytest

from attack_shark_x68he.controller import (
    PRESET_MODES,
    X68Manager,
    compile_custom_pattern,
    preset_from_request,
)
from attack_shark_x68he.device import DeviceController
from attack_shark_x68he.errors import DeviceBusyError, ProtocolError
from attack_shark_x68he.led_map import LED_MAP


def test_static_preset_maps_api_values_to_gen2_wire_values() -> None:
    state = preset_from_request(
        {
            "mode": "static",
            "color": "#1020ff",
            "brightness": 4,
            "speed": 1,
            "option": 2,
        }
    )

    assert state.mode == 1
    assert state.speed == 3
    assert state.brightness == 4
    assert state.option == 2
    assert state.flags == 7
    assert state.rgb == (0x10, 0x20, 0xFF)


def test_host_driven_and_flash_modes_are_not_public_presets() -> None:
    assert not {"user_picture", "music", "screen_color", "user_color"} & PRESET_MODES.keys()


@pytest.mark.parametrize(
    ("field", "value"),
    [("brightness", 5), ("speed", -1), ("option", 16)],
)
def test_invalid_preset_values_fail_before_encoding(field: str, value: int) -> None:
    with pytest.raises(ProtocolError):
        preset_from_request({"mode": "static", field: value})


def test_invalid_mode_and_color_are_rejected() -> None:
    with pytest.raises(ProtocolError):
        preset_from_request({"mode": "screen_color"})
    with pytest.raises(ProtocolError):
        preset_from_request({"mode": "static", "color": "blue"})


def test_manager_exposes_external_device_busy(monkeypatch) -> None:
    def raise_busy() -> None:
        raise DeviceBusyError("HID interface is busy")

    monkeypatch.setattr(DeviceController, "open", staticmethod(raise_busy))
    manager = X68Manager()

    assert manager.list_devices() == []
    assert manager.busy is True
    with pytest.raises(DeviceBusyError):
        manager.get_device("x68he")


def test_custom_pattern_compiles_named_keys_to_verified_firmware_slots() -> None:
    pattern = compile_custom_pattern(
        {
            "escape": "#ff0000",
            "a": "#00ff00",
            "space": "#0000ff",
            "arrow_right": "#ffffff",
        }
    )

    assert len(pattern) == 126
    assert pattern[1] == (255, 0, 0)
    assert pattern[9] == (0, 255, 0)
    assert pattern[41] == (0, 0, 255)
    assert pattern[89] == (255, 255, 255)
    assert sum(color != (0, 0, 0) for color in pattern) == 4


def test_custom_pattern_rejects_unknown_keys_before_hid_access() -> None:
    with pytest.raises(ProtocolError, match="unknown key"):
        compile_custom_pattern({"not_a_key": "#ffffff"})


def test_custom_pattern_background_applies_only_to_physical_keys() -> None:
    pattern = compile_custom_pattern({"escape": "#ff0000"}, background="#010203")
    physical_slots = {led.matrix_slot for led in LED_MAP}

    assert pattern[1] == (255, 0, 0)
    assert all(pattern[index] == (1, 2, 3) for index in physical_slots - {1})
    assert all(pattern[index] == (0, 0, 0) for index in set(range(126)) - physical_slots)

import pytest

from attack_shark_x68he.controller import PRESET_MODES, X68Manager, preset_from_request
from attack_shark_x68he.device import DeviceController
from attack_shark_x68he.errors import DeviceBusyError, ProtocolError


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

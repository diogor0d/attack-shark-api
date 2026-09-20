import pytest

from attack_shark_x68he.device import DeviceController
from attack_shark_x68he.errors import DeviceBusyError, UnsupportedDeviceError
from attack_shark_x68he.models import LightingState
from attack_shark_x68he.protocol import FLASH_USERPIC, SET_AUDIO, SET_SCREEN_COLOR


class FakeTransport:
    def __init__(self):
        self.writes = []
        self.responses = [
            bytes([0x8F, 0xDE, 8, 0, 0]) + bytes(59),
            bytes([0x80, 2, 1]) + bytes(61),
            bytes([0x87, 21, 3, 4, 0x21, 1, 2, 3]) + bytes(56),
        ]

    def write(self, report):
        self.writes.append(report)
        return len(report)

    def read(self):
        return self.responses.pop(0)

    def close(self):
        pass


def test_controller_probe_state_and_preset():
    t = FakeTransport()
    d = DeviceController(t, settle_seconds=0)
    identity = d.probe()
    assert identity.internal_id == 2270 and d.current_state().mode == 21
    d.set_preset(LightingState(21, rgb=(10, 20, 30)))
    assert t.writes[0][0] == 0x8F and t.writes[-1][0] == 7


def test_global_stream_selects_mode_21_and_emits_only_volatile_color():
    t = FakeTransport()
    d = DeviceController(t, settle_seconds=0)
    d.probe()
    previous = d.acquire_global_stream()
    d.set_global_color((10, 20, 30))
    d.release()
    assert previous.mode == 21
    assert [report[0] for report in t.writes] == [0x8F, 0x80, 0x87, 0x07, SET_SCREEN_COLOR, 0x07]
    assert all(report[0] != 0x0C for report in t.writes)


def test_audio_probe_selects_mode_22_sends_spectrum_and_restores_state():
    t = FakeTransport()
    d = DeviceController(t, settle_seconds=0)
    d.probe()
    previous = d.acquire_audio_probe()
    d.set_audio_spectrum((0, 2, 6, 6, 1) + (0,) * 27)
    d.release()
    assert previous.mode == 21
    assert [report[0] for report in t.writes] == [0x8F, 0x80, 0x87, 0x07, SET_AUDIO, 0x07]
    assert t.writes[-2][8:40] == bytes((0, 2, 6, 6, 1) + (0,) * 27)
    assert all(report[0] != 0x0C for report in t.writes)


def test_custom_pattern_writes_seven_pages_and_leaves_mode_13_selected():
    t = FakeTransport()
    d = DeviceController(
        t,
        settle_seconds=0,
        userpic_mode_seconds=0,
        userpic_page_seconds=0,
        userpic_settle_seconds=0,
    )
    d.probe()
    d.commit_custom_pattern(((0, 0, 0),) * 126)

    assert [report[0] for report in t.writes] == [
        0x8F,
        0x80,
        0x87,
        0x07,
        *([FLASH_USERPIC] * 7),
    ]
    assert t.writes[3][:9].hex() == "070d04040000c8c853"
    assert d._saved_state is None and d._claim is None


def test_controller_requires_probe():
    with pytest.raises(UnsupportedDeviceError):
        DeviceController(FakeTransport(), settle_seconds=0).current_state()


def test_controller_skips_asynchronous_host_driven_reports():
    transport = FakeTransport()
    identify = bytes([0x8F, 0xDE, 8, 0, 0]) + bytes(59)
    transport.responses = [bytes([0x0D]) + bytes(63), identify]
    controller = DeviceController(transport, settle_seconds=0)

    assert controller._exchange(0x8F) == identify


def test_controller_reports_busy_when_host_driven_reports_never_stop():
    transport = FakeTransport()
    transport.responses = [bytes([0x0D]) + bytes(63)] * 60
    controller = DeviceController(transport, settle_seconds=0)

    with pytest.raises(DeviceBusyError):
        controller._exchange(0x8F)


def test_claim_is_process_wide():
    first = DeviceController(FakeTransport(), settle_seconds=0)
    first.identity = first.probe()
    second = DeviceController(FakeTransport(), settle_seconds=0)
    second.identity = first.identity
    first.acquire()
    try:
        with pytest.raises(DeviceBusyError):
            second.acquire()
    finally:
        first.release()

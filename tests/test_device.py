import pytest

from attack_shark_x68he.device import DeviceController
from attack_shark_x68he.errors import DeviceBusyError, UnsupportedDeviceError
from attack_shark_x68he.models import LightingState


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

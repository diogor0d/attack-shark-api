import pytest

from attack_shark_x68he.errors import UnsafeCommandError
from attack_shark_x68he.protocol import GET_LIGHT
from attack_shark_x68he.transport import HidTransport


class Handle:
    def __init__(self):
        self.sent = None

    def send_feature_report(self, value):
        self.sent = value
        return len(value)

    def get_feature_report(self, report_id, length):
        return bytes([0]) + bytes(range(1, length))

    def close(self):
        pass


def test_hidapi_report_id_is_added_and_removed():
    h = Handle()
    t = HidTransport(h)
    payload = bytes([GET_LIGHT]) + bytes(63)
    assert t.write(payload) == 65 and h.sent == bytes([0]) + payload
    assert t.read() == bytes(range(1, 65))


def test_transport_rejects_unallowlisted_write_opcode():
    h = Handle()
    with pytest.raises(UnsafeCommandError):
        HidTransport(h).write(bytes([0x0C]) + bytes(63))


def test_discovery_restricts_to_vendor_interface(monkeypatch):
    import sys
    import types

    devices = [
        {
            "interface_number": 1,
            "usage_page": 0xFFFF,
            "usage": 2,
        },
        {
            "interface_number": 2,
            "usage_page": 0xFFFF,
            "usage": 2,
        },
    ]
    monkeypatch.setitem(sys.modules, "hid", types.SimpleNamespace(enumerate=lambda *_: devices))

    assert list(HidTransport.discover()) == [devices[1]]

from fastapi.testclient import TestClient

from attack_shark_x68he.api import create_app
from attack_shark_x68he.errors import DeviceBusyError
from attack_shark_x68he.flash_guard import FlashDecision


class Device:
    id = "x68he"
    name = "Test X68HE"
    vendor_id = 3151
    product_id = 502
    revision = "2270"
    led_map = [{"index": i, "name": f"K{i}"} for i in range(2)]
    capabilities = {"streaming_supported": False, "presets": True}
    max_frame_rate = 0

    def __init__(self):
        self.calls = []
        self.restored = None

    def set_preset(self, value):
        self.calls.append(("preset", value))
        return None

    def set_frame(self, value):
        self.calls.append(("frame", value))
        return None

    def capture_state(self):
        return {"mode": "saved"}

    def restore_state(self, value):
        self.restored = value

    def commit_custom_pattern(self, colors, *, background):
        self.calls.append(("custom", colors, background))


class Manager:
    last_error = None

    def __init__(self):
        self.device = Device()

    def list_devices(self):
        return [self.device]

    def get_device(self, device_id):
        if device_id != self.device.id:
            raise KeyError(device_id)
        return self.device

    def close(self):
        pass


class BusyManager:
    last_error = "HID interface is busy"
    busy = True

    def list_devices(self):
        return []

    def get_device(self, _device_id):
        raise DeviceBusyError(self.last_error)

    def close(self):
        pass


def _enable_global_stream(manager):
    manager.device.capabilities = {
        "global_color_streaming": True,
        "presets": True,
    }
    manager.device.acquire_global_stream = lambda: manager.device.capture_state()
    manager.device.release_global_stream = lambda: manager.device.restore_state({"mode": "saved"})


def test_health_and_device_metadata():
    client = TestClient(create_app(Manager()))
    assert client.get("/health").json()["status"] == "ok"
    response = client.get("/v1/devices/x68he")
    assert response.status_code == 200
    assert response.json()["led_count"] == 2


def test_global_stream_capabilities_advertise_20_fps_and_no_per_key_support():
    manager = Manager()
    manager.device.capabilities = {
        "streaming_supported": False,
        "global_color_streaming": True,
        "global_color_max_frame_rate": 20,
        "per_key_streaming": False,
    }
    manager.device.max_frame_rate = 20
    metadata = TestClient(create_app(manager)).get("/v1/devices/x68he").json()
    assert metadata["max_frame_rate"] == 20
    assert metadata["capabilities"]["global_color_max_frame_rate"] == 20
    assert metadata["capabilities"]["per_key_streaming"] is False


def test_busy_device_is_not_reported_as_missing():
    client = TestClient(create_app(BusyManager()))
    response = client.get("/v1/devices/x68he")
    assert response.status_code == 409


def test_unproven_frame_is_501_and_does_not_write():
    manager = Manager()
    client = TestClient(create_app(manager))
    response = client.put("/v1/devices/x68he/lighting/frame", content=b"\0" * 6)
    assert response.status_code == 501
    assert manager.device.calls == []


def test_invalid_preset_is_rejected_without_write():
    manager = Manager()
    client = TestClient(create_app(manager))
    response = client.put(
        "/v1/devices/x68he/lighting/preset", json={"mode": "solid", "color": [999, 0, 0]}
    )
    assert response.status_code == 422
    assert manager.device.calls == []


def test_static_custom_pattern_requires_flash_confirmation(monkeypatch):
    manager = Manager()
    manager.device.capabilities = {"static_per_key": True}
    client = TestClient(create_app(manager))

    response = client.put(
        "/v1/devices/x68he/lighting/custom",
        json={"colors": {"escape": "#ff0000"}},
    )

    assert response.status_code == 422
    assert manager.device.calls == []


def test_static_custom_pattern_commits_once_and_reports_unchanged(monkeypatch):
    manager = Manager()
    manager.device.capabilities = {"static_per_key": True}
    client = TestClient(create_app(manager))
    recorded = []
    monkeypatch.setattr(
        "attack_shark_x68he.api.check_flash_write",
        lambda *_args, **_kwargs: FlashDecision("abc", False),
    )
    monkeypatch.setattr(
        "attack_shark_x68he.api.record_flash_write", lambda decision: recorded.append(decision)
    )

    response = client.put(
        "/v1/devices/x68he/lighting/custom",
        json={
            "colors": {"escape": "#ff0000", "space": [0, 0, 255]},
            "background": "#010101",
            "confirm_flash_write": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["written"] is True
    assert manager.device.calls == [
        ("custom", {"escape": "#ff0000", "space": [0, 0, 255]}, "#010101")
    ]
    assert recorded == [FlashDecision("abc", False)]

    monkeypatch.setattr(
        "attack_shark_x68he.api.check_flash_write",
        lambda *_args, **_kwargs: FlashDecision("abc", True),
    )
    response = client.put(
        "/v1/devices/x68he/lighting/custom",
        json={"colors": {"escape": "#ff0000"}, "confirm_flash_write": True},
    )
    assert response.json() == {"ok": True, "written": False, "reason": "unchanged"}


def test_static_custom_pattern_rejects_unknown_key_without_flash_check(monkeypatch):
    manager = Manager()
    manager.device.capabilities = {"static_per_key": True}
    client = TestClient(create_app(manager))
    checked = []
    monkeypatch.setattr(
        "attack_shark_x68he.api.check_flash_write",
        lambda *_args, **_kwargs: checked.append(True),
    )

    response = client.put(
        "/v1/devices/x68he/lighting/custom",
        json={"colors": {"not_a_key": "#ff0000"}, "confirm_flash_write": True},
    )

    assert response.status_code == 422
    assert checked == []
    assert manager.device.calls == []


def test_unproven_websocket_is_closed_clearly():
    client = TestClient(create_app(Manager()))
    with client.websocket_connect("/v1/devices/x68he/lighting/stream") as socket:
        message = socket.receive()
        assert message["type"] == "websocket.close"
        assert message["code"] == 1011


def test_supported_stream_writes_frame_and_restores_state():
    manager = Manager()
    manager.device.capabilities = {"streaming_supported": True, "presets": True}
    manager.device.max_frame_rate = 20
    client = TestClient(create_app(manager))
    with client.websocket_connect("/v1/devices/x68he/lighting/stream") as socket:
        assert socket.receive_json()["type"] == "metadata"
        socket.send_bytes(b"\x01\x02\x03" * 2)
        socket.send_json({"type": "release"})
        assert socket.receive_json()["type"] == "released"
    assert manager.device.calls == [("frame", b"\x01\x02\x03" * 2)]
    assert manager.device.restored == {"mode": "saved"}


def test_supported_stream_uses_device_claim_hooks_when_available():
    manager = Manager()
    manager.device.capabilities = {"streaming_supported": True, "presets": True}
    manager.device.max_frame_rate = 20
    manager.device.claimed = False
    manager.device.released = False
    manager.device.acquire_stream = lambda: (
        setattr(manager.device, "claimed", True) or {"mode": "saved"}
    )
    manager.device.release_stream = lambda: setattr(manager.device, "released", True)

    client = TestClient(create_app(manager))
    with client.websocket_connect("/v1/devices/x68he/lighting/stream") as socket:
        assert socket.receive_json()["type"] == "metadata"
        socket.send_json({"type": "release"})

    assert manager.device.claimed is True
    assert manager.device.released is True


def test_global_stream_accepts_rgb_and_restores_state():
    manager = Manager()
    manager.device.capabilities = {
        "streaming_supported": False,
        "global_color_streaming": True,
        "presets": True,
    }
    manager.device.acquire_global_stream = lambda: manager.device.capture_state()
    manager.device.set_global_color = lambda rgb: manager.device.calls.append(("global", rgb))
    manager.device.release_global_stream = lambda: (
        manager.device.calls.append(("release",)),
        manager.device.restore_state({"mode": "saved"}),
    )[-1]
    client = TestClient(create_app(manager))
    with client.websocket_connect("/v1/devices/x68he/lighting/global-stream") as socket:
        assert socket.receive_json() == {"type": "metadata", "max_frame_rate": 20, "mode": 21}
        socket.send_json({"color": [1, 2, 3]})
        socket.send_json({"color": [4, 5, 6]})
        socket.send_json({"type": "release"})
        assert socket.receive_json() == {"type": "released"}
    assert any(call[0] == "global" for call in manager.device.calls)
    assert ("release",) in manager.device.calls


def test_global_stream_owns_device_and_blocks_preset_until_release():
    manager = Manager()
    _enable_global_stream(manager)
    client = TestClient(create_app(manager))
    with client.websocket_connect("/v1/devices/x68he/lighting/global-stream") as socket:
        assert socket.receive_json()["type"] == "metadata"

        response = client.put(
            "/v1/devices/x68he/lighting/preset",
            json={"mode": "solid", "color": [1, 2, 3]},
        )
        assert response.status_code == 409
        assert manager.device.calls == []

        response = client.put(
            "/v1/devices/x68he/lighting/custom",
            json={"colors": {"escape": "#ff0000"}, "confirm_flash_write": True},
        )
        assert response.status_code == 409
        assert manager.device.calls == []

        socket.send_json({"type": "release"})
        assert socket.receive_json() == {"type": "released"}

    response = client.put(
        "/v1/devices/x68he/lighting/preset",
        json={"mode": "solid", "color": [1, 2, 3]},
    )
    assert response.status_code == 200
    assert manager.device.calls[0][0] == "preset"


def test_global_stream_disconnect_releases_device_for_preset():
    manager = Manager()
    _enable_global_stream(manager)
    client = TestClient(create_app(manager))
    with client.websocket_connect("/v1/devices/x68he/lighting/global-stream") as socket:
        assert socket.receive_json()["type"] == "metadata"
        response = client.put(
            "/v1/devices/x68he/lighting/preset",
            json={"mode": "solid", "color": [1, 2, 3]},
        )
        assert response.status_code == 409
        assert manager.device.calls == []

    response = client.put(
        "/v1/devices/x68he/lighting/preset",
        json={"mode": "solid", "color": [1, 2, 3]},
    )
    assert response.status_code == 200
    assert manager.device.calls[0][0] == "preset"


def test_global_stream_rejects_non_triplets_without_writing():
    manager = Manager()
    manager.device.capabilities = {"global_color_streaming": True}
    manager.device.acquire_global_stream = lambda: manager.device.capture_state()
    manager.device.set_global_color = lambda rgb: manager.device.calls.append(("global", rgb))
    manager.device.release_stream = lambda: None
    client = TestClient(create_app(manager))
    with client.websocket_connect("/v1/devices/x68he/lighting/global-stream") as socket:
        socket.receive_json()
        socket.send_json({"color": [1, 2]})
        assert socket.receive_json()["error"]
        socket.send_json({"type": "release"})
    assert not any(call[0] == "global" for call in manager.device.calls)


def test_global_stream_restores_and_reports_hid_writer_failure():
    manager = Manager()
    manager.device.capabilities = {"global_color_streaming": True}
    manager.device.acquire_global_stream = lambda: manager.device.capture_state()

    def fail_write(_rgb):
        raise OSError("simulated HID failure")

    manager.device.set_global_color = fail_write
    manager.device.release_global_stream = lambda: manager.device.calls.append(("release",))
    client = TestClient(create_app(manager))
    with client.websocket_connect("/v1/devices/x68he/lighting/global-stream") as socket:
        socket.receive_json()
        socket.send_bytes(b"\x01\x02\x03")
        socket.send_json({"type": "release"})
        messages = [socket.receive_json(), socket.receive_json()]

    assert messages[0] == {"type": "error", "error": "simulated HID failure"}
    assert messages[1] == {"type": "released"}
    assert ("release",) in manager.device.calls

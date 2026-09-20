import time

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


def test_dashboard_and_browser_security_headers_are_served_locally():
    client = TestClient(create_app(Manager()))
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]

    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "javascript" in asset.headers["content-type"]
    assert '"use strict"' in asset.text


def test_lighting_state_returns_named_preset_without_mutation():
    manager = Manager()
    manager.device.capture_state = lambda: {
        "mode": 1,
        "speed": 4,
        "brightness": 3,
        "option": 0,
        "flags": 7,
        "rgb": (12, 34, 56),
    }
    response = TestClient(create_app(manager)).get("/v1/devices/x68he/lighting/state")
    assert response.status_code == 200
    assert response.json() == {
        "mode": 1,
        "mode_name": "static",
        "speed": 0,
        "wire_speed": 4,
        "brightness": 3,
        "option": 0,
        "flags": 7,
        "rgb": [12, 34, 56],
    }


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


def test_global_layers_compose_multiple_apps_and_restore_after_last_layer():
    manager = Manager()
    _enable_global_stream(manager)
    manager.device.set_global_color = lambda rgb: manager.device.calls.append(("global", rgb))

    with TestClient(create_app(manager)) as client:
        response = client.put(
            "/v1/devices/x68he/lighting/global-layers/game/base",
            json={"color": [10, 20, 30], "priority": 0},
        )
        assert response.status_code == 200
        assert response.json()["output"] == [10, 20, 30]

        response = client.put(
            "/v1/devices/x68he/lighting/global-layers/notifications/alert",
            json={"color": "#ff0000", "priority": 200},
        )
        assert response.status_code == 200
        assert response.json()["output"] == [255, 0, 0]
        assert len(response.json()["layers"]) == 2

        blocked = client.put(
            "/v1/devices/x68he/lighting/preset",
            json={"mode": "solid", "color": [1, 2, 3]},
        )
        assert blocked.status_code == 409

        response = client.delete("/v1/devices/x68he/lighting/global-layers/notifications/alert")
        assert response.json()["output"] == [10, 20, 30]
        response = client.delete("/v1/devices/x68he/lighting/global-layers/game/base")
        assert response.json()["active"] is False
        assert response.json()["layers"] == []

    assert manager.device.restored == {"mode": "saved"}


def test_global_layer_websocket_owns_and_cleans_up_its_source():
    manager = Manager()
    _enable_global_stream(manager)
    manager.device.set_global_color = lambda rgb: manager.device.calls.append(("global", rgb))

    with TestClient(create_app(manager)) as client:
        with client.websocket_connect(
            "/v1/devices/x68he/lighting/global-layers/my-app/stream"
        ) as socket:
            metadata = socket.receive_json()
            assert metadata["scope"] == "global_color"
            assert metadata["blend_modes"] == ["replace", "alpha", "add"]
            socket.send_json(
                {
                    "type": "set",
                    "layer_id": "keypress",
                    "color": [0, 255, 0],
                    "priority": 200,
                    "ttl_ms": 500,
                    "fade_out_ms": 100,
                }
            )
            updated = socket.receive_json()
            assert updated["type"] == "updated"
            assert updated["output"] == [0, 255, 0]
            socket.send_json({"type": "release"})
            released = socket.receive_json()
            assert released["type"] == "released"
            assert released["removed"] == 1

        assert client.get("/v1/devices/x68he/lighting/global-layers").json()["layers"] == []

    assert manager.device.restored == {"mode": "saved"}


def test_global_layer_ttl_expires_and_releases_device():
    manager = Manager()
    _enable_global_stream(manager)
    manager.device.set_global_color = lambda rgb: manager.device.calls.append(("global", rgb))

    with TestClient(create_app(manager)) as client:
        response = client.put(
            "/v1/devices/x68he/lighting/global-layers/app/short",
            json={"color": [1, 2, 3], "ttl_ms": 20},
        )
        assert response.status_code == 200
        time.sleep(0.15)
        status = client.get("/v1/devices/x68he/lighting/global-layers").json()
        assert status["active"] is False
        assert status["layers"] == []

    assert manager.device.restored == {"mode": "saved"}


def test_global_layer_rejects_fade_without_compatible_ttl():
    manager = Manager()
    _enable_global_stream(manager)
    client = TestClient(create_app(manager))

    no_ttl = client.put(
        "/v1/devices/x68he/lighting/global-layers/app/invalid",
        json={"color": [1, 2, 3], "fade_out_ms": 100},
    )
    longer_than_ttl = client.put(
        "/v1/devices/x68he/lighting/global-layers/app/invalid",
        json={"color": [1, 2, 3], "ttl_ms": 100, "fade_out_ms": 101},
    )

    assert no_ttl.status_code == 422
    assert longer_than_ttl.status_code == 422
    assert manager.device.calls == []


def test_global_layer_restore_failure_is_reported_and_releases_api_owner():
    manager = Manager()
    _enable_global_stream(manager)
    manager.device.set_global_color = lambda rgb: manager.device.calls.append(("global", rgb))

    def fail_restore():
        raise OSError("restore failed")

    manager.device.release_global_stream = fail_restore
    with TestClient(create_app(manager)) as client:
        assert (
            client.put(
                "/v1/devices/x68he/lighting/global-layers/app/base",
                json={"color": [1, 2, 3]},
            ).status_code
            == 200
        )
        response = client.delete("/v1/devices/x68he/lighting/global-layers/app/base")
        assert response.status_code == 503
        assert "restore failed" in response.json()["detail"]
        metadata = client.get("/v1/devices/x68he").json()
        assert metadata["owner"] is False


def test_global_layer_writer_failure_clears_layers_and_releases_owner():
    manager = Manager()
    _enable_global_stream(manager)

    def fail_write(_rgb):
        raise OSError("HID write failed")

    manager.device.set_global_color = fail_write
    with TestClient(create_app(manager)) as client:
        response = client.put(
            "/v1/devices/x68he/lighting/global-layers/app/base",
            json={"color": [1, 2, 3]},
        )
        assert response.status_code == 200
        time.sleep(0.1)
        status = client.get("/v1/devices/x68he/lighting/global-layers").json()
        assert status["active"] is False
        assert status["layers"] == []
        assert status["last_error"] == "HID write failed"
        assert client.get("/v1/devices/x68he").json()["owner"] is False


def test_global_layer_websocket_rejects_duplicate_source_and_malformed_messages():
    manager = Manager()
    _enable_global_stream(manager)
    manager.device.set_global_color = lambda rgb: manager.device.calls.append(("global", rgb))

    with (
        TestClient(create_app(manager)) as client,
        client.websocket_connect(
            "/v1/devices/x68he/lighting/global-layers/same-source/stream"
        ) as first,
    ):
        assert first.receive_json()["type"] == "metadata"
        with client.websocket_connect(
            "/v1/devices/x68he/lighting/global-layers/same-source/stream"
        ) as duplicate:
            closed = duplicate.receive()
            assert closed["type"] == "websocket.close"
            assert closed["code"] == 4409

        first.send_text("not-json")
        assert first.receive_json()["status"] == 422
        first.send_json({"type": "set", "layer_id": 123, "color": [1, 2, 3]})
        assert first.receive_json()["status"] == 422
        first.send_json({"type": "release"})
        assert first.receive_json()["type"] == "released"

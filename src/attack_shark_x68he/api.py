"""FastAPI surface for the X68HE controller."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .controller import compile_custom_pattern
from .errors import DeviceBusyError as HardwareDeviceBusyError
from .errors import ProtocolError, UnsafeCommandError, X68Error
from .flash_guard import check_flash_write, record_flash_write
from .streaming import DeviceBusyError, LatestFrameQueue, StreamOwners


class DeviceManager(Protocol):
    last_error: str | None

    def list_devices(self) -> list[Any]: ...

    def get_device(self, device_id: str) -> Any: ...

    def close(self) -> None: ...


class PresetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = Field(min_length=1, max_length=64)
    color: str | list[int] | None = None
    brightness: int = Field(default=4, ge=0, le=4)
    speed: int = Field(default=2, ge=0, le=4)
    option: int = Field(default=0, ge=0, le=15)

    @field_validator("color")
    @classmethod
    def valid_color(cls, value: str | list[int] | None) -> str | list[int] | None:
        if value is None:
            return value
        if isinstance(value, str):
            if len(value) != 7 or not value.startswith("#"):
                raise ValueError("color must use #RRGGBB")
            try:
                bytes.fromhex(value[1:])
            except ValueError as exc:
                raise ValueError("color must use #RRGGBB") from exc
            return value
        if len(value) != 3 or any(
            not isinstance(component, int) or not 0 <= component <= 255 for component in value
        ):
            raise ValueError("color must contain three integers in range 0..255")
        return value


class CustomPatternRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    colors: dict[str, str | list[int]] = Field(min_length=1)
    background: str | list[int] = "#000000"
    confirm_flash_write: bool = False


def _value(value: Any, key: str, default: Any = None) -> Any:
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _controller(manager: DeviceManager, device_id: str) -> Any:
    try:
        device = manager.get_device(device_id)
    except HardwareDeviceBusyError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (KeyError, LookupError, AttributeError) as exc:
        raise HTTPException(404, f"unknown or disconnected device: {device_id}") from exc
    if device is None:
        raise HTTPException(404, f"unknown or disconnected device: {device_id}")
    return device


def _capabilities(device: Any) -> dict[str, Any]:
    value = _value(device, "capabilities", {}) or {}
    if isinstance(value, dict):
        return value
    return vars(value)


def _metadata(device: Any, owners: StreamOwners) -> dict[str, Any]:
    device_id = str(_value(device, "id", _value(device, "device_id", "unknown")))
    capabilities = _capabilities(device)
    leds = _value(device, "led_map", _value(device, "leds", [])) or []
    return {
        "id": device_id,
        "name": _value(device, "name", "Attack Shark X68HE"),
        "vendor_id": _value(device, "vendor_id", 0x3151),
        "product_id": _value(device, "product_id", 0x502D),
        "internal_id": _value(device, "internal_id"),
        "revision": _value(device, "revision"),
        "capabilities": capabilities,
        "led_count": len(leds),
        "led_map": leds,
        "owner": owners.owner(device_id) is not None,
        "max_frame_rate": _value(device, "max_frame_rate", 0),
    }


def _decode_color(value: Any, name: str) -> bytes:
    if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
        try:
            return bytes.fromhex(value[1:])
        except ValueError as exc:
            raise ValueError(f"invalid RGB color for {name}") from exc
    if (
        isinstance(value, list)
        and len(value) == 3
        and all(isinstance(component, int) and 0 <= component <= 255 for component in value)
    ):
        return bytes(value)
    raise ValueError(f"invalid RGB color for {name}")


def _frame_from_json(payload: Any, device: Any) -> bytes:
    leds = _value(device, "led_map", _value(device, "leds", [])) or []
    colors = payload.get("colors") if isinstance(payload, dict) else None
    if not isinstance(colors, dict):
        raise ValueError("JSON frame must contain a colors object keyed by LED name")
    names = {str(_value(led, "name", _value(led, "key", ""))): led for led in leds}
    unknown = set(colors) - set(names)
    if unknown:
        raise ValueError(f"unknown LED name: {sorted(unknown)[0]}")
    output = bytearray(len(leds) * 3)
    for name, color in colors.items():
        index = int(_value(names[name], "index", 0))
        output[index * 3 : index * 3 + 3] = _decode_color(color, name)
    return bytes(output)


def _streaming_supported(device: Any) -> bool:
    return bool(_capabilities(device).get("streaming_supported", False))


def _global_color(message: Any) -> tuple[int, int, int]:
    if isinstance(message, (bytes, bytearray)):
        values = list(message)
    else:
        if isinstance(message, list):
            values = message
        else:
            value = message.get("color", message.get("rgb")) if isinstance(message, dict) else None
            values = value if isinstance(value, list) else None
    if (
        not isinstance(values, list)
        or len(values) != 3
        or any(not isinstance(value, int) or not 0 <= value <= 255 for value in values)
    ):
        raise ValueError("global stream frames must contain exactly one RGB triplet")
    return (values[0], values[1], values[2])


def create_app(manager: DeviceManager) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        close = getattr(manager, "close", None)
        if close is not None:
            close()

    app = FastAPI(
        title="Attack Shark X68HE Lighting API",
        version="0.1.0",
        lifespan=lifespan,
    )
    owners = StreamOwners()
    custom_write_lock = asyncio.Lock()
    app.state.manager = manager
    app.state.stream_owners = owners

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "service": "attack-shark-x68he"}

    @app.get("/v1/devices")
    async def devices() -> dict[str, Any]:
        found = manager.list_devices()
        return {
            "devices": [_metadata(device, owners) for device in found],
            "error": manager.last_error if not found else None,
            "busy": bool(getattr(manager, "busy", False)) if not found else False,
        }

    @app.get("/v1/devices/{device_id}")
    async def device_info(device_id: str) -> dict[str, Any]:
        return _metadata(_controller(manager, device_id), owners)

    @app.put("/v1/devices/{device_id}/lighting/preset")
    async def preset(device_id: str, body: PresetRequest) -> dict[str, Any]:
        device = _controller(manager, device_id)
        if owners.owner(device_id) is not None:
            raise HTTPException(409, "device is currently owned by a stream")
        if not bool(_capabilities(device).get("presets", True)):
            raise HTTPException(501, "preset control is unsupported")
        try:
            device.set_preset(body.model_dump(exclude_none=True))
        except (ProtocolError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        except (X68Error, OSError) as exc:
            raise HTTPException(503, str(exc)) from exc
        return {"ok": True}

    @app.put("/v1/devices/{device_id}/lighting/frame")
    async def frame(device_id: str, request: Request) -> dict[str, Any]:
        device = _controller(manager, device_id)
        if owners.owner(device_id) is not None:
            raise HTTPException(409, "device is currently owned by a stream")
        if not _streaming_supported(device):
            raise HTTPException(501, "volatile streaming is not proven for this device")
        try:
            raw = await request.body()
            if "application/json" in request.headers.get("content-type", ""):
                raw = _frame_from_json(json.loads(raw), device)
            expected = len(_value(device, "led_map", _value(device, "leds", [])) or []) * 3
            if len(raw) != expected:
                raise ValueError(f"frame must be exactly {expected} bytes")
            device.set_frame(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        except NotImplementedError as exc:
            raise HTTPException(501, str(exc)) from exc
        except (X68Error, OSError) as exc:
            raise HTTPException(503, str(exc)) from exc
        return {"ok": True}

    @app.put("/v1/devices/{device_id}/lighting/custom")
    async def custom_pattern(device_id: str, body: CustomPatternRequest) -> dict[str, Any]:
        device = _controller(manager, device_id)
        if owners.owner(device_id) is not None:
            raise HTTPException(409, "device is currently owned by a stream")
        if not bool(_capabilities(device).get("static_per_key", False)):
            raise HTTPException(501, "static per-key patterns are unsupported")
        try:
            pattern = compile_custom_pattern(body.colors, background=body.background)
            async with custom_write_lock:
                decision = check_flash_write(pattern, confirmed=body.confirm_flash_write)
                if decision.unchanged:
                    return {"ok": True, "written": False, "reason": "unchanged"}
                await asyncio.to_thread(
                    device.commit_custom_pattern,
                    body.colors,
                    background=body.background,
                )
                record_flash_write(decision)
        except HardwareDeviceBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ProtocolError, UnsafeCommandError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        except (X68Error, OSError) as exc:
            raise HTTPException(503, str(exc)) from exc
        return {
            "ok": True,
            "written": True,
            "storage": "USERPIC flash slot 0",
            "mode": 13,
        }

    @app.websocket("/v1/devices/{device_id}/lighting/stream")
    async def stream(websocket: WebSocket, device_id: str) -> None:
        try:
            device = manager.get_device(device_id)
        except HardwareDeviceBusyError:
            await websocket.accept()
            await websocket.close(code=4409, reason="device is busy")
            return
        except (KeyError, LookupError, AttributeError):
            await websocket.accept()
            await websocket.close(code=4404, reason="unknown or disconnected device")
            return
        if not _streaming_supported(device):
            await websocket.accept()
            await websocket.close(code=1011, reason="volatile streaming is not proven")
            return
        try:
            lease = await owners.acquire(device_id, websocket)
        except DeviceBusyError:
            await websocket.accept()
            await websocket.close(code=4409, reason="device is already streaming")
            return

        release_stream = getattr(device, "release_stream", None)
        acquired_stream = getattr(device, "acquire_stream", None)
        try:
            previous = acquired_stream() if callable(acquired_stream) else device.capture_state()
        except (X68Error, OSError) as exc:
            await owners.release(lease)
            await websocket.accept()
            await websocket.close(code=1011, reason=str(exc))
            return

        queue = LatestFrameQueue(1)
        maximum = min(30, int(_value(device, "max_frame_rate", 0)))
        if maximum < 1:
            await owners.release(lease)
            with suppress(Exception):
                if callable(release_stream):
                    release_stream()
                else:
                    device.restore_state(previous)
            await websocket.accept()
            await websocket.close(code=1011, reason="no safe frame rate has been measured")
            return
        frame_rate = min(20, maximum)

        async def write_frames() -> None:
            delay = 1 / frame_rate
            while True:
                payload = await queue.get()
                try:
                    await asyncio.to_thread(device.set_frame, payload)
                    await asyncio.sleep(delay)
                finally:
                    queue.task_done()

        writer = asyncio.create_task(write_frames())
        explicit_release = False
        try:
            await websocket.accept()
            await websocket.send_json(
                {
                    "type": "metadata",
                    "mapping_version": 1,
                    "default_frame_rate": frame_rate,
                    **_metadata(device, owners),
                }
            )
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                try:
                    if message.get("bytes") is not None:
                        payload = bytes(message["bytes"])
                    elif message.get("text") is not None:
                        decoded = json.loads(message["text"])
                        if isinstance(decoded, dict) and decoded.get("type") == "release":
                            explicit_release = True
                            break
                        payload = _frame_from_json(decoded, device)
                    else:
                        continue
                    expected = len(_value(device, "led_map", _value(device, "leds", []))) * 3
                    if len(payload) != expected:
                        raise ValueError(f"frame must be exactly {expected} bytes")
                except (ValueError, json.JSONDecodeError) as exc:
                    await websocket.send_json({"error": str(exc)})
                    continue
                queue.put_nowait(payload)
        except WebSocketDisconnect:
            pass
        finally:
            with suppress(TimeoutError):
                await asyncio.wait_for(queue.join(), timeout=1)
            writer.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await writer
            await owners.release(lease)
            with suppress(Exception):
                if callable(release_stream):
                    release_stream()
                else:
                    device.restore_state(previous)
            if explicit_release:
                with suppress(Exception):
                    await websocket.send_json({"type": "released"})

    @app.websocket("/v1/devices/{device_id}/lighting/global-stream")
    async def global_stream(websocket: WebSocket, device_id: str) -> None:
        try:
            device = manager.get_device(device_id)
            if not _capabilities(device).get("global_color_streaming", False):
                raise NotImplementedError("global colour streaming is unsupported")
        except HardwareDeviceBusyError:
            await websocket.accept()
            await websocket.close(code=4409, reason="device is busy")
            return
        except (KeyError, LookupError, AttributeError):
            await websocket.accept()
            await websocket.close(code=4404, reason="unknown or disconnected device")
            return
        except NotImplementedError:
            await websocket.accept()
            await websocket.close(code=1011, reason="global colour streaming is unsupported")
            return
        except (X68Error, OSError) as exc:
            await websocket.accept()
            await websocket.close(code=1011, reason=str(exc))
            return

        try:
            lease = await owners.acquire(device_id, websocket)
        except DeviceBusyError:
            await websocket.accept()
            await websocket.close(code=4409, reason="device is already streaming")
            return

        try:
            previous = device.acquire_global_stream()
        except HardwareDeviceBusyError:
            await owners.release(lease)
            await websocket.accept()
            await websocket.close(code=4409, reason="device is busy")
            return
        except NotImplementedError:
            await owners.release(lease)
            await websocket.accept()
            await websocket.close(code=1011, reason="global colour streaming is unsupported")
            return
        except (X68Error, OSError) as exc:
            await owners.release(lease)
            await websocket.accept()
            await websocket.close(code=1011, reason=str(exc))
            return
        except Exception:
            await owners.release(lease)
            raise

        queue = LatestFrameQueue(1)
        writer_error: Exception | None = None

        async def write_colors() -> None:
            nonlocal writer_error
            while True:
                raw_rgb = await queue.get()
                rgb = tuple(raw_rgb)
                try:
                    await asyncio.to_thread(device.set_global_color, rgb)
                    await asyncio.sleep(1 / 20)
                except Exception as exc:
                    writer_error = exc
                    raise
                finally:
                    queue.task_done()

        writer = asyncio.create_task(write_colors())
        explicit_release = False
        try:
            await websocket.accept()
            await websocket.send_json({"type": "metadata", "max_frame_rate": 20, "mode": 21})
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                try:
                    if message.get("bytes") is not None:
                        rgb = _global_color(bytes(message["bytes"]))
                    elif message.get("text") is not None:
                        decoded = json.loads(message["text"])
                        if isinstance(decoded, dict) and decoded.get("type") == "release":
                            explicit_release = True
                            break
                        rgb = _global_color(decoded)
                    else:
                        continue
                except (ValueError, json.JSONDecodeError) as exc:
                    await websocket.send_json({"error": str(exc)})
                    continue
                queue.put_nowait(bytes(rgb))
        except WebSocketDisconnect:
            pass
        finally:
            with suppress(TimeoutError):
                await asyncio.wait_for(queue.join(), timeout=1)
            writer.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await writer
            with suppress(Exception):
                release_stream = getattr(device, "release_global_stream", None)
                if not callable(release_stream):
                    release_stream = getattr(device, "release_stream", None)
                if callable(release_stream):
                    release_stream()
                else:
                    device.restore_state(previous)
            await owners.release(lease)
            if writer_error is not None:
                invalidate = getattr(manager, "invalidate", None)
                if callable(invalidate):
                    invalidate(device_id)
            if writer_error is not None:
                with suppress(Exception):
                    await websocket.send_json({"type": "error", "error": str(writer_error)})
            if explicit_release:
                with suppress(Exception):
                    await websocket.send_json({"type": "released"})

    return app

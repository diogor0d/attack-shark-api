"""Application-facing adapter around the conservative HID controller."""

from __future__ import annotations

from dataclasses import asdict
from threading import RLock
from typing import Any

from .device import DeviceController
from .errors import DeviceBusyError, DeviceNotFoundError, ProtocolError, X68Error
from .flash_guard import MIN_WRITE_INTERVAL_SECONDS
from .led_map import LED_MAP, MAPPING_VERIFIED
from .models import PID, VID, LightingState

DEVICE_ID = "x68he"

# Host-facing names. Modes that require host data or flash-backed USERPIC writes are omitted.
PRESET_MODES = {
    "off": 0,
    "static": 1,
    "breathing": 2,
    "spectrum": 3,
    "wave": 4,
    "ripple": 5,
    "star": 6,
    "flow": 7,
    "key_shadow": 8,
    "layers": 9,
    "sine": 10,
    "spring": 11,
    "neon": 12,
    "radiant": 14,
    "loop": 15,
    "color_grid": 16,
    "snowfall": 17,
    "meteor": 18,
    "silent_snow": 19,
    "train": 23,
    "endless": 24,
}


def _normalize_color(value: Any) -> tuple[int, int, int]:
    if value is None:
        return (0, 0, 0)
    if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
        try:
            return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]
        except ValueError as exc:
            raise ProtocolError("color must be #RRGGBB") from exc
    if (
        isinstance(value, (list, tuple))
        and len(value) == 3
        and all(isinstance(component, int) and 0 <= component <= 255 for component in value)
    ):
        return tuple(value)  # type: ignore[return-value]
    raise ProtocolError("color must be #RRGGBB or three integers in range 0..255")


def preset_from_request(payload: dict[str, Any]) -> LightingState:
    mode_name = str(payload.get("mode", "")).lower()
    if mode_name not in PRESET_MODES:
        raise ProtocolError(f"unsupported preset mode: {mode_name}")
    brightness = int(payload.get("brightness", 4))
    speed = int(payload.get("speed", 2))
    option = int(payload.get("option", 0))
    if not 0 <= brightness <= 4:
        raise ProtocolError("brightness must be in range 0..4")
    if not 0 <= speed <= 4:
        raise ProtocolError("speed must be in range 0..4")
    if not 0 <= option <= 15:
        raise ProtocolError("option must be in range 0..15")
    color_supplied = payload.get("color") is not None
    color = _normalize_color(payload.get("color"))
    flags = 7 if color_supplied else 8
    wire_speed = 4 - speed
    return LightingState(PRESET_MODES[mode_name], wire_speed, brightness, option, flags, color)


def compile_custom_pattern(
    colors_by_name: dict[str, Any], *, background: Any = "#000000"
) -> tuple[tuple[int, int, int], ...]:
    """Build the complete 126-slot matrix required by gen2 USERPIC."""
    unknown = sorted(set(colors_by_name) - {led.name for led in LED_MAP})
    if unknown:
        raise ProtocolError(f"unknown key names: {', '.join(unknown)}")
    base = _normalize_color(background)
    slots = [(0, 0, 0)] * 126
    for led in LED_MAP:
        if led.matrix_slot is None:
            raise ProtocolError(f"key has no verified matrix slot: {led.name}")
        slots[led.matrix_slot] = base
        if led.name in colors_by_name:
            slots[led.matrix_slot] = _normalize_color(colors_by_name[led.name])
    return tuple(slots)


class ManagedX68HE:
    """Metadata and safe application operations for one connected keyboard."""

    id = DEVICE_ID
    device_id = DEVICE_ID
    name = "Attack Shark X68HE"
    vendor_id = VID
    product_id = PID
    led_map = tuple(asdict(led) for led in LED_MAP)
    leds = led_map
    max_frame_rate = 20
    capabilities = {
        "presets": True,
        "streaming_supported": False,
        "global_color_streaming": True,
        "global_color_max_frame_rate": 20,
        "per_key_streaming": False,
        "static_per_key": True,
        "static_per_key_storage": "flash",
        "custom_pattern_min_interval_seconds": int(MIN_WRITE_INTERVAL_SECONDS),
        "mapping_verified": MAPPING_VERIFIED,
        "preset_modes": tuple(PRESET_MODES),
    }

    def __init__(self, controller: DeviceController) -> None:
        self._controller = controller
        self.identity = controller.identity
        self.internal_id = self.identity.internal_id if self.identity else None
        self.revision = self.identity.revision if self.identity else None

    def set_preset(self, payload: dict[str, Any]) -> None:
        self._controller.set_preset(preset_from_request(payload))

    def capture_state(self) -> LightingState:
        return self._controller.current_state()

    def acquire_stream(self) -> LightingState:
        """Claim the HID interface and capture the state for stream restoration."""
        return self._controller.acquire()

    def restore_state(self, state: LightingState) -> None:
        self._controller.set_preset(state)

    def release_stream(self) -> None:
        """Restore the controller-owned state and release the process-wide claim."""
        self._controller.release()

    def set_frame(self, _frame: bytes) -> None:
        raise NotImplementedError("volatile streaming is not proven for this device")

    def acquire_global_stream(self) -> LightingState:
        return self._controller.acquire_global_stream()

    def set_global_color(self, rgb: tuple[int, int, int]) -> None:
        self._controller.set_global_color(rgb)

    def release_global_stream(self) -> None:
        self._controller.release()

    def acquire_audio_probe(self) -> LightingState:
        """Acquire experimental mode-22 control without advertising an API capability."""
        return self._controller.acquire_audio_probe()

    def set_audio_spectrum(self, levels: tuple[int, ...]) -> None:
        self._controller.set_audio_spectrum(levels)

    def release_audio_probe(self) -> None:
        self._controller.release()

    def commit_custom_pattern(
        self, colors_by_name: dict[str, Any], *, background: Any = "#000000"
    ) -> tuple[tuple[int, int, int], ...]:
        pattern = compile_custom_pattern(colors_by_name, background=background)
        self._controller.commit_custom_pattern(pattern)
        return pattern

    def close(self) -> None:
        self._controller.close()


class X68Manager:
    """Lazy single-device manager; starting the API does not require attached hardware."""

    def __init__(self) -> None:
        self._device: ManagedX68HE | None = None
        self._lock = RLock()
        self.last_error: str | None = None
        self.busy = False

    def refresh(self) -> ManagedX68HE | None:
        with self._lock:
            if self._device is not None:
                return self._device
            controller: DeviceController | None = None
            try:
                controller = DeviceController.open()
                controller.probe()
                self._device = ManagedX68HE(controller)
                self.last_error = None
                self.busy = False
            except DeviceBusyError as exc:
                if controller is not None:
                    controller.close()
                self.last_error = str(exc)
                self.busy = True
            except (DeviceNotFoundError, OSError, RuntimeError, X68Error) as exc:
                if controller is not None:
                    controller.close()
                self.last_error = str(exc)
                self.busy = False
            return self._device

    def list_devices(self) -> list[ManagedX68HE]:
        device = self.refresh()
        return [] if device is None else [device]

    def get_device(self, device_id: str) -> ManagedX68HE:
        if device_id != DEVICE_ID:
            raise KeyError(device_id)
        device = self.refresh()
        if device is None:
            if self.busy:
                raise DeviceBusyError(self.last_error or "X68HE HID interface is busy")
            raise KeyError(device_id)
        return device

    def close(self) -> None:
        with self._lock:
            if self._device is not None:
                self._device.close()
                self._device = None

    def invalidate(self, device_id: str) -> None:
        """Drop a failed cached device so the next request performs discovery again."""
        if device_id != DEVICE_ID:
            return
        self.close()


def create_manager() -> X68Manager:
    return X68Manager()

"""Thread-safe composition of named global RGB lighting layers."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from threading import RLock
from typing import Literal

BlendMode = Literal["replace", "alpha", "add"]


@dataclass(frozen=True, slots=True)
class Layer:
    """A snapshot of one source-owned lighting layer."""

    source_id: str
    name: str
    priority: int
    color: tuple[int, int, int]
    opacity: float
    blend_mode: BlendMode
    expires_at: float | None = None
    fade_out_seconds: float = 0.0

    # Internal monotonic sequence used to break equal-priority ties.
    _updated: int = 0


class GlobalLayerCompositor:
    """Compose source-owned RGB layers without any hardware dependencies."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._layers: dict[tuple[str, str], Layer] = {}
        self._sequence = 0
        self._lock = RLock()

    @staticmethod
    def _text(value: str, field: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} must be a non-empty string")
        return value

    @staticmethod
    def _rgb(color: tuple[int, int, int] | list[int]) -> tuple[int, int, int]:
        if (
            not isinstance(color, (tuple, list))
            or len(color) != 3
            or any(
                isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255
                for value in color
            )
        ):
            raise ValueError("color must contain three integers in range 0..255")
        return (color[0], color[1], color[2])

    @staticmethod
    def _unit(value: float, field: str) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{field} must be a finite number")
        if not 0 <= value <= 1:
            raise ValueError(f"{field} must be in range 0..1")
        return float(value)

    @staticmethod
    def _seconds(value: float, field: str) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{field} must be a finite number")
        if value < 0:
            raise ValueError(f"{field} must be non-negative")
        return float(value)

    @staticmethod
    def _timestamp(value: float | None) -> float | None:
        if value is None:
            return None
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("expires_at must be a finite monotonic timestamp")
        return float(value)

    def _now(self, now: float | None) -> float:
        timestamp = self._clock() if now is None else now
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp)
        ):
            raise ValueError("now must be a finite monotonic timestamp")
        return float(timestamp)

    def set_layer(
        self,
        source_id: str,
        name: str,
        priority: int,
        color: tuple[int, int, int] | list[int],
        *,
        opacity: float = 1.0,
        blend_mode: BlendMode = "replace",
        expires_at: float | None = None,
        fade_out_seconds: float = 0.0,
    ) -> Layer:
        """Create or replace a source-owned layer and return its snapshot."""
        source_id = self._text(source_id, "source_id")
        name = self._text(name, "name")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ValueError("priority must be an integer")
        if blend_mode not in ("replace", "alpha", "add"):
            raise ValueError("blend_mode must be replace, alpha, or add")
        layer = Layer(
            source_id,
            name,
            priority,
            self._rgb(color),
            self._unit(opacity, "opacity"),
            blend_mode,
            self._timestamp(expires_at),
            self._seconds(fade_out_seconds, "fade_out_seconds"),
        )
        with self._lock:
            self._sequence += 1
            layer = replace(layer, _updated=self._sequence)
            self._layers[(source_id, name)] = layer
            return layer

    update_layer = set_layer

    def upsert(
        self,
        source_id: str,
        layer_id: str,
        *,
        color: tuple[int, int, int] | list[int],
        priority: int = 0,
        opacity: float = 1.0,
        blend_mode: BlendMode = "replace",
        expires_at: float | None = None,
        fade_out_seconds: float = 0.0,
    ) -> Layer:
        return self.set_layer(
            source_id,
            layer_id,
            priority,
            color,
            opacity=opacity,
            blend_mode=blend_mode,
            expires_at=expires_at,
            fade_out_seconds=fade_out_seconds,
        )

    def remove_layer(self, source_id: str, name: str) -> bool:
        key = (self._text(source_id, "source_id"), self._text(name, "name"))
        with self._lock:
            return self._layers.pop(key, None) is not None

    def remove_source(self, source_id: str) -> int:
        source_id = self._text(source_id, "source_id")
        with self._lock:
            keys = [key for key in self._layers if key[0] == source_id]
            for key in keys:
                del self._layers[key]
            return len(keys)

    remove = remove_layer
    clear_source = remove_source

    def clear(self) -> int:
        """Remove every layer and return the number removed."""
        with self._lock:
            count = len(self._layers)
            self._layers.clear()
            return count

    def _active(self, now: float) -> list[Layer]:
        expired = [
            key
            for key, layer in self._layers.items()
            if layer.expires_at is not None and now >= layer.expires_at
        ]
        for key in expired:
            del self._layers[key]
        return sorted(self._layers.values(), key=lambda layer: (layer.priority, layer._updated))

    def snapshot(self, now: float | None = None) -> list[dict[str, object]]:
        timestamp = self._now(now)
        with self._lock:
            return [
                {
                    "source_id": layer.source_id,
                    "layer_id": layer.name,
                    "priority": layer.priority,
                    "color": layer.color,
                    "opacity": layer.opacity,
                    "blend_mode": layer.blend_mode,
                    "expires_at": layer.expires_at,
                    "fade_out_seconds": layer.fade_out_seconds,
                }
                for layer in self._active(float(timestamp))
            ]

    list_layers = snapshot

    def __len__(self) -> int:
        with self._lock:
            return len(self._layers)

    def compose(self, now: float | None = None) -> tuple[int, int, int] | None:
        timestamp = self._now(now)
        with self._lock:
            layers = self._active(float(timestamp))
        if not layers:
            return None
        output = (0.0, 0.0, 0.0)
        for layer in layers:
            opacity = layer.opacity
            if layer.expires_at is not None and layer.fade_out_seconds:
                opacity *= max(
                    0.0,
                    min(1.0, (layer.expires_at - timestamp) / layer.fade_out_seconds),
                )
            color = tuple(float(value) for value in layer.color)
            if layer.blend_mode in ("replace", "alpha"):
                output = tuple(
                    source * opacity + current * (1.0 - opacity)
                    for current, source in zip(output, color, strict=True)
                )
            else:
                output = tuple(
                    min(255.0, current + source * opacity)
                    for current, source in zip(output, color, strict=True)
                )
        return tuple(round(max(0.0, min(255.0, value))) for value in output)


LayerCompositor = GlobalLayerCompositor

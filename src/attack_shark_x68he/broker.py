"""Multi-client broker for the capture-proven global-colour lighting path."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from .layers import LayerCompositor
from .streaming import StreamLease, StreamOwners


async def _blocking_call(function: Any, *args: Any) -> Any:
    """Finish a dispatched blocking call before propagating task cancellation."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        with suppress(Exception):
            await asyncio.shield(task)
        raise


class GlobalLayerSession:
    """Own one device while global-colour layers are active."""

    def __init__(self, device_id: str, owners: StreamOwners, manager: Any) -> None:
        self.device_id = device_id
        self._owners = owners
        self._manager = manager
        self._compositor = LayerCompositor()
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._lease: StreamLease | None = None
        self._device: Any = None
        self._last_error: str | None = None
        self._closed = False

    async def upsert(
        self,
        device: Any,
        source_id: str,
        layer_id: str,
        *,
        color: tuple[int, int, int],
        priority: int,
        opacity: float,
        blend_mode: str,
        expires_at: float | None,
        fade_out_seconds: float,
    ) -> dict[str, Any]:
        async with self._lock:
            if self._closed:
                raise RuntimeError("layer broker is shutting down")
            if self._task is not None and self._task.done():
                await self._release_locked(self._task)
            if self._task is None:
                await self._acquire_locked(device)
            self._compositor.upsert(
                source_id,
                layer_id,
                color=color,
                priority=priority,
                opacity=opacity,
                blend_mode=blend_mode,
                expires_at=expires_at,
                fade_out_seconds=fade_out_seconds,
            )
            self._last_error = None
            self._wake.set()
            return self.status()

    async def remove(self, source_id: str, layer_id: str) -> tuple[bool, dict[str, Any]]:
        async with self._lock:
            removed = self._compositor.remove(source_id, layer_id)
            if len(self._compositor) == 0:
                await self._release_locked(self._task, report_restore_error=True)
            else:
                self._wake.set()
            return removed, self.status()

    async def clear_source(self, source_id: str) -> tuple[int, dict[str, Any]]:
        async with self._lock:
            removed = self._compositor.clear_source(source_id)
            if len(self._compositor) == 0:
                await self._release_locked(self._task, report_restore_error=True)
            else:
                self._wake.set()
            return removed, self.status()

    def status(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "active": self._task is not None and not self._task.done(),
            "output": self._compositor.compose(),
            "layers": self._compositor.snapshot(),
            "last_error": self._last_error,
            "max_frame_rate": 20,
            "scope": "global_color",
        }

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            self._compositor.clear()
            await self._release_locked(self._task)

    async def _acquire_locked(self, device: Any) -> None:
        capabilities = getattr(device, "capabilities", {}) or {}
        if not capabilities.get("global_color_streaming", False):
            raise NotImplementedError("global colour layering is unsupported")
        lease = await self._owners.acquire(self.device_id, self)
        try:
            await _blocking_call(device.acquire_global_stream)
        except BaseException:
            release = getattr(device, "release_global_stream", None)
            if not callable(release):
                release = getattr(device, "release_stream", None)
            if callable(release):
                with suppress(Exception):
                    await _blocking_call(release)
            await asyncio.shield(self._owners.release(lease))
            raise
        self._device = device
        self._lease = lease
        self._wake.set()
        self._task = asyncio.create_task(
            self._write_loop(), name=f"x68he-global-layers-{self.device_id}"
        )

    async def _write_loop(self) -> None:
        task = asyncio.current_task()
        last_color: tuple[int, int, int] | None = None
        try:
            while True:
                color = self._compositor.compose()
                if color is None:
                    asyncio.create_task(self._cleanup_completed_writer(task))
                    return
                if color != last_color:
                    await _blocking_call(self._device.set_global_color, color)
                    last_color = color
                self._wake.clear()
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=1 / 20)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._last_error = str(exc)
            asyncio.create_task(self._cleanup_completed_writer(task, failed=True))

    async def _cleanup_completed_writer(
        self, task: asyncio.Task[None] | None, *, failed: bool = False
    ) -> None:
        async with self._lock:
            if self._task is task:
                if failed:
                    self._compositor.clear()
                await self._release_locked(task)
        if failed:
            invalidate = getattr(self._manager, "invalidate", None)
            if callable(invalidate):
                with suppress(Exception):
                    await _blocking_call(invalidate, self.device_id)

    async def _release_locked(
        self, task: asyncio.Task[None] | None, *, report_restore_error: bool = False
    ) -> None:
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        device, lease = self._device, self._lease
        self._task = None
        self._device = None
        self._lease = None
        restore_error: Exception | None = None
        if device is not None:
            release = getattr(device, "release_global_stream", None)
            if not callable(release):
                release = getattr(device, "release_stream", None)
            if callable(release):
                try:
                    await _blocking_call(release)
                except asyncio.CancelledError:
                    if lease is not None:
                        await asyncio.shield(self._owners.release(lease))
                    raise
                except Exception as exc:
                    restore_error = exc
                    self._last_error = f"failed to restore lighting state: {exc}"
        if lease is not None:
            await asyncio.shield(self._owners.release(lease))
        if restore_error is not None and report_restore_error:
            raise OSError(self._last_error) from restore_error


class GlobalLayerBroker:
    """Create persistent device sessions and compose layers from multiple applications."""

    def __init__(self, manager: Any, owners: StreamOwners) -> None:
        self._manager = manager
        self._owners = owners
        self._sessions: dict[str, GlobalLayerSession] = {}

    def session(self, device_id: str) -> GlobalLayerSession:
        session = self._sessions.get(device_id)
        if session is None:
            session = GlobalLayerSession(device_id, self._owners, self._manager)
            self._sessions[device_id] = session
        return session

    async def close(self) -> None:
        sessions = tuple(self._sessions.values())
        await asyncio.gather(*(session.close() for session in sessions), return_exceptions=True)

"""Concurrency primitives used by the localhost lighting service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


class DeviceBusyError(RuntimeError):
    """Raised when another client owns a device stream."""


class LatestFrameQueue:
    """A bounded queue which retains the newest frame and drops stale frames."""

    def __init__(self, maxsize: int = 1) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be positive")
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=maxsize)

    def put_nowait(self, frame: bytes) -> None:
        try:
            self._queue.put_nowait(bytes(frame))
        except asyncio.QueueFull:
            self._queue.get_nowait()
            self._queue.task_done()
            self._queue.put_nowait(bytes(frame))

    async def get(self) -> bytes:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()

    def clear(self) -> None:
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()


@dataclass
class StreamLease:
    device_id: str
    owner: object
    previous_state: Any = None


class StreamOwners:
    """Process-local ownership registry; one active stream per device."""

    def __init__(self) -> None:
        self._leases: dict[str, StreamLease] = {}
        self._lock = asyncio.Lock()

    async def acquire(
        self, device_id: str, owner: object, previous_state: Any = None
    ) -> StreamLease:
        async with self._lock:
            if device_id in self._leases:
                raise DeviceBusyError(f"device {device_id} is already streaming")
            lease = StreamLease(device_id, owner, previous_state)
            self._leases[device_id] = lease
            return lease

    async def release(self, lease: StreamLease) -> None:
        async with self._lock:
            if self._leases.get(lease.device_id) is lease:
                del self._leases[lease.device_id]

    def owner(self, device_id: str) -> object | None:
        lease = self._leases.get(device_id)
        return None if lease is None else lease.owner

import asyncio

import pytest

from attack_shark_x68he.streaming import DeviceBusyError, LatestFrameQueue, StreamOwners


def test_latest_queue_drops_oldest():
    async def run():
        queue = LatestFrameQueue(1)
        queue.put_nowait(b"old")
        queue.put_nowait(b"new")
        assert await queue.get() == b"new"

    asyncio.run(run())


def test_one_owner_per_device():
    async def run():
        owners = StreamOwners()
        first = await owners.acquire("x", "a")
        with pytest.raises(DeviceBusyError):
            await owners.acquire("x", "b")
        await owners.release(first)
        assert await owners.acquire("x", "b")

    asyncio.run(run())

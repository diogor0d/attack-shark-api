"""Exercise the localhost global-colour WebSocket at a bounded frame rate."""

from __future__ import annotations

import argparse
import asyncio
import colorsys
import json
import math
import sys
import time
from typing import Any

import websockets


def positive_number(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return number


def parse_message(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("server returned a non-object message")
    return value


def rainbow(frame_index: int, fps: int) -> bytes:
    hue = ((frame_index / fps) / 6) % 1
    return bytes(round(channel * 255) for channel in colorsys.hsv_to_rgb(hue, 1, 1))


async def soak(url: str, fps: int, duration: float, progress_interval: float) -> dict[str, Any]:
    frame_count = max(1, math.ceil(fps * duration))
    async with websockets.connect(url, max_size=64 * 1024) as socket:
        metadata = parse_message(await socket.recv())
        if metadata.get("type") != "metadata":
            raise RuntimeError(f"expected metadata, received: {metadata}")
        maximum = int(metadata.get("max_frame_rate", 0))
        if fps > maximum:
            raise RuntimeError(f"requested {fps} FPS exceeds server maximum {maximum}")

        started = time.monotonic()
        next_progress = progress_interval
        for frame_index in range(frame_count):
            await socket.send(rainbow(frame_index, fps))
            sent = frame_index + 1
            remaining = started + sent / fps - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(remaining)
            elapsed = time.monotonic() - started
            if elapsed >= next_progress:
                print(
                    f"progress elapsed={elapsed:.1f}s frames={sent}/{frame_count}",
                    file=sys.stderr,
                    flush=True,
                )
                next_progress += progress_interval

        await socket.send(json.dumps({"type": "release"}))
        while True:
            message = parse_message(await asyncio.wait_for(socket.recv(), timeout=5))
            if message.get("type") == "error" or "error" in message:
                raise RuntimeError(str(message.get("error", message)))
            if message.get("type") == "released":
                break

    elapsed = time.monotonic() - started
    return {
        "ok": True,
        "url": url,
        "fps": fps,
        "duration_seconds": duration,
        "frames_sent": frame_count,
        "elapsed_seconds": round(elapsed, 3),
        "released": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="ws://127.0.0.1:8768/v1/devices/x68he/lighting/global-stream",
    )
    parser.add_argument("--fps", type=int, choices=range(1, 21), default=20)
    parser.add_argument("--duration", type=positive_number, default=900.0, metavar="SECONDS")
    parser.add_argument(
        "--progress-interval", type=positive_number, default=30.0, metavar="SECONDS"
    )
    args = parser.parse_args()
    try:
        result = asyncio.run(soak(args.url, args.fps, args.duration, args.progress_interval))
    except (OSError, RuntimeError, TimeoutError, websockets.WebSocketException) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "interrupted": True}), file=sys.stderr)
        return 130
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

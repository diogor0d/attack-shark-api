"""Command-line entry point for the X68HE service."""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import time
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from typing import Any

from .controller import PRESET_MODES, create_manager
from .errors import DeviceBusyError
from .ownership import named_mutex


def _positive_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("duration must be a number") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("duration must be greater than zero")
    return seconds


def run_global_demo(
    device: Any,
    fps: int,
    duration: float,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Run a bounded hue cycle and restore the state captured on acquisition."""
    if not 1 <= fps <= 20:
        raise ValueError("fps must be in range 1..20")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration must be greater than zero")

    frame_count = max(1, math.ceil(fps * duration))
    device.acquire_global_stream()
    started = monotonic()
    frames_sent = 0
    try:
        for frame_index in range(frame_count):
            hue = ((frame_index / fps) / 6) % 1
            rgb = tuple(round(channel * 255) for channel in colorsys.hsv_to_rgb(hue, 1, 1))
            device.set_global_color(rgb)
            frames_sent += 1
            remaining = started + frames_sent / fps - monotonic()
            if remaining > 0:
                sleep(remaining)
    finally:
        device.release_global_stream()

    return {
        "ok": True,
        "mode": "global_color",
        "pattern": "hue_cycle",
        "fps": fps,
        "duration_seconds": duration,
        "frames_sent": frames_sent,
        "restored": True,
        "elapsed_seconds": round(monotonic() - started, 3),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="x68ctl")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("probe", help="read device identity and capabilities")

    preset = subcommands.add_parser("set-preset", help="set a safe built-in lighting mode")
    preset.add_argument("mode", choices=tuple(PRESET_MODES))
    preset.add_argument("--color", metavar="#RRGGBB")
    preset.add_argument("--brightness", type=int, choices=range(5), default=4)
    preset.add_argument("--speed", type=int, choices=range(5), default=2)
    preset.add_argument("--option", type=int, choices=range(16), default=0)

    demo = subcommands.add_parser(
        "demo", help="run a bounded whole-keyboard hue cycle and restore prior lighting"
    )
    demo.add_argument("--fps", type=int, choices=range(1, 21), default=10)
    demo.add_argument("--duration", type=_positive_seconds, default=10.0, metavar="SECONDS")

    serve = subcommands.add_parser("serve", help="start the localhost API")
    serve.add_argument("--port", type=int, default=8768)
    return parser


def _json_default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return vars(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manager = create_manager()
    if args.command == "serve":
        import uvicorn

        from .api import create_app

        try:
            with named_mutex("Global\\AttackSharkX68HE-API"):
                uvicorn.run(create_app(manager), host="127.0.0.1", port=args.port)
            return 0
        except DeviceBusyError as exc:
            print(json.dumps({"error": str(exc)}))
            return 1
        finally:
            manager.close()

    devices = manager.list_devices()
    if not devices:
        print(json.dumps({"devices": [], "error": manager.last_error}, indent=2))
        return 1
    device = devices[0]
    try:
        if args.command == "probe":
            from .api import _metadata
            from .streaming import StreamOwners

            print(json.dumps(_metadata(device, StreamOwners()), default=_json_default, indent=2))
            return 0
        if args.command == "set-preset":
            device.set_preset(
                {
                    "mode": args.mode,
                    "color": args.color,
                    "brightness": args.brightness,
                    "speed": args.speed,
                    "option": args.option,
                }
            )
            return 0
        if args.command == "demo":
            try:
                result = run_global_demo(device, args.fps, args.duration)
            except KeyboardInterrupt:
                print(json.dumps({"ok": False, "interrupted": True, "restored": True}))
                return 130
            print(json.dumps(result, indent=2))
            return 0
        return 2
    finally:
        manager.close()


if __name__ == "__main__":
    raise SystemExit(main())

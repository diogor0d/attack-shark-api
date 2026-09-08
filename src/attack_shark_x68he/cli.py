"""Command-line entry point for the X68HE service."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from typing import Any

from .controller import PRESET_MODES, create_manager


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

    demo = subcommands.add_parser("demo", help="run a volatile streaming demo when supported")
    demo.add_argument("--fps", type=int, choices=range(1, 31), default=10)

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

        uvicorn.run(create_app(manager), host="127.0.0.1", port=args.port)
        return 0

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
            print("demo requires a capture-verified volatile streaming encoder")
            return 2
        return 2
    finally:
        manager.close()


if __name__ == "__main__":
    raise SystemExit(main())

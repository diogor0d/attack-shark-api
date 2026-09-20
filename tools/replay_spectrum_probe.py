"""Replay sanitized mode-22 spectrum bodies for physical-response research."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time

from attack_shark_x68he.controller import create_manager

# Dominant 32-bin bodies from the controlled 2026-09-20 frequency capture.
CAPTURED_PROFILES = {
    "110 Hz": "0002060601000000000000000000000000000000000000000000000000000000",
    "220 Hz": "0000000106060300000000000000000000000000000000000000000000000000",
    "440 Hz": "0000000000000000020606010000000000000000000000000000000000000000",
    "880 Hz": "0000000000000000000000000000000000010606030000000000000000000000",
}
SILENCE = (0,) * 32


def _bounded_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or not 0.1 <= parsed <= 10:
        raise argparse.ArgumentTypeError("value must be in range 0.1..10")
    return parsed


def _bins(value: str) -> tuple[int, ...]:
    try:
        bins = tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bins must be comma-separated integers") from exc
    if not bins or len(set(bins)) != len(bins) or any(not 0 <= item < 32 for item in bins):
        raise argparse.ArgumentTypeError("bins must be unique integers in range 0..31")
    return bins


def _profiles(
    bins: tuple[int, ...] | None, band_starts: tuple[int, ...] | None = None
) -> dict[str, tuple[int, ...]]:
    if bins is None and band_starts is None:
        return {name: tuple(bytes.fromhex(body)) for name, body in CAPTURED_PROFILES.items()}
    profiles = {}
    if bins is not None:
        for index in bins:
            levels = [0] * 32
            levels[index] = 6
            profiles[f"bin {index}"] = tuple(levels)
    if band_starts is not None:
        for start in band_starts:
            if start > 28:
                raise argparse.ArgumentTypeError("band starts must be in range 0..28")
            levels = [0] * 32
            levels[start : start + 4] = [1, 6, 6, 1]
            profiles[f"band {start}-{start + 3}"] = tuple(levels)
    return profiles


def _send_for(device, levels: tuple[int, ...], seconds: float, fps: int) -> int:
    frames = max(1, math.ceil(seconds * fps))
    started = time.monotonic()
    for index in range(frames):
        device.set_audio_spectrum(levels)
        remaining = started + (index + 1) / fps - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
    return frames


def _send_interactive(device, profiles: dict[str, tuple[int, ...]], fps: int) -> tuple[int, bool]:
    """Keep each profile alive until the local console user advances it."""
    try:
        import msvcrt
    except ImportError as exc:  # pragma: no cover - this toolkit is Windows-only
        raise RuntimeError("interactive mode requires Windows") from exc

    frames = 0
    interrupted = False
    print("Press Enter for the next pattern; press Q to finish and restore lighting.")
    for position, (name, levels) in enumerate(profiles.items(), start=1):
        print(f"\n[{position}/{len(profiles)}] ACTIVE: {name}", flush=True)
        while True:
            started = time.monotonic()
            device.set_audio_spectrum(levels)
            frames += 1
            while msvcrt.kbhit():
                key = msvcrt.getwch().lower()
                if key == "q":
                    interrupted = True
                    break
                if key == "\r":
                    break
            else:
                remaining = started + 1 / fps - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
                continue
            break
        if interrupted:
            break
        _send_for(device, SILENCE, 0.5, fps)
    return frames, interrupted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fps", type=int, choices=range(1, 21), default=10)
    parser.add_argument("--hold", type=_bounded_float, default=1.5, metavar="SECONDS")
    parser.add_argument("--gap", type=_bounded_float, default=0.5, metavar="SECONDS")
    pattern = parser.add_mutually_exclusive_group()
    pattern.add_argument(
        "--bins",
        type=_bins,
        metavar="N,N,...",
        help="replay one observed-range level-6 bin at a time instead of captured tones",
    )
    pattern.add_argument(
        "--bands",
        type=_bins,
        metavar="START,START,...",
        help="replay captured-width 1,6,6,1 bands; each start must be in range 0..28",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="hold each selected pattern until Enter is pressed in this console",
    )
    args = parser.parse_args()
    profiles = _profiles(args.bins, args.bands)

    manager = create_manager()
    devices = manager.list_devices()
    if not devices:
        print(json.dumps({"ok": False, "error": manager.last_error}), file=sys.stderr)
        return 1

    device = devices[0]
    frames_sent = 0
    restored = False
    interrupted = False
    try:
        device.acquire_audio_probe()
        try:
            if args.interactive:
                frames_sent, interrupted = _send_interactive(device, profiles, args.fps)
            else:
                for name, levels in profiles.items():
                    print(f"Replaying {name}", flush=True)
                    frames_sent += _send_for(device, levels, args.hold, args.fps)
                    frames_sent += _send_for(device, SILENCE, args.gap, args.fps)
        finally:
            device.release_audio_probe()
            restored = True
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "interrupted": True, "restored": restored}))
        return 130
    finally:
        manager.close()

    print(
        json.dumps(
            {
                "ok": True,
                "profiles": list(profiles),
                "fps": args.fps,
                "frames_sent": frames_sent,
                "stopped_early": interrupted,
                "restored": restored,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

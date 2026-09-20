"""Persistent safety guard for flash-backed USERPIC writes."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .errors import UnsafeCommandError

MIN_WRITE_INTERVAL_SECONDS = 600.0


@dataclass(frozen=True)
class FlashDecision:
    digest: str
    unchanged: bool


def default_guard_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return root / "AttackSharkX68HE" / "flash-guard.json"


def pattern_bytes(colors: tuple[tuple[int, int, int], ...]) -> bytes:
    return bytes(component for color in colors for component in color)


def check_flash_write(
    colors: tuple[tuple[int, int, int], ...],
    *,
    confirmed: bool,
    path: Path | None = None,
    now: float | None = None,
) -> FlashDecision:
    if not confirmed:
        raise UnsafeCommandError("flash-backed custom patterns require explicit confirmation")
    digest = hashlib.sha256(pattern_bytes(colors)).hexdigest()
    guard_path = path or default_guard_path()
    timestamp = time.time() if now is None else now
    try:
        state = json.loads(guard_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        state = {}
    if state.get("sha256") == digest:
        return FlashDecision(digest, True)
    last_write = state.get("written_at")
    if isinstance(last_write, (int, float)) and timestamp - last_write < MIN_WRITE_INTERVAL_SECONDS:
        remaining = MIN_WRITE_INTERVAL_SECONDS - (timestamp - last_write)
        raise UnsafeCommandError(f"wait {remaining:.1f}s before another custom-pattern write")
    return FlashDecision(digest, False)


def record_flash_write(
    decision: FlashDecision, *, path: Path | None = None, now: float | None = None
) -> None:
    guard_path = path or default_guard_path()
    guard_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.time() if now is None else now
    temporary = guard_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"sha256": decision.digest, "written_at": timestamp}, indent=2),
        encoding="utf-8",
    )
    temporary.replace(guard_path)

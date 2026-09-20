"""Optional hidapi transport; importing the package never requires hidapi."""

from collections.abc import Iterable
from typing import Any

from .errors import DeviceBusyError, DeviceNotFoundError, UnsafeCommandError
from .models import PID, VID
from .protocol import (
    ALLOWED_OPCODES,
    FLASH_USERPIC,
    SET_AUDIO,
    validate_audio_report,
    validate_userpic_report,
)

INTERFACE_NUMBER = 2
USAGE_PAGE, USAGE = 0xFFFF, 2


class HidTransport:
    def __init__(self, handle: Any):
        self.handle = handle

    @classmethod
    def discover(cls) -> Iterable[dict[str, Any]]:
        try:
            import hid
        except ImportError as exc:
            raise RuntimeError("install hidapi to access the keyboard") from exc
        return (
            d
            for d in hid.enumerate(VID, PID)
            if d.get("interface_number") == INTERFACE_NUMBER
            and d.get("usage_page") == USAGE_PAGE
            and d.get("usage") == USAGE
        )

    @classmethod
    def open(cls) -> "HidTransport":
        devices = list(cls.discover())
        if not devices:
            raise DeviceNotFoundError("X68HE vendor HID interface was not found")
        try:
            import hid

            handle = hid.device()
            handle.open_path(devices[0]["path"])
            handle.set_nonblocking(0)
            return cls(handle)
        except OSError as exc:
            raise DeviceBusyError(
                "X68HE HID interface could not be opened; close other lighting software"
            ) from exc

    def write(self, report: bytes) -> int:
        if len(report) != 64:
            raise ValueError("protocol reports must contain 64 payload bytes")
        if report[0] not in ALLOWED_OPCODES:
            raise UnsafeCommandError(f"opcode 0x{report[0]:02X} is not allowlisted")
        if report[0] == SET_AUDIO:
            validate_audio_report(report)
        if report[0] == FLASH_USERPIC:
            validate_userpic_report(report)
        return self.handle.send_feature_report(bytes([0]) + report)

    def read(self, length: int = 64, timeout_ms: int = 500) -> bytes:
        raw = bytes(self.handle.get_feature_report(0, length + 1))
        if len(raw) == length + 1 and raw[0] == 0:
            raw = raw[1:]
        if len(raw) != length:
            raise ValueError("hidapi returned an invalid feature report length")
        return raw

    def close(self) -> None:
        self.handle.close()

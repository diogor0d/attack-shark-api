"""Conservative ROYUAN/X68HE report construction and parsing."""

from .errors import ProtocolError, UnsafeCommandError
from .models import ALLOWED_INTERNAL_IDS, LightingState

REPORT_SIZE = 64
GET_IDENTIFY, GET_REVISION, GET_LIGHT = 0x8F, 0x80, 0x87
SET_LIGHT = 0x07
SET_SCREEN_COLOR = 0x0E
FLASH_USERPIC = 0x0C
ALLOWED_OPCODES = frozenset({GET_IDENTIFY, GET_REVISION, GET_LIGHT, SET_LIGHT, SET_SCREEN_COLOR})


def checksum7(packet: bytes) -> int:
    return 0xFF - (sum(packet[:7]) & 0xFF)


def checksum8(packet: bytes) -> int:
    return 0xFF - (sum(packet[:8]) & 0xFF)


def _report(values: bytes) -> bytes:
    if len(values) > REPORT_SIZE:
        raise ProtocolError("report exceeds 64 bytes")
    return values + bytes(REPORT_SIZE - len(values))


def encode_get(opcode: int) -> bytes:
    if opcode not in {GET_IDENTIFY, GET_REVISION, GET_LIGHT}:
        raise UnsafeCommandError(f"read opcode 0x{opcode:02X} is not allowlisted")
    p = bytearray(REPORT_SIZE)
    p[0] = opcode
    p[7] = checksum7(p)
    return bytes(p)


def encode_light_preset(state: LightingState, *, identified: bool) -> bytes:
    if not identified:
        raise UnsafeCommandError("device identification is required before writes")
    if (
        not 0 <= state.mode <= 255
        or not 0 <= state.speed <= 255
        or not 0 <= state.brightness <= 255
    ):
        raise ProtocolError("mode, speed, and brightness must be bytes")
    if not 0 <= state.option <= 15 or not 0 <= state.flags <= 15:
        raise ProtocolError("option and flags must be nibbles")
    if any(not 0 <= value <= 255 for value in state.rgb):
        raise ProtocolError("RGB must be bytes")
    p = bytearray(9)
    p[:8] = bytes(
        [
            SET_LIGHT,
            state.mode,
            state.speed,
            state.brightness,
            (state.option << 4) | state.flags,
            *state.rgb,
        ]
    )
    p[8] = checksum8(p)
    return _report(bytes(p))


def encode_screen_color(rgb: tuple[int, int, int], *, identified: bool) -> bytes:
    """Encode the volatile, whole-keyboard colour used by vendor mode 21."""
    if not identified:
        raise UnsafeCommandError("device identification is required before writes")
    if len(rgb) != 3 or any(not 0 <= value <= 255 for value in rgb):
        raise ProtocolError("RGB must contain three bytes")
    p = bytearray(8)
    p[:4] = bytes([SET_SCREEN_COLOR, *rgb])
    p[7] = checksum7(p)
    return _report(bytes(p))


def parse_identify(report: bytes) -> int:
    if len(report) < 5:
        raise ProtocolError("identification response is too short")
    return int.from_bytes(report[1:5], "little")


def validate_reply(report: bytes, expected_opcode: int) -> bytes:
    """Validate a normalized 64-byte reply and its echoed command opcode."""
    if len(report) != REPORT_SIZE:
        raise ProtocolError("reply must contain exactly 64 payload bytes")
    if report[0] != expected_opcode:
        raise ProtocolError(f"unexpected reply opcode 0x{report[0]:02X}")
    return report


def parse_revision(report: bytes) -> int:
    if len(report) < 3:
        raise ProtocolError("revision response is too short")
    return int.from_bytes(report[1:3], "little")


def parse_light_state(report: bytes) -> LightingState:
    if len(report) < 8:
        raise ProtocolError("lighting response is too short")
    return LightingState(
        report[1], report[2], report[3], report[4] >> 4, report[4] & 0xF, tuple(report[5:8])
    )


def validate_internal_id(value: int) -> int:
    if value not in ALLOWED_INTERNAL_IDS:
        raise ProtocolError(f"unsupported internal device ID: {value}")
    return value

"""Conservative ROYUAN/X68HE report construction and parsing."""

from collections.abc import Sequence

from .errors import ProtocolError, UnsafeCommandError
from .models import ALLOWED_INTERNAL_IDS, LightingState

REPORT_SIZE = 64
GET_IDENTIFY, GET_REVISION, GET_LIGHT = 0x8F, 0x80, 0x87
SET_LIGHT = 0x07
SET_AUDIO = 0x0D
SET_SCREEN_COLOR = 0x0E
FLASH_USERPIC = 0x0C
ALLOWED_OPCODES = frozenset(
    {
        GET_IDENTIFY,
        GET_REVISION,
        GET_LIGHT,
        SET_LIGHT,
        FLASH_USERPIC,
        SET_AUDIO,
        SET_SCREEN_COLOR,
    }
)


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


def encode_audio_spectrum(levels: Sequence[int], *, identified: bool) -> bytes:
    """Encode the captured volatile mode-22 spectrum report.

    The controlled frequency capture established 32 spectrum bins at report
    bytes 8 through 39. Only the observed firmware level range is accepted.
    """
    if not identified:
        raise UnsafeCommandError("device identification is required before writes")
    if len(levels) != 32:
        raise ProtocolError("audio spectrum must contain exactly 32 levels")
    if any(type(level) is not int or not 0 <= level <= 6 for level in levels):
        raise ProtocolError("audio spectrum levels must be integers in range 0..6")
    p = bytearray(REPORT_SIZE)
    p[0] = SET_AUDIO
    p[7] = checksum7(p)
    p[8:40] = bytes(levels)
    return bytes(p)


def validate_audio_report(report: bytes) -> bytes:
    """Apply the captured mode-22 shape as a second outbound safety boundary."""
    if len(report) != REPORT_SIZE or report[0] != SET_AUDIO:
        raise ProtocolError("audio report must be a 64-byte opcode 0x0D report")
    if any(report[1:7]) or report[7] != checksum7(report):
        raise ProtocolError("audio report header does not match the captured format")
    if any(level > 6 for level in report[8:40]) or any(report[40:]):
        raise ProtocolError("audio report body is outside the captured format")
    return report


def encode_userpic_pages(
    colors: Sequence[tuple[int, int, int]], *, identified: bool
) -> tuple[bytes, ...]:
    """Encode one complete gen2 USERPIC slot-0 upload.

    USERPIC is persistent flash storage. Callers must apply their own explicit
    confirmation, deduplication, and rate limit before transmitting these pages.
    """
    if not identified:
        raise UnsafeCommandError("device identification is required before writes")
    if len(colors) != 126:
        raise ProtocolError("USERPIC must contain exactly 126 RGB slots")
    if any(
        len(color) != 3
        or any(type(component) is not int or not 0 <= component <= 255 for component in color)
        for color in colors
    ):
        raise ProtocolError("USERPIC colors must contain three integer bytes")

    data = bytes(component for color in colors for component in color)
    pages = []
    for page in range(7):
        offset = page * 56
        length = 56 if page < 6 else 42
        report = bytearray(REPORT_SIZE)
        report[:7] = bytes([FLASH_USERPIC, 0, 0xFF, page, length, int(page == 6), 0])
        report[7] = checksum7(report)
        report[8 : 8 + length] = data[offset : offset + length]
        pages.append(bytes(report))
    return tuple(pages)


def validate_userpic_report(report: bytes) -> bytes:
    """Reject every USERPIC shape except the captured seven-page slot-0 upload."""
    if len(report) != REPORT_SIZE or report[0] != FLASH_USERPIC:
        raise ProtocolError("USERPIC report must be a 64-byte opcode 0x0C report")
    page = report[3]
    if report[1] != 0 or report[2] != 0xFF or page > 6 or report[6] != 0:
        raise ProtocolError("USERPIC header does not match the captured gen2 slot-0 format")
    expected_length = 56 if page < 6 else 42
    expected_final = int(page == 6)
    if report[4] != expected_length or report[5] != expected_final:
        raise ProtocolError("USERPIC page length or final flag is invalid")
    if report[7] != checksum7(report) or any(report[8 + expected_length :]):
        raise ProtocolError("USERPIC checksum or zero padding is invalid")
    return report


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

import pytest

from attack_shark_x68he.errors import ProtocolError, UnsafeCommandError
from attack_shark_x68he.models import LightingState
from attack_shark_x68he.protocol import (
    GET_LIGHT,
    GET_REVISION,
    checksum7,
    checksum8,
    encode_get,
    encode_light_preset,
    encode_screen_color,
    parse_identify,
    parse_revision,
    validate_internal_id,
    validate_reply,
)


def test_identify_and_revision_parsing():
    assert parse_identify(bytes([0x8F, 0xDE, 8, 0, 0])) == 2270
    assert parse_revision(bytes([0x80, 2, 1])) == 258


def test_get_report_is_checksummed_and_reply_echo_is_validated():
    report = encode_get(GET_LIGHT)
    assert report[0] == GET_LIGHT and report[7] == checksum7(report)
    assert validate_reply(bytes([GET_LIGHT]) + bytes(63), GET_LIGHT)[0] == GET_LIGHT
    with pytest.raises(ProtocolError):
        validate_reply(bytes([GET_REVISION]) + bytes(63), GET_LIGHT)


def test_preset_report_checksums_and_shape():
    report = encode_light_preset(LightingState(21, 3, 200, 2, 1, (1, 2, 3)), identified=True)
    assert len(report) == 64
    assert report[:8] == bytes([7, 21, 3, 200, 0x21, 1, 2, 3])
    assert report[8] == checksum8(report)


@pytest.mark.parametrize(
    ("state", "captured_prefix"),
    [
        (LightingState(1, 4, 4, 0, 7, (255, 0, 0)), "0701040407ff0000e9"),
        (LightingState(1, 4, 4, 0, 7, (0, 255, 0)), "070104040700ff00e9"),
        (LightingState(1, 4, 4, 0, 7, (0, 0, 255)), "07010404070000ffe9"),
        (LightingState(1, 4, 0, 0, 7, (250, 255, 250)), "0701040007fafffaf9"),
        (LightingState(1, 4, 4, 0, 7, (250, 255, 250)), "0701040407fafffaf5"),
    ],
)
def test_preset_reports_match_sanitized_vendor_capture(state, captured_prefix):
    report = encode_light_preset(state, identified=True)
    assert report[:9] == bytes.fromhex(captured_prefix)


@pytest.mark.parametrize(
    ("rgb", "captured_prefix"),
    [
        ((255, 0, 0), "0eff0000000000f2"),
        ((0, 255, 0), "0e00ff00000000f2"),
        ((0, 0, 255), "0e0000ff000000f2"),
        ((255, 255, 255), "0effffff000000f4"),
        ((0, 0, 0), "0e000000000000f1"),
    ],
)
def test_screen_color_reports_match_sanitized_mode21_capture(rgb, captured_prefix):
    report = encode_screen_color(rgb, identified=True)
    assert report[:8] == bytes.fromhex(captured_prefix)
    assert report[7] == checksum7(report)


def test_screen_color_requires_identification_and_byte_rgb():
    with pytest.raises(UnsafeCommandError):
        encode_screen_color((1, 2, 3), identified=False)
    with pytest.raises(ProtocolError):
        encode_screen_color((256, 0, 0), identified=True)


def test_writes_are_fail_closed():
    with pytest.raises(UnsafeCommandError):
        encode_light_preset(LightingState(1), identified=False)
    with pytest.raises(UnsafeCommandError):
        encode_get(0x0C)
    with pytest.raises(ProtocolError):
        encode_light_preset(LightingState(1, rgb=(256, 0, 0)), identified=True)


def test_only_known_ids_are_accepted():
    assert validate_internal_id(2270) == 2270
    with pytest.raises(ProtocolError):
        validate_internal_id(1234)

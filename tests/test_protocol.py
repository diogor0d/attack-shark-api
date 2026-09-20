import pytest

from attack_shark_x68he.errors import ProtocolError, UnsafeCommandError
from attack_shark_x68he.models import LightingState
from attack_shark_x68he.protocol import (
    GET_LIGHT,
    GET_REVISION,
    checksum7,
    checksum8,
    encode_audio_spectrum,
    encode_get,
    encode_light_preset,
    encode_screen_color,
    encode_userpic_pages,
    parse_identify,
    parse_revision,
    validate_audio_report,
    validate_internal_id,
    validate_reply,
    validate_userpic_report,
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


@pytest.mark.parametrize(
    "body",
    [
        "0002060601000000000000000000000000000000000000000000000000000000",
        "0000000106060300000000000000000000000000000000000000000000000000",
        "0000000000000000020606010000000000000000000000000000000000000000",
        "0000000000000000000000000000000000010606030000000000000000000000",
    ],
)
def test_audio_spectrum_reports_match_sanitized_frequency_capture(body):
    report = encode_audio_spectrum(tuple(bytes.fromhex(body)), identified=True)
    assert len(report) == 64
    assert report[:8] == bytes.fromhex("0d000000000000f2")
    assert report[8:40].hex() == body
    assert report[40:] == bytes(24)


def test_audio_spectrum_requires_identity_exact_length_and_captured_range():
    with pytest.raises(UnsafeCommandError):
        encode_audio_spectrum((0,) * 32, identified=False)
    with pytest.raises(ProtocolError):
        encode_audio_spectrum((0,) * 31, identified=True)
    with pytest.raises(ProtocolError):
        encode_audio_spectrum((0,) * 31 + (7,), identified=True)
    with pytest.raises(ProtocolError):
        encode_audio_spectrum((0,) * 31 + (True,), identified=True)


def test_audio_report_validator_rejects_non_captured_fields():
    valid = encode_audio_spectrum((0,) * 32, identified=True)
    assert validate_audio_report(valid) == valid
    invalid_header = bytearray(valid)
    invalid_header[1] = 1
    with pytest.raises(ProtocolError):
        validate_audio_report(bytes(invalid_header))
    invalid_trailer = bytearray(valid)
    invalid_trailer[40] = 1
    with pytest.raises(ProtocolError):
        validate_audio_report(bytes(invalid_trailer))


def test_userpic_pages_match_captured_headers_and_preserve_cross_page_rgb_data():
    colors = [(0, 0, 0)] * 126
    colors[1] = (255, 0, 0)
    colors[9] = (0, 255, 0)
    colors[41] = (0, 0, 255)
    colors[89] = (255, 255, 255)
    pages = encode_userpic_pages(tuple(colors), identified=True)

    assert [page[:8].hex() for page in pages] == [
        "0c00ff00380000bc",
        "0c00ff01380000bb",
        "0c00ff02380000ba",
        "0c00ff03380000b9",
        "0c00ff04380000b8",
        "0c00ff05380000b7",
        "0c00ff062a0100c3",
    ]
    rebuilt = b"".join(page[8 : 8 + page[4]] for page in pages)
    assert len(rebuilt) == 378
    assert rebuilt[3:6] == bytes.fromhex("ff0000")
    assert rebuilt[27:30] == bytes.fromhex("00ff00")
    assert rebuilt[123:126] == bytes.fromhex("0000ff")
    assert rebuilt[267:270] == bytes.fromhex("ffffff")
    assert all(validate_userpic_report(page) == page for page in pages)


def test_userpic_encoder_and_validator_fail_closed():
    with pytest.raises(UnsafeCommandError):
        encode_userpic_pages(((0, 0, 0),) * 126, identified=False)
    with pytest.raises(ProtocolError):
        encode_userpic_pages(((0, 0, 0),) * 125, identified=True)
    valid = encode_userpic_pages(((0, 0, 0),) * 126, identified=True)[-1]
    invalid = bytearray(valid)
    invalid[5] = 0
    with pytest.raises(ProtocolError):
        validate_userpic_report(bytes(invalid))


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

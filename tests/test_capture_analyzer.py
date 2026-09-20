import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import Mock


def load_analyzer():
    path = Path(__file__).parents[1] / "tools" / "analyze_capture.py"
    spec = spec_from_file_location("analyze_capture", path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_and_classify_bit8_packet() -> None:
    analyzer = load_analyzer()
    prefix = bytes([0x07, 1, 0, 4, 7, 255, 0, 0])
    payload = prefix + bytes([analyzer.checksum(prefix, 8)]) + bytes(55)

    result = analyzer.classify("12", "0.250", payload)

    assert result["opcode"] == "0x07"
    assert result["bit8_checksum_valid"] is True
    assert "prohibited" not in result


def test_classify_flags_flash_backed_userpic() -> None:
    analyzer = load_analyzer()
    result = analyzer.classify("3", "0.1", bytes([0x0C]) + bytes(63))

    assert result["prohibited"] == "flash-backed per-key pattern"


def test_classify_strips_hidapi_style_report_id() -> None:
    analyzer = load_analyzer()
    payload = bytes([0, 0x87]) + bytes(63)

    result = analyzer.classify("4", "0.2", payload)

    assert result["length"] == 64
    assert result["opcode"] == "0x87"


def test_extract_ignores_interrupt_hid_input_and_uses_control_payload(monkeypatch) -> None:
    analyzer = load_analyzer()
    capture = Path(__file__)
    feature = bytes.fromhex("0701040407ff0000e9") + bytes(55)
    # frame|time|src|dst|data_fragment|capdata|usbhid.data
    output = "\n".join(
        [
            "10|0.1|host|keyboard||01:00:04:00:00:00:00:00|01:00:04:00:00:00:00:00",
            "10|0.15|host|keyboard|01||",
            f"11|0.2|host|keyboard|{feature.hex()}||",
        ]
    )
    completed = Mock(stdout=output)
    monkeypatch.setattr(analyzer.shutil, "which", lambda _: str(Path(__file__)))
    monkeypatch.setattr(analyzer.subprocess, "run", Mock(return_value=completed))

    records = analyzer.extract(capture, 12)

    assert len(records) == 1
    assert records[0]["opcode"] == "0x07"
    assert records[0]["length"] == 64
    assert records[0]["bit8_checksum_valid"] is True
    assert records[0]["transfer"] == "control"
    assert "prohibited" not in records[0]


def test_summarize_payloads_reports_complete_32_byte_audio_body() -> None:
    analyzer = load_analyzer()
    reports = []
    for frame, body in enumerate((bytes(32), bytes([0, 3, 0, 9]) + bytes(28)), start=1):
        prefix = bytes([0x0D]) + bytes(6)
        payload = prefix + bytes([analyzer.checksum(prefix, 7)]) + body + bytes(24)
        reports.append(analyzer.classify(str(frame), str(frame / 10), payload))

    summary = analyzer.summarize_payloads(reports)["0x0D"]

    assert summary["count"] == 2
    assert summary["unique_payloads"] == 2
    assert summary["data_bytes_1_to_6_changed_positions"] == []
    assert summary["data_bytes_1_to_6_nonzero_positions"] == []
    assert summary["bytes_8_plus_changed_positions"] == [9, 11]
    assert summary["bytes_8_plus_nonzero_positions"] == [9, 11]
    assert len(summary["sample_prefixes"]) == 1
    assert len(summary["sample_bodies_8_to_39"]) == 2
    assert all(len(sample["body"]) == 64 for sample in summary["sample_bodies_8_to_39"])


def test_sanitized_frequency_fixture_records_32_bin_observations() -> None:
    fixture = Path(__file__).parent / "fixtures" / "mode22_spectrum_samples.json"
    samples = json.loads(fixture.read_text(encoding="utf-8"))

    assert [(sample["frequency_hz"], sample["peak_bin"]) for sample in samples] == [
        (110, 2),
        (220, 5),
        (440, 9),
        (880, 19),
    ]
    for sample in samples:
        body = bytes.fromhex(sample["observed_body_hex"])
        assert len(body) == 32
        assert max(body, default=0) <= 6
        assert 0 <= sample["peak_bin"] < 32

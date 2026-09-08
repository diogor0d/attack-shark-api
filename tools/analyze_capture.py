"""Extract and classify X68HE USB control payloads from a local packet capture."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

PROHIBITED_OPCODES = {
    0x01: "gen2 factory reset",
    0x0A: "keymap write",
    0x0B: "macro write",
    0x0C: "flash-backed per-key pattern",
    0x1C: "sensor calibration",
    0x1E: "sensor calibration",
    0x30: "display bootloader",
    0x65: "magnetic-switch settings",
    0x7F: "keyboard bootloader",
    0xAC: "flash erase",
}


def checksum(payload: bytes, covered: int) -> int:
    return 0xFF - (sum(payload[:covered]) & 0xFF)


def parse_hex_payload(value: str) -> bytes:
    compact = value.replace(":", "").replace(" ", "").replace("-", "")
    if not compact or len(compact) % 2:
        return b""
    try:
        return bytes.fromhex(compact)
    except ValueError:
        return b""


def classify(frame: str, timestamp: str, payload: bytes) -> dict[str, object]:
    if len(payload) == 65 and payload[0] == 0:
        payload = payload[1:]
    opcode = payload[0] if payload else None
    result: dict[str, object] = {
        "frame": int(frame),
        "time": float(timestamp),
        "length": len(payload),
        "opcode": f"0x{opcode:02X}" if opcode is not None else None,
        "payload": payload.hex(),
    }
    if opcode in PROHIBITED_OPCODES:
        result["prohibited"] = PROHIBITED_OPCODES[opcode]
    if len(payload) >= 8:
        result["bit7_checksum_valid"] = payload[7] == checksum(payload, 7)
    if len(payload) >= 9:
        result["bit8_checksum_valid"] = payload[8] == checksum(payload, 8)
    return result


def is_complete_feature_payload(payload: bytes) -> bool:
    """Return whether payload is a complete 64-byte feature report."""
    return len(payload) == 64 or (len(payload) == 65 and payload[0] == 0)


def extract(capture: Path, device_address: int) -> list[dict[str, object]]:
    tshark = shutil.which("tshark") or r"C:\Program Files\Wireshark\tshark.exe"
    if not Path(tshark).exists():
        raise RuntimeError("TShark was not found; install Wireshark or add tshark to PATH")
    # usb.data_fragment is the payload of a USB control transfer.  The vendor
    # driver sends lighting SET_REPORTs there, while ordinary keyboard and
    # mouse input is dissected as usbhid.data (and must be ignored).
    # usb.capdata remains a fallback for older/sanitized captures, but only
    # complete report-sized payloads are accepted from that field.
    display_filter = f"usb.device_address == {device_address} && (usb.data_fragment || usb.capdata)"
    command = [
        tshark,
        "-r",
        str(capture),
        "-Y",
        display_filter,
        "-T",
        "fields",
        "-E",
        "separator=|",
        "-e",
        "frame.number",
        "-e",
        "frame.time_relative",
        "-e",
        "usb.src",
        "-e",
        "usb.dst",
        "-e",
        "usb.data_fragment",
        "-e",
        "usb.capdata",
        "-e",
        "usbhid.data",
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    records: list[dict[str, object]] = []
    for line in completed.stdout.splitlines():
        parts = line.split("|", 6)
        if len(parts) != 7:
            continue
        data_fragment = parts[4]
        capdata = parts[5]
        # Do not fall back to usbhid.data: an 8-byte key report beginning with
        # 0x01 would otherwise look like the prohibited factory-reset opcode.
        if data_fragment:
            payload = parse_hex_payload(data_fragment.split(",", 1)[0])
        else:
            payload = parse_hex_payload(capdata.split(",", 1)[0])
        if not is_complete_feature_payload(payload):
            continue
        if payload:
            record = classify(parts[0], parts[1], payload)
            record["source"] = parts[2]
            record["destination"] = parts[3]
            record["transfer"] = "control" if data_fragment else "capture-data"
            records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--device-address", type=int, required=True)
    args = parser.parse_args()
    if not args.capture.is_file():
        parser.error(f"capture does not exist: {args.capture}")
    records = extract(args.capture, args.device_address)
    counts = Counter(record["opcode"] for record in records)
    prohibited = [record for record in records if "prohibited" in record]
    json.dump(
        {"records": records, "opcode_counts": counts, "prohibited_records": prohibited},
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")
    return 2 if prohibited else 0


if __name__ == "__main__":
    raise SystemExit(main())

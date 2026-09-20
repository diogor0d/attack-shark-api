"""Play deterministic tones separated by silence for mode-22 USB captures."""

from __future__ import annotations

import json
import math
import struct
import tempfile
import wave
import winsound
from pathlib import Path

SAMPLE_RATE = 48_000
AMPLITUDE = 0.25
LEAD_IN_SECONDS = 3
TONE_SECONDS = 3
SILENCE_SECONDS = 2
FREQUENCIES_HZ = (110, 220, 440, 880, 1760, 3520)


def append_silence(frames: bytearray, seconds: int) -> None:
    frames.extend(bytes(SAMPLE_RATE * seconds * 4))


def append_tone(frames: bytearray, frequency: int, seconds: int) -> None:
    for sample in range(SAMPLE_RATE * seconds):
        value = int(32767 * AMPLITUDE * math.sin(2 * math.pi * frequency * sample / SAMPLE_RATE))
        frames.extend(struct.pack("<hh", value, value))


def main() -> None:
    path = Path(tempfile.gettempdir()) / "x68he-frequency-sequence.wav"
    frames = bytearray()
    timeline: list[dict[str, int | str]] = []
    elapsed = 0

    append_silence(frames, LEAD_IN_SECONDS)
    timeline.append(
        {
            "event": "silence",
            "start_seconds": elapsed,
            "duration_seconds": LEAD_IN_SECONDS,
        }
    )
    elapsed += LEAD_IN_SECONDS
    for frequency in FREQUENCIES_HZ:
        append_tone(frames, frequency, TONE_SECONDS)
        timeline.append(
            {
                "event": "tone",
                "frequency_hz": frequency,
                "start_seconds": elapsed,
                "duration_seconds": TONE_SECONDS,
            }
        )
        elapsed += TONE_SECONDS
        append_silence(frames, SILENCE_SECONDS)
        timeline.append(
            {
                "event": "silence",
                "start_seconds": elapsed,
                "duration_seconds": SILENCE_SECONDS,
            }
        )
        elapsed += SILENCE_SECONDS

    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(frames)

    print(
        json.dumps({"wav": str(path), "duration_seconds": elapsed, "timeline": timeline}, indent=2)
    )
    winsound.PlaySound(str(path), winsound.SND_FILENAME)


if __name__ == "__main__":
    main()

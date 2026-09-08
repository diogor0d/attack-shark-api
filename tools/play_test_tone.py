"""Play a deterministic Windows test tone for music-mode USB captures."""

from __future__ import annotations

import math
import struct
import tempfile
import wave
import winsound
from pathlib import Path

SAMPLE_RATE = 48_000
DURATION_SECONDS = 5
FREQUENCY_HZ = 440
AMPLITUDE = 0.25


def main() -> None:
    path = Path(tempfile.gettempdir()) / "x68he-440hz-test-tone.wav"
    frames = bytearray()
    for sample in range(SAMPLE_RATE * DURATION_SECONDS):
        value = int(32767 * AMPLITUDE * math.sin(2 * math.pi * FREQUENCY_HZ * sample / SAMPLE_RATE))
        frames.extend(struct.pack("<hh", value, value))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(frames)
    print(f"TONE start frequency={FREQUENCY_HZ}Hz duration={DURATION_SECONDS}s", flush=True)
    winsound.PlaySound(str(path), winsound.SND_FILENAME)
    print("TONE complete", flush=True)


if __name__ == "__main__":
    main()

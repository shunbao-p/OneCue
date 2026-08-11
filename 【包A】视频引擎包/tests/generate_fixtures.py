# -*- coding: utf-8 -*-
"""以 Python 标准库确定性生成 Phase 0 的极小 PCM WAV 夹具。"""

import math
import struct
import wave
from pathlib import Path


FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_RATE = 8_000
AMPLITUDE = 8_000


def _tone(seconds, frequency):
    frames = int(round(seconds * SAMPLE_RATE))
    return b"".join(
        struct.pack("<h", int(AMPLITUDE * math.sin(2 * math.pi * frequency * i / SAMPLE_RATE)))
        for i in range(frames)
    )


def _silence(seconds):
    return b"\x00\x00" * int(round(seconds * SAMPLE_RATE))


def _write_wav(path, pcm):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm)


def main():
    FIXTURES.mkdir(parents=True, exist_ok=True)
    _write_wav(FIXTURES / "one_block.wav", _tone(1.2, 440.0))
    _write_wav(
        FIXTURES / "two_blocks.wav",
        _tone(0.30, 440.0) + _silence(0.25) + _tone(0.30, 660.0),
    )


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""为 Phase 2 实机验证生成指定时长的确定性 PCM WAV。"""

import argparse
import math
import struct
import wave
from pathlib import Path


def write_tone(path, duration, sample_rate=48_000, frequency=440.0):
    duration = float(duration)
    if duration <= 0:
        raise ValueError("时长必须大于 0")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(round(duration * sample_rate))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        block = bytearray()
        for index in range(frame_count):
            sample = int(7_500 * math.sin(2 * math.pi * frequency * index / sample_rate))
            block.extend(struct.pack("<h", sample))
            if len(block) >= 256 * 1024:
                output.writeframesraw(block)
                block.clear()
        if block:
            output.writeframesraw(block)
        output.writeframes(b"")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sample-rate", type=int, default=48_000)
    parser.add_argument("--frequency", type=float, default=440.0)
    args = parser.parse_args()
    result = write_tone(args.output, args.duration, args.sample_rate, args.frequency)
    print(result)


if __name__ == "__main__":
    main()

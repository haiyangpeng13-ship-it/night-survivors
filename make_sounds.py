"""Run this script on your computer to build sounds/ from nothing but Python.

    py -3.13 make_sounds.py

Every sound is a short mono 16-bit WAV written with the `wave` module: the numbers
in the file are simply the position of the speaker, sample by sample.
Standard library only. main.py never imports this file.
"""

import math
import pathlib
import random
import wave
from array import array

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "sounds"

RATE = 22050  # samples per second
LOUD = 12000  # how far the speaker moves (16-bit sound goes from -32768 to 32767)


def shape(samples):
    """Fade the first and last few milliseconds so the sound does not click."""
    edge = max(1, int(RATE * 0.004))
    last = len(samples) - 1
    return [
        value * min(1.0, min(index, last - index) / edge)
        for index, value in enumerate(samples)
    ]


def tone(seconds, from_hz, to_hz, square=False, decay=2.0):
    """One note that slides from `from_hz` to `to_hz` and gets quieter as it ends."""
    count = max(1, int(RATE * seconds))
    samples = []
    phase = 0.0
    for index in range(count):
        at = index / count
        hertz = from_hz + (to_hz - from_hz) * at
        phase += 2.0 * math.pi * hertz / RATE
        up = math.sin(phase)
        value = (1.0 if up >= 0 else -1.0) if square else up
        samples.append(LOUD * value * (1.0 - at) ** decay)
    return samples


def hiss(seconds, loud=LOUD, decay=3.0):
    """A short burst of random noise: good for hits and getting hurt."""
    rng = random.Random(4)
    count = max(1, int(RATE * seconds))
    return [
        loud * rng.uniform(-1.0, 1.0) * (1.0 - index / count) ** decay
        for index in range(count)
    ]


def mix(*parts):
    """Add sounds together, sample by sample, up to the loudest length."""
    longest = max(len(part) for part in parts)
    out = []
    for index in range(longest):
        total = 0.0
        for part in parts:
            if index < len(part):
                total += part[index]
        out.append(max(-LOUD, min(LOUD, total)))
    return out


def join(*parts):
    """Play sounds one after another."""
    out = []
    for part in parts:
        out.extend(part)
    return out


def write(name, samples):
    path = OUT / f"{name}.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(array("h", [round(v) for v in shape(samples)]).tobytes())
    return path


def build():
    OUT.mkdir(exist_ok=True)
    sounds = {
        # a small punch: noise plus a low square blip
        "hit": mix(hiss(0.05, loud=LOUD * 0.7), tone(0.06, 320.0, 180.0, square=True)),
        # a bright rising blip when a gem is picked up
        "gem": tone(0.09, 700.0, 1250.0),
        # four rising notes: you went up a level
        "level_up": join(
            *[tone(0.09, hertz, hertz, decay=1.0) for hertz in (523.0, 659.0, 784.0, 1046.0)]
        ),
        # a low wobble when the hero is hurt
        "hurt": mix(tone(0.18, 200.0, 90.0, square=True), hiss(0.08, loud=LOUD * 0.4)),
        # a falling two-note ending: the run is over
        "end": join(
            tone(0.18, 440.0, 440.0, decay=1.0), tone(0.4, 300.0, 90.0, decay=1.5)
        ),
    }
    for name, samples in sounds.items():
        path = write(name, samples)
        print(f"  {path.relative_to(ROOT)}  {len(samples) / RATE:.2f}s")


if __name__ == "__main__":
    print(f"writing short sounds to {OUT.name}/:")
    build()

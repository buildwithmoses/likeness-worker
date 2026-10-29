#!/usr/bin/env python3
"""Stick-channel narration on the Mac (Kokoro, default am_onyx at speed 0.93), one wav per script paragraph. Free.

    ~/.cache/likeness-tts/venv/bin/python tools/tts_kokoro.py pilots/stick-003-house-elf [voice] [speed]
Reads <pilot>/script.txt (paragraphs split by blank lines), writes <pilot>/voice/vo1.wav ...
Every line is voiced in the same voice and speed, so a re-voice never leaves a build half in one voice.
"""
import os, sys
import soundfile as sf
from kokoro_onnx import Kokoro

P = sys.argv[1]; C = os.path.expanduser("~/.cache/likeness-tts")
VOICE = sys.argv[2] if len(sys.argv) > 2 else "am_onyx"
SPEED = float(sys.argv[3]) if len(sys.argv) > 3 else 0.93
k = Kokoro(f"{C}/kokoro-v1.0.onnx", f"{C}/voices-v1.0.bin")
paras = [p.strip().replace("\n", " ") for p in open(f"{P}/script.txt").read().split("\n\n") if p.strip()]
os.makedirs(f"{P}/voice", exist_ok=True)
for f in os.listdir(f"{P}/voice"):   # a shorter script must not leave old lines behind in another voice
    if f.startswith("vo") and f.endswith(".wav"):
        os.remove(f"{P}/voice/{f}")
for i, text in enumerate(paras, 1):
    audio, sr = k.create(text, voice=VOICE, speed=SPEED, lang="en-us")
    sf.write(f"{P}/voice/vo{i}.wav", audio, sr); print(f"vo{i}: {len(audio) / sr:.1f}s ({VOICE} {SPEED})")

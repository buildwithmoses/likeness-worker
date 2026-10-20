#!/usr/bin/env python3
"""Stick-channel narration on the Mac (Kokoro am_onyx, speed 0.93), one wav per script paragraph. Free.

    ~/.cache/likeness-tts/venv/bin/python tools/tts_kokoro.py pilots/stick-003-house-elf
Reads <pilot>/script.txt (paragraphs split by blank lines), writes <pilot>/voice/vo1.wav ...
"""
import os, sys
import soundfile as sf
from kokoro_onnx import Kokoro

P = sys.argv[1]; C = os.path.expanduser("~/.cache/likeness-tts")
k = Kokoro(f"{C}/kokoro-v1.0.onnx", f"{C}/voices-v1.0.bin")
paras = [p.strip().replace("\n", " ") for p in open(f"{P}/script.txt").read().split("\n\n") if p.strip()]
os.makedirs(f"{P}/voice", exist_ok=True)
for i, text in enumerate(paras, 1):
    audio, sr = k.create(text, voice="am_onyx", speed=0.93, lang="en-us")
    sf.write(f"{P}/voice/vo{i}.wav", audio, sr); print(f"vo{i}: {len(audio) / sr:.1f}s")

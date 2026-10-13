#!/usr/bin/env python3
"""Assemble an animated pilot on the Mac: voice lines -> one track, animated clips cut to the narration
(fixed framing, no zoom: each clip is only scaled to 1280x720, stretched up to 1.35x or frame-held to fill
its slot), Nick-Invests-style phrase captions, loudness-normalised. No GPU, no cost.

    python3 assemble_clips.py pilots/finance-002-simpsons
"""
import json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

P = sys.argv[1]; plan = json.load(open(f"{P}/plan.json"))
OUT = "outputs"; pre = plan["prefix"]; work = f"{P}/build"; os.makedirs(work, exist_ok=True)
sh = lambda *a: subprocess.run(a, check=True, capture_output=True, text=True)
dur_of = lambda f: float(sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f).stdout)

# 1. voice
paras, t, starts = [], 0.0, []
for i in range(1, plan["n_vo"] + 1):
    src = sorted(f for f in os.listdir(OUT) if f.startswith(f"{pre}_vo{i}_{pre}_vo{i}_") and f.endswith(".flac"))[-1]
    wav = f"{work}/vo{i}.wav"; sh("ffmpeg", "-v", "error", "-y", "-i", f"{OUT}/{src}", "-ar", "48000", "-ac", "1", wav)
    starts.append(t); paras.append(wav); t += dur_of(wav) + plan["gap"]
total = t
sil = f"{work}/gap.wav"
sh("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", str(plan["gap"]), sil)
open(f"{work}/vo.txt", "w").write("".join(f"file '{os.path.abspath(p)}'\nfile '{os.path.abspath(sil)}'\n" for p in paras))
sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{work}/vo.txt", f"{work}/vo.wav")

# 2. word timings
sh("whisper", f"{work}/vo.wav", "--model", "base.en", "--word_timestamps", "True", "--output_format", "json", "--output_dir", work)
raw = [w for s in json.load(open(f"{work}/vo.json"))["segments"] for w in s.get("words", [])]
words = []
for w in raw:  # glue "$1" + ",000"
    if words and not w["word"].startswith(" "):
        words[-1] = {**words[-1], "word": words[-1]["word"] + w["word"], "end": w["end"]}
    else:
        words.append(dict(w))

def at(spec):
    para, cue = spec; t0 = starts[para - 1]
    if not cue: return max(0.0, t0 - 0.05)
    for w in words:
        if w["start"] >= t0 - 0.1 and w["word"].strip(" ,.?!").lower() == cue.lower():
            return w["start"] - 0.05
    raise SystemExit(f"cue {cue!r} not found in paragraph {para}")

cuts = [at(s["start"]) for s in plan["shots"]] + [total]
# 3. clips: scale to 1280x720 (no zoom), stretch <=1.35x then hold last frame to fill the slot
clips = []
for i, s in enumerate(plan["shots"]):
    src = sorted(f for f in os.listdir(OUT) if f.startswith(f"{pre}_anim_{s['clip']}_") and f.endswith(".mp4"))[-1]
    slot = cuts[i + 1] - cuts[i]; cd = dur_of(f"{OUT}/{src}")
    speed = min(max(slot / cd, 1.0), 1.35)
    c = f"{work}/clip{i:02d}.mp4"
    sh("ffmpeg", "-v", "error", "-y", "-i", f"{OUT}/{src}", "-vf",
       f"setpts={speed:.4f}*PTS,scale=1280:720:flags=lanczos,fps=30,tpad=stop_mode=clone:stop_duration=30,format=yuv420p",
       "-t", f"{slot:.3f}", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "17", c)
    clips.append(c)
open(f"{work}/clips.txt", "w").write("".join(f"file '{os.path.abspath(c)}'\n" for c in clips))
sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{work}/clips.txt", "-c", "copy", f"{work}/video.mp4")

# 4. captions like the reference: short phrases (<=7 words, break at punctuation), condensed bold white, black outline
font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", 38)
chunks, cur = [], []
for w in words:
    cur.append(w)
    if len(cur) >= 7 or w["word"].rstrip().endswith((".", "?", "!", ",")):
        chunks.append(cur); cur = []
if cur: chunks.append(cur)
caps = []
for ci, ch in enumerate(chunks):
    nxt = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else ch[-1]["end"] + 0.4
    txt = "".join(w["word"] for w in ch).strip().lower().rstrip(",")
    im = Image.new("RGBA", (1280, 90), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.text(((1280 - d.textlength(txt, font=font)) / 2, 20), txt, font=font, fill="white", stroke_width=3, stroke_fill="black")
    path = f"{work}/cap{ci:03d}.png"; im.save(path)
    caps.append((path, ch[0]["start"], min(nxt, ch[-1]["end"] + 0.35)))
inputs = ["-i", f"{work}/video.mp4", "-i", f"{work}/vo.wav"]
for c in caps: inputs += ["-i", c[0]]
chain, last = [], "[0:v]"
for n, (_, a, b) in enumerate(caps):
    out = f"[v{n}]"; chain.append(f"{last}[{n + 2}:v]overlay=0:H-150:enable='between(t,{a:.3f},{b:.3f})'{out}"); last = out
final = f"{P}/{plan['out']}"
sh("ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", last, "-map", "1:a",
   "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
   "-c:a", "aac", "-b:a", "192k", "-shortest", final)
print(f"done: {final}  ({total:.1f}s, {len(clips)} clips, {len(caps)} captions)")

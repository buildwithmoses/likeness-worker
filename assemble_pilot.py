#!/usr/bin/env python3
"""Assemble a pilot locally: voice lines -> one track, scenes timed to the narration with a slow
push-in, word-synced captions (Whisper), H.264 1280x720 mp4. No GPU, no cost.

    python3 assemble_pilot.py pilots/finance-001
Reads pilots/<p>/plan.json: {"prefix": "fin001", "gap": 0.35,
  "shots": [{"img": "s1_awake", "start": [para, word_index_or_0]}, ...]}
"""
import json, os, subprocess, sys

P = sys.argv[1]; plan = json.load(open(f"{P}/plan.json"))
OUT = "outputs"; pre = plan["prefix"]; work = f"{P}/build"; os.makedirs(work, exist_ok=True)
sh = lambda *a: subprocess.run(a, check=True, capture_output=True, text=True)

# 1. voice: each paragraph line -> wav, joined with short gaps; remember where each starts
paras, t, starts = [], 0.0, []
for i in range(1, plan["n_vo"] + 1):
    src = sorted(f for f in os.listdir(OUT) if f.startswith(f"{pre}_vo{i}_") and f.endswith(".flac"))[-1]
    wav = f"{work}/vo{i}.wav"; sh("ffmpeg", "-v", "error", "-y", "-i", f"{OUT}/{src}", "-ar", "48000", "-ac", "1", wav)
    dur = float(sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav).stdout)
    starts.append(t); paras.append(wav); t += dur + plan["gap"]
total = t
lst = f"{work}/vo.txt"; sil = f"{work}/gap.wav"
sh("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=mono", "-t", str(plan["gap"]), sil)
open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\nfile '{os.path.abspath(sil)}'\n" for p in paras))
sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, f"{work}/vo.wav")

# 2. word timings for captions and mid-paragraph cuts
sh("whisper", f"{work}/vo.wav", "--model", "base.en", "--word_timestamps", "True",
   "--output_format", "json", "--output_dir", work)
words = [w for s in json.load(open(f"{work}/vo.json"))["segments"] for w in s.get("words", [])]

def at(spec):  # [para, cue_word] -> seconds; cue_word "" = paragraph start
    para, cue = spec; t0 = starts[para - 1]
    if not cue: return max(0.0, t0 - 0.05)
    for w in words:
        if w["start"] >= t0 - 0.1 and w["word"].strip(" ,.?!").lower() == cue.lower():
            return w["start"] - 0.05
    raise SystemExit(f"cue word {cue!r} not found in paragraph {para}")

cuts = [at(s["start"]) for s in plan["shots"]] + [total]
# 3. scenes: slow 1.00 -> 1.07 push-in, alternating anchor so consecutive shots don't feel identical
clips = []
for i, s in enumerate(plan["shots"]):
    img = sorted(f for f in os.listdir(OUT) if f.startswith(f"{pre}_{s['img']}_") and f.endswith(".png"))[-1]
    d = cuts[i + 1] - cuts[i]; n = max(1, round(d * 30)); c = f"{work}/clip{i:02d}.mp4"
    zx = "iw/2-(iw/zoom/2)" if i % 2 == 0 else "iw/2-(iw/zoom/2)+(on/%d)*30" % n
    sh("ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", f"{OUT}/{img}", "-vf",
       f"scale=2560:1440,zoompan=z='1+0.07*on/{n}':x='{zx}':y='ih/2-(ih/zoom/2)':d={n}:s=1280x720:fps=30,format=yuv420p",
       "-frames:v", str(n), "-c:v", "libx264", "-preset", "fast", "-crf", "18", c)
    clips.append(c)
open(f"{work}/clips.txt", "w").write("".join(f"file '{os.path.abspath(c)}'\n" for c in clips))
sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{work}/clips.txt", "-c", "copy", f"{work}/video.mp4")

# 4. captions: 3-word chunks drawn as transparent PNGs (this ffmpeg has no libass/drawtext),
#    white bold with black outline in the lower third like the reference, overlaid at their word times
from PIL import Image, ImageDraw, ImageFont
font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Black.ttf", 40)
# Whisper splits "$1,000" into "$1" + ",000": glue any token without a leading space onto the previous word
cw = []
for w in words:
    if cw and not w["word"].startswith(" "):
        cw[-1] = {**cw[-1], "word": cw[-1]["word"] + w["word"], "end": w["end"]}
    else:
        cw.append(dict(w))
# chunks of up to 3 words that never cross a sentence end
chunks, cur = [], []
for w in cw:
    cur.append(w)
    if len(cur) == 3 or w["word"].rstrip().endswith((".", "?", "!")):
        chunks.append(cur); cur = []
if cur: chunks.append(cur)
caps = []
for ci, ch in enumerate(chunks):
    nxt = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else ch[-1]["end"] + 0.4
    txt = "".join(w["word"] for w in ch).strip().lower()
    im = Image.new("RGBA", (1280, 120), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    w = d.textlength(txt, font=font)
    d.text(((1280 - w) / 2, 30), txt, font=font, fill="white", stroke_width=4, stroke_fill="black")
    path = f"{work}/cap{len(caps):03d}.png"; im.save(path)
    caps.append((path, ch[0]["start"], min(nxt, ch[-1]["end"] + 0.4)))
inputs = ["-i", f"{work}/video.mp4", "-i", f"{work}/vo.wav"]
for c in caps: inputs += ["-i", c[0]]
chain, last = [], "[0:v]"
for n, (_, a, b) in enumerate(caps):
    out = f"[v{n}]"; chain.append(f"{last}[{n + 2}:v]overlay=0:H-170:enable='between(t,{a:.3f},{b:.3f})'{out}"); last = out
final = f"{P}/{plan['out']}"
sh("ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", last, "-map", "1:a", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
   "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-shortest", final)
print(f"done: {final}  ({total:.1f}s, {len(clips)} scenes, {len(words)} words, {len(caps)} captions)")

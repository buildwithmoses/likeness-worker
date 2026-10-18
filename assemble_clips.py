#!/usr/bin/env python3
"""Assemble an animated pilot on the Mac: voice lines -> one track, animated clips cut to the narration
(fixed framing, no zoom: each clip is only scaled to 1280x720, stretched up to 1.35x or frame-held to fill
its slot), Nick-Invests-style phrase captions, loudness-normalised. No GPU, no cost.

    python3 assemble_clips.py pilots/finance-002-simpsons
"""
import json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

def _font(size, *prefs):
    """The first font that exists: the Mac faces the pilots used, then the Linux ones the worker image ships."""
    import os as _os
    cands = list(prefs) + ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
    for c in cands:
        if _os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()

P = sys.argv[1]; plan = json.load(open(f"{P}/plan.json"))
OUT = "outputs"; pre = plan["prefix"]
W, H = plan.get("size", [1280, 720])
IMG = "outputs/up" if plan.get("upscaled") else OUT          # tools/upscale.sh writes 2x pictures to outputs/up
work = f"{P}/build"; os.makedirs(work, exist_ok=True)
sh = lambda *a: subprocess.run(a, check=True, capture_output=True, text=True)
dur_of = lambda f: float(sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f).stdout)

# 1. voice
paras, t, starts = [], 0.0, []
for i in range(1, plan["n_vo"] + 1):
    if plan.get("voice_dir"):
        srcpath = f"{plan['voice_dir']}/vo{i}.wav"
    else:
        srcpath = OUT + "/" + sorted(f for f in os.listdir(OUT) if f.startswith(f"{pre}_vo{i}_{pre}_vo{i}_") and f.endswith(".flac"))[-1]
    # TTS pads each file with ~0.75 s of silence; trim both ends so plan["gap"] is the only pause between paragraphs
    trim = "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,apad=pad_dur=0.08"
    wav = f"{work}/vo{i}.wav"; sh("ffmpeg", "-v", "error", "-y", "-i", srcpath, "-af", trim, "-ar", "48000", "-ac", "1", wav)
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
# 3. clips: scale to the output size (no zoom), stretch <=1.35x then hold last frame to fill the slot
clips = []
for i, s in enumerate(plan["shots"]):
    slot = cuts[i + 1] - cuts[i]; c = f"{work}/clip{i:02d}.mp4"
    if "bg" in s:  # puppet shot: green-screen character keyed out and moved over a still background (no zoom)
        mv = s["move"]; d = slot
        fgf = "colorkey=0x00FF00:0.30:0.08,despill=type=green" + (",hflip" if mv == "fly_left" else "")
        crop = ",crop=iw*0.62:ih:iw*0.19:0" if mv in ("walk", "tremble") else ""
        size = f"scale=-1:{int(H*0.58)}" if mv in ("walk", "tremble") else f"scale={int(W*0.78)}:-1"
        pos = {"walk":     f"x='-w+(W*0.62+w)*t/{d:.3f}':y='H-h-{int(H*0.04)}+{H/120:.1f}*abs(sin(t*6))'",
               "tremble":  f"x='W*0.16+{W/320:.1f}*sin(t*45)':y='H-h-{int(H*0.03)}+{H/360:.1f}*sin(t*53)'",
               "fly":      f"x='-w+(W+w)*t/{d:.3f}':y='{int(H*0.1)}+{H/16:.0f}*sin(t*1.6)'",
               "fly_left": f"x='W-(W+w)*t/{d:.3f}':y='{int(H*0.12)}+{H/16:.0f}*sin(t*1.6)'"}[mv]
        sh("ffmpeg", "-v", "error", "-y", "-loop", "1", "-t", f"{d:.3f}", "-i", f"{IMG}/{s['bg']}",
           "-loop", "1", "-t", f"{d:.3f}", "-i", f"{IMG}/{s['fg']}", "-filter_complex",
           f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},setsar=1[b];"
           f"[1:v]scale={W}:{H}:flags=lanczos,{fgf}{crop},{size}[f];[b][f]overlay={pos}:shortest=1,fps=30,format=yuv420p",
           "-t", f"{d:.3f}", "-c:v", "libx264", "-preset", "fast", "-crf", "17", c)
        clips.append(c); continue
    if "still" in s:  # still picture held for the whole slot: no zoom, no motion
        cx = ""
        if "crop" in s:   # fixed tighter framing [x0, y0, width] as fractions (16:9 kept); NOT a zoom, the frame never moves
            x0, y0, cw = s["crop"]; cx = f"crop=iw*{cw}:ih*{cw}:iw*{x0}:ih*{y0},"
        sh("ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", f"{IMG}/{s['still']}", "-vf",
           f"{cx}scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps=30,format=yuv420p",
           "-t", f"{slot:.3f}", "-c:v", "libx264", "-preset", "fast", "-crf", "17", c)
        clips.append(c); continue
    src = sorted(f for f in os.listdir(OUT) if f.startswith(f"{pre}_anim_{s['clip']}_") and f.endswith(".mp4"))[-1]
    cd = dur_of(f"{OUT}/{src}")
    speed = min(max(slot / cd, 1.0), 1.35)
    sh("ffmpeg", "-v", "error", "-y", "-i", f"{OUT}/{src}", "-vf",
       f"setpts={speed:.4f}*PTS,scale={W}:{H}:flags=lanczos,fps=30,tpad=stop_mode=clone:stop_duration=30,format=yuv420p",
       "-t", f"{slot:.3f}", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "17", c)
    clips.append(c)
open(f"{work}/clips.txt", "w").write("".join(f"file '{os.path.abspath(c)}'\n" for c in clips))
sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{work}/clips.txt", "-c", "copy", f"{work}/video.mp4")

# 3b. sound effects per shot: [["pop"|"whoosh"|"fire", offset_s], ...] relative to the shot start
SFX = {"pop":    ["-f", "lavfi", "-i", "aevalsrc=exprs=0.7*sin(2*PI*t*(1100-7000*t))*exp(-t*35):s=48000:d=0.14"],
       "whoosh": ["-f", "lavfi", "-i", "anoisesrc=d=1.1:c=pink:r=48000,highpass=f=350,lowpass=f=2800,afade=t=in:d=0.45,afade=t=out:st=0.5:d=0.6,volume=0.55"],
       "fire":   ["-f", "lavfi", "-i", "anoisesrc=d=3.5:c=brown:r=48000,lowpass=f=900,tremolo=f=9:d=0.6,afade=t=in:d=0.6,afade=t=out:st=2.4:d=1.1,volume=0.5"]}
hits = [(name, cuts[i] + off) for i, s in enumerate(plan["shots"]) for name, off in s.get("sfx", [])]
hits += [("pop", cuts[i] + lb["at"]) for i, s in enumerate(plan["shots"]) for lb in s.get("labels", [])]
if hits:
    vov = "1.0" if plan.get("voice", True) else "0"     # "voice": false = preview with SFX only (timing still from the VO)
    args, mix = ["-i", f"{work}/vo.wav"], [f"[0:a]volume={vov}[a0]"]
    for k, (name, at_s) in enumerate(hits):
        args += SFX[name]; ms = int(at_s * 1000)
        mix.append(f"[{k+1}:a]adelay={ms}|{ms},volume={plan.get('sfx_volume', 0.35)}[s{k}]")
    mix.append("".join(f"[a0]" if j == 0 else f"[s{j-1}]" for j in range(len(hits) + 1)) +
               f"amix=inputs={len(hits)+1}:normalize=0:duration=first[mixed]")
    sh("ffmpeg", "-v", "error", "-y", *args, "-filter_complex", ";".join(mix), "-map", "[mixed]", f"{work}/vo_sfx.wav")
    os.replace(f"{work}/vo_sfx.wav", f"{work}/vo.wav")
final = f"{P}/{plan['out']}"
labels = []
for i, sh_ in enumerate(plan["shots"]):
    for k, lb in enumerate(sh_.get("labels", [])):
        from PIL import Image, ImageDraw, ImageFont
        fnt = _font(int(H * 0.055), "/System/Library/Fonts/Supplemental/Arial Bold.ttf")
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        tx, ty = lb["x"] * W, lb["y"] * H; tw = d.textlength(lb["text"], font=fnt)
        tx = min(max(tx, tw / 2 + W * 0.03), W - tw / 2 - W * 0.03)   # keep the whole label inside the frame
        d.text((tx - tw / 2, ty), lb["text"], font=fnt, fill="black", stroke_width=int(H * 0.006), stroke_fill="white")
        if "arrow" in lb:   # simple thick arrow from under the label to the target point
            x2, y2 = lb["arrow"][0] * W, lb["arrow"][1] * H; x1, y1 = tx, ty + H * 0.075
            d.line([(x1, y1), (x2, y2)], fill="black", width=int(H * 0.008))
            import math
            a = math.atan2(y2 - y1, x2 - x1); L = H * 0.03
            d.polygon([(x2, y2), (x2 - L * math.cos(a - 0.45), y2 - L * math.sin(a - 0.45)),
                       (x2 - L * math.cos(a + 0.45), y2 - L * math.sin(a + 0.45))], fill="black")
        path = f"{work}/label{i:02d}_{k}.png"; im.save(path)
        # a short shot can end before lb["at"]: pull the label earlier so it still shows for >= 1 s (or the whole shot)
        a = max(cuts[i], min(cuts[i] + lb["at"], cuts[i + 1] - 1.0))
        labels.append((path, a, cuts[i + 1]))
src_v = f"{work}/video.mp4"
if labels:
    # One full-frame transparent label track: for every stretch of time, the labels on screen are composited into
    # one PNG; the stretches are concatenated and overlaid once. (Per-label overlays either drop labels, take
    # 15 min for 8 minutes, or deadlock when each input is time-shifted.)
    edges = sorted({0.0, total, *[e for _, a, b in labels for e in (a, b)]})
    blank = Image.new("RGBA", (W, H), (0, 0, 0, 0)); lines = []
    for k in range(len(edges) - 1):
        t0, t1 = edges[k], edges[k + 1]
        if t1 - t0 < 0.001: continue
        on = [p for p, a, b in labels if a <= t0 + 1e-6 and b >= t1 - 1e-6]
        frame = f"{work}/labeltrack_{k:03d}.png"
        im = blank.copy()
        for p in on: im = Image.alpha_composite(im, Image.open(p).convert("RGBA"))
        im.save(frame); lines += [f"file '{os.path.abspath(frame)}'", f"duration {t1 - t0:.3f}"]
    lines.append(lines[-2])
    open(f"{work}/labels.txt", "w").write("\n".join(lines) + "\n")
    # render the track to its own file first: overlaying the concat input directly silently drops all but the first label
    sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{work}/labels.txt",
       "-vf", "fps=30,format=argb", "-c:v", "qtrle", f"{work}/labeltrack.mov")
    sh("ffmpeg", "-v", "error", "-y", "-i", src_v, "-i", f"{work}/labeltrack.mov",
       "-filter_complex", "[0:v][1:v]overlay=0:0:eof_action=pass[v]", "-map", "[v]",
       "-c:v", "libx264", "-preset", "fast", "-crf", "17", f"{work}/video_labels.mp4")
    src_v = f"{work}/video_labels.mp4"
if not plan.get("captions", True):   # Wallace-style videos have no captions
    norm = "loudnorm=I=-16:TP=-1.5:LRA=11" if plan.get("voice", True) else "volume=1.6"   # don't normalise an SFX-only track
    sh("ffmpeg", "-v", "error", "-y", "-i", src_v, "-i", f"{work}/vo.wav", "-map", "0:v", "-map", "1:a",
       "-af", norm, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
       "-c:a", "aac", "-b:a", "192k", "-shortest", final)
    print(f"done: {final}  ({total:.1f}s, {len(clips)} clips, {len(labels)} labels, {len(hits)} sfx, {W}x{H}, no captions)"); sys.exit(0)
# 4. captions like the reference: short phrases (<=7 words, break at punctuation), condensed bold white, black outline
font = _font(round(H * 0.053), "/System/Library/Fonts/Supplemental/Impact.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")   # 38 px at 720p
chunks, cur = [], []
for w in words:
    cur.append(w)
    if len(cur) >= 7 or w["word"].rstrip().endswith((".", "?", "!", ",")):
        chunks.append(cur); cur = []
if cur: chunks.append(cur)
CAP_H = round(H * 0.125)
caps = []
for ci, ch in enumerate(chunks):
    nxt = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else ch[-1]["end"] + 0.4
    txt = "".join(w["word"] for w in ch).strip().lower().rstrip(",")
    im = Image.new("RGBA", (W, CAP_H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.text(((W - d.textlength(txt, font=font)) / 2, CAP_H * 0.22), txt, font=font, fill="white", stroke_width=round(H / 240), stroke_fill="black")
    path = f"{work}/cap{ci:03d}.png"; im.save(path)
    caps.append((path, ch[0]["start"], min(nxt, ch[-1]["end"] + 0.35)))
# One transparent caption track (concat of the caption PNGs with blanks in the gaps), overlaid once.
# Overlaying each caption PNG separately fails past a few hundred inputs (an 8-minute video has ~400).
blank = f"{work}/cap_blank.png"; Image.new("RGBA", (W, CAP_H), (0, 0, 0, 0)).save(blank)
lines, t = [], 0.0
for pth, a, b in caps:
    if a > t + 0.001: lines += [f"file '{os.path.abspath(blank)}'", f"duration {a - t:.3f}"]
    a = max(a, t); lines += [f"file '{os.path.abspath(pth)}'", f"duration {max(b - a, 0.04):.3f}"]; t = max(b, a + 0.04)
lines += [f"file '{os.path.abspath(blank)}'", f"duration {max(total - t, 0.04):.3f}", f"file '{os.path.abspath(blank)}'"]
open(f"{work}/caps.txt", "w").write("\n".join(lines) + "\n")
sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{work}/caps.txt",
   "-vf", "fps=30,format=argb", "-c:v", "qtrle", f"{work}/captrack.mov")   # own file first, as with the labels
inputs = ["-i", src_v, "-i", f"{work}/vo.wav", "-i", f"{work}/captrack.mov"]
chain, last = [f"[0:v][2:v]overlay=0:H-{round(H * 0.21)}:eof_action=pass[vcap]"], "[vcap]"
final = f"{P}/{plan['out']}"
sh("ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", last, "-map", "1:a",
   "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
   "-c:a", "aac", "-b:a", "192k", "-shortest", final)
print(f"done: {final}  ({total:.1f}s, {len(clips)} clips, {len(caps)} captions)")

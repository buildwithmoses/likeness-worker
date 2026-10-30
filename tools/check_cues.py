#!/usr/bin/env python3
"""Check every shot cue in a plan against the last Whisper transcript (build/vo.json) without rendering.
Reports cues that aren't found, cuts that go backwards, and very short/long shots.

    python3 tools/check_cues.py pilots/stick-004-dragonrider-full
"""
import json, subprocess, sys
P = sys.argv[1]; plan = json.load(open(f"{P}/plan.json")); work = f"{P}/build"
dur = lambda f: float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f],
                                     capture_output=True, text=True).stdout)
starts, t = [], 0.0
for i in range(1, plan["n_vo"] + 1):
    starts.append(t); t += dur(f"{work}/vo{i}.wav") + plan["gap"]
words = []
for w in (w for s in json.load(open(f"{work}/vo.json"))["segments"] for w in s.get("words", [])):
    if words and not w["word"].startswith(" "): words[-1] = {**words[-1], "word": words[-1]["word"] + w["word"], "end": w["end"]}
    else: words.append(dict(w))
bad, cuts = 0, []
for n, s in enumerate(plan["shots"]):
    para, cue = s["start"]; t0 = starts[para - 1]
    if not cue: cuts.append(t0); continue
    cw, _, k = cue.partition("#")   # "word#2" = the second time the word is said in this paragraph (assemble_clips.py)
    hits = [w["start"] for w in words if w["start"] >= t0 - 0.1 and w["word"].strip(" ,.?!").lower() == cw.lower()]
    hit = hits[int(k or 1) - 1] if len(hits) >= int(k or 1) else None
    if hit is None or (para < len(starts) and hit >= starts[para]):
        bad += 1; near = " ".join(w["word"] for w in words if t0 <= w["start"] < (starts[para] if para < len(starts) else t))
        print(f"shot {n}: cue {cue!r} not in paragraph {para}: {near[:160]}"); cuts.append(None); continue
    cuts.append(hit)
cuts.append(t)
for n in range(len(plan["shots"])):
    a, b = cuts[n], cuts[n + 1]
    if a is None or b is None: continue
    if b <= a: bad += 1; print(f"shot {n} ({plan['shots'][n]['start']}): cut goes backwards ({a:.1f} -> {b:.1f})")
    elif b - a < 1.0: print(f"shot {n} ({plan['shots'][n]['start']}): only {b - a:.1f}s")
    elif b - a > 9.0: print(f"shot {n} ({plan['shots'][n]['start']}): long hold {b - a:.1f}s")
print(f"{len(plan['shots'])} shots, {t:.1f}s, {bad} problems")

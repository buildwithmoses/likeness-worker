#!/usr/bin/env python3
"""Find and label the non-speech sounds (SFX, music, ambience) in a reference video.

    ~/.cache/likeness-audio/venv/bin/python tools/sfx_scan.py VIDEO.mp4 OUT.json

Runs PANNs Cnn14 sound-event detection (AudioSet, 527 classes) frame by frame on the Mac, drops speech and
room-tone classes, merges frames into events, and lines events up with the video's scene cuts.
"""
import json, subprocess, sys, collections
import numpy as np, librosa
from panns_inference import SoundEventDetection, labels

video, out = sys.argv[1], sys.argv[2]
TH = float(sys.argv[3]) if len(sys.argv) > 3 else 0.25
import os
y, sr = librosa.load(video, sr=32000, mono=True)
FPS = 100                                   # Cnn14_DecisionLevelMax outputs 100 frames per second
cache = os.path.splitext(video)[0] + ".sfx_probs.npy"  # saved next to the video: retuning thresholds is free
if os.path.exists(cache):
    probs = np.load(cache)
else:
    sed = SoundEventDetection(checkpoint_path=None, device="cpu")
    probs = []
    for s in range(0, len(y), sr * 60):      # one minute at a time keeps memory low
        chunk = y[s:s + sr * 60]
        if len(chunk) < sr: chunk = np.pad(chunk, (0, sr - len(chunk)))
        probs.append(sed.inference(chunk[None, :])[0][: int(len(chunk) / sr * FPS)])
    probs = np.concatenate(probs); np.save(cache, probs)

IGNORE = {"Speech", "Male speech, man speaking", "Female speech, woman speaking", "Narration, monologue", "Conversation",
          "Speech synthesizer", "Inside, small room", "Inside, large room or hall", "Silence", "Child speech, kid speaking",
          "Speech, human voice"}
keep = [i for i, l in enumerate(labels) if l not in IGNORE]
MIN = 0.12
events = []
for i in keep:
    on = probs[:, i] > TH
    if not on.any(): continue
    t = 0
    while t < len(on):
        if on[t]:
            e = t
            while e < len(on) and on[e]: e += 1
            if (e - t) / FPS >= MIN:
                events.append({"t": round(t / FPS, 2), "dur": round((e - t) / FPS, 2), "label": labels[i],
                               "peak": round(float(probs[t:e, i].max()), 2)})
            t = e
        else:
            t += 1
events.sort(key=lambda e: e["t"])

cuts = subprocess.run(["ffmpeg", "-hide_banner", "-i", video, "-vf", "select='gt(scene,0.3)',showinfo", "-an", "-f", "null", "-"],
                      capture_output=True, text=True).stderr
cuts = [float(x.split(":")[1]) for x in __import__("re").findall(r"pts_time:[0-9.]+", cuts)]
near = lambda t: any(abs(t - c) <= 0.35 for c in cuts)

dur = len(y) / sr
music = float((probs[:, labels.index("Music")] > TH).mean())
counts = collections.Counter(e["label"] for e in events if e["label"] != "Music")
at_cuts = collections.Counter(e["label"] for e in events if e["label"] != "Music" and near(e["t"]))
summary = {"video": video, "duration_s": round(dur, 1), "cuts": len(cuts), "music_fraction": round(music, 3),
           "sfx_events": sum(counts.values()), "sfx_per_minute": round(sum(counts.values()) / dur * 60, 1),
           "top_labels": counts.most_common(25), "labels_on_cuts": at_cuts.most_common(15),
           "cuts_with_a_sound": sum(1 for c in cuts if any(abs(e["t"] - c) <= 0.35 and e["label"] != "Music" for e in events))}
json.dump({"summary": summary, "events": events, "cuts": cuts}, open(out, "w"), indent=1)
print(json.dumps(summary, indent=1))

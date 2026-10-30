"""The green boxes: checks written as code, no LLM. Each returns {"pass": bool, "fails": [...], "warns": [...], ...}.
A fail sends the work back (max twice) or to Henry; a warn is only shown to him at the gate.

Calibrated 2026-10-15 on the two approved Day 2 episodes (finance-005, stick-005) and on the stills we had to
redo by hand: the checkerboard finance props (outputs/orig_checker/) and the stick-005 v4 heroes drawn in a
blue suit instead of the green one.
"""
import colorsys, json, os, re, subprocess
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = f"{HERE}/outputs"
NUM_WORDS = re.compile(r"\d")


def paragraphs(pilot):
    return [p.strip().replace("\n", " ") for p in open(f"{pilot}/script.txt").read().split("\n\n") if p.strip()]


def report(fails, warns, **k):
    return {"pass": not fails, "fails": fails, "warns": warns, **k}


# ------------------------------------------------------------------ script
def script_eval(pilot, fmt):
    paras = paragraphs(pilot); text = " ".join(paras); words = len(text.split())
    est = words / fmt.wpm * 60
    fails, warns = [], []
    if not fmt.min_s <= est <= fmt.max_s:
        need = round((fmt.min_s if est < fmt.min_s else fmt.max_s) / 60 * fmt.wpm)
        fails.append(f"about {est / 60:.1f} min ({words} words); 8-9 min needs {round(fmt.min_s / 60 * fmt.wpm)}-{round(fmt.max_s / 60 * fmt.wpm)} words "
                     f"({'add' if est < fmt.min_s else 'cut'} about {abs(need - words)})")
    for i, p in enumerate(paras, 1):
        n = len(p.split())
        if n > 120:   # Chatterbox stops at max_new_tokens; the longest approved paragraph is 71 words
            fails.append(f"paragraph {i} is {n} words; split it (max 120)")
        if NUM_WORDS.search(p):
            fails.append(f"paragraph {i} has digits ({', '.join(sorted(set(re.findall(r'[$]?[0-9][0-9,.%]*', p))))}); say numbers in words")
    for w in fmt.banned:
        if re.search(rf"\b{re.escape(w)}\b", text, re.I):
            fails.append(f"says {w!r} (no brand names in this format)")
    if fmt.needs_disclaimer and not re.search(r"not financial advice|education, not", text, re.I):
        fails.append("no disclaimer (education, not financial advice)")
    if fmt.needs_facts:
        if not os.path.exists(f"{pilot}/facts.py"):
            fails.append("no facts.py: every number in the script must be recomputed by code")
        else:
            r = subprocess.run(["python3", "-I", "facts.py"], cwd=pilot, capture_output=True, text=True, timeout=120)
            if r.returncode:
                fails.append("facts.py failed: " + (r.stdout + r.stderr).strip()[-600:])
    if not re.search(r"subscribe", paras[-1] + (paras[-2] if len(paras) > 1 else ""), re.I):
        warns.append("no subscribe ask at the end")
    return report(fails, warns, words=words, paragraphs=len(paras), est_s=round(est))


# ------------------------------------------------------------------ shots
def _norm(w):
    return w.strip(" ,.?!;:\"'()").lower()


def shots_eval(pilot, fmt, plan, jobs):
    """plan = the assembler plan (shots with still + [para, cue]); jobs = every picture job we know about."""
    paras = paragraphs(pilot); fails, warns = [], []
    if plan["n_vo"] != len(paras):
        fails.append(f"plan has n_vo {plan['n_vo']} but the script has {len(paras)} paragraphs")
    tags = {j["tag"] for j in jobs}
    pos, last = [], (0, -1)        # estimated start of each shot, in words from the top
    offsets = np.cumsum([0] + [len(p.split()) for p in paras])
    for n, s in enumerate(plan["shots"]):
        para, cue = s["start"]
        if not 1 <= para <= len(paras):
            fails.append(f"shot {n}: paragraph {para} doesn't exist"); continue
        words = [_norm(w) for w in paras[para - 1].split()]
        if not cue:
            i = 0
        elif cue.isdigit():     # Whisper writes "90" for "ninety": can't be checked against the text
            warns.append(f"shot {n}: cue {cue!r} is a number; checked only after voicing"); i = last[1] + 1 if last[0] == para else 0
        else:
            # assemble_clips cuts at the cue's FIRST match in the paragraph, so that's the one that counts
            i = next((k for k, w in enumerate(words) if w == cue.lower()), None)
            if i is None:
                fails.append(f"shot {n}: cue {cue!r} isn't a word in paragraph {para}"); continue
        if (para, i) < last:
            fails.append(f"shot {n}: cue {cue!r} comes before the previous shot's cue in paragraph {para} (cut would go backwards)")
        last = (para, i); pos.append(offsets[para - 1] + i)
        still = s["still"]
        if not os.path.exists(f"{OUT}/{still}") and not any(still.startswith(t + "_") for t in tags):
            fails.append(f"shot {n}: {still} has no picture and no job")
    covered = {s["start"][0] for s in plan["shots"]}
    pos.append(offsets[-1])
    secs = [(b - a) / fmt.wpm * 60 for a, b in zip(pos, pos[1:])]
    for n, d in enumerate(secs):
        if d > fmt.max_shot_s:
            fails.append(f"shot {n} runs about {d:.0f} s (max {fmt.max_shot_s}); add a picture")
    if len(paras) - len(covered) > len(paras) // 4:
        warns.append(f"{len(paras) - len(covered)} paragraphs have no cut of their own")
    return report(fails, warns, shots=len(plan["shots"]), longest_s=round(max(secs or [0])))


# ------------------------------------------------------------------ stills
def _hsv(a):
    f = a.astype(float) / 255
    mx, mn = f.max(-1), f.min(-1); d = mx - mn + 1e-9
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    h = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6
    return h, d / (mx + 1e-9), mx


def signature(path):
    """The hero's colour: the biggest hue bin among strong-colour pixels (the green suit, the yellow skin)."""
    h, s, v = _hsv(np.asarray(Image.open(path).convert("RGB").resize((320, 180))))
    m = (s > 0.45) & (v > 0.35)
    if m.sum() < 200: return None
    hist = np.bincount((h[m] * 24).astype(int) % 24, minlength=24)
    k = int(hist.argmax()); return k, hist[k] / h.size


def hue_share(path, k):
    h, s, v = _hsv(np.asarray(Image.open(path).convert("RGB").resize((320, 180))))
    m = (s > 0.45) & (v > 0.35) & ((h * 24).astype(int) % 24 == k)
    return m.mean()


def checker_share(a):
    """Share of 16 px tiles that hold both pure white and light neutral grey in a grid: the transparent-background
    pattern Qwen paints when it 'removes' a background (finance-005 props)."""
    g = a.mean(-1); sat = a.max(-1) - a.min(-1)
    white = (g > 247) & (sat < 6); grey = (g > 195) & (g < 225) & (sat < 6)
    H, W = g.shape; t = 16; H, W = H - H % t, W - W % t
    tw = white[:H, :W].reshape(H // t, t, W // t, t).mean((1, 3)); tg = grey[:H, :W].reshape(H // t, t, W // t, t).mean((1, 3))
    return float(((tw > 0.2) & (tg > 0.2)).mean())


def still_eval(path, fmt, hero=None):
    """hero = the reference picture this still was drawn from (ref shots only)."""
    if not os.path.exists(path):
        return report(["missing"], [])
    a = np.asarray(Image.open(path).convert("RGB")).astype(int); fails, warns = [], []
    if a.std() < 8:
        fails.append("blank")
    c = checker_share(a)
    if c > fmt.max_checker:
        fails.append(f"checkerboard background ({c:.0%} of tiles)")
    if fmt.white_bg:
        b = max(4, a.shape[0] // 30)
        border = np.concatenate([a[:b].reshape(-1, 3), a[-b:].reshape(-1, 3), a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3)])
        wb = float(((border.min(-1) > 235)).mean())
        if wb < 0.5:
            fails.append(f"background isn't plain white ({wb:.0%} of the border is white)")
    share = None
    if hero and os.path.exists(hero):
        sig = signature(hero)
        if sig:
            share = hue_share(path, sig[0]) / max(sig[1], 1e-6)
            if share < fmt.min_hero_color:
                fails.append(f"hero looks off-model: only {share:.0%} of the reference's main colour")
    return report(fails, warns, checker=round(c, 3), hero_color=None if share is None else round(float(share), 2))


# ------------------------------------------------------------------ video
def _probe(mp4):
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                                   "-of", "json", mp4], capture_output=True, text=True).stdout)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    return float(j["format"]["duration"]), v["width"], v["height"]


def video_eval(mp4, fmt, size=(1920, 1080)):
    if not os.path.exists(mp4):
        return report(["no video"], [])
    dur, w, h = _probe(mp4); fails, warns = [], []
    if not fmt.min_s <= dur <= fmt.max_s:
        fails.append(f"{dur / 60:.2f} min; needs 8-9")
    if (w, h) != tuple(size):
        fails.append(f"{w}x{h}, expected {size[0]}x{size[1]}")
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", mp4, "-af", "silencedetect=noise=-45dB:d=2.5,ebur128",
                          "-vf", "blackdetect=d=1:pix_th=0.05", "-f", "null", "-"], capture_output=True, text=True).stderr
    sil = re.findall(r"silence_duration: ([\d.]+)", err)
    black = re.findall(r"black_duration:([\d.]+)", err)
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    if sil:
        fails.append(f"{len(sil)} silence(s) over 2.5 s (longest {max(map(float, sil)):.1f} s)")
    if black:
        fails.append(f"{len(black)} black stretch(es) over 1 s")
    loud = float(lufs[-1]) if lufs else None
    if loud is None or abs(loud + 16) > 2:
        fails.append(f"loudness {loud} LUFS, expected about -16")
    return report(fails, warns, seconds=round(dur, 1), size=f"{w}x{h}", lufs=loud)

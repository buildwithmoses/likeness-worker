"""Video formats: everything that is the same for every episode of a channel. An episode only adds
its script and its shot list (pilots/<id>/video.json); the format turns those into ComfyUI jobs and
an assembler plan.

The two recipes below are lifted unchanged from finance-005 and stick-005 (Henry approved both,
2026-10-15), so a new episode looks like the last one without anyone copying a make_jobs.py.

video.json:
  {"format": "stick-doodle", "prefix": "gln", "title": "...", "out": "green_lantern.mp4",
   "heroes": {"char": {"tag": "gln_char", "desc": "the man from image 1 (round white head, ...)",
                       "scene": "full body, standing, plain background"}},
   "shots": [{"tag": "ac", "kind": "ref", "hero": "char", "scene": "...", "para": 1, "cue": "",
              "sfx": [["pop", 0.05]], "labels": [{"text": "Oa", "at": 0.8, "x": 0.5, "y": 0.08}]},
             {"tag": "field", "kind": "prop", "scene": "...", "para": 2, "cue": "green"}, ...]}

  kind "ref"  = a picture of a hero (uploads the hero image so the face stays the same)
  kind "prop" = no hero, an object or a place
  "expr" (simpsons only) = neutral | happy | worried | panicked | relieved
  A shot can reuse an earlier picture with "reuse": "<tag>" (no new job); "file" points at any
  existing picture in outputs/ (e.g. a still from an earlier episode).
"""
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
O = f"{HERE}/outputs"
fname = lambda tag: f"{tag}_{tag}_00001_.png"          # what ComfyUI + comfy_pod.py call a job's picture


class Format:
    name = ""
    voice = "kokoro"          # kokoro (Mac, free) | chatterbox (GPU pod)
    captions = False
    wpm = 220                 # measured on the approved episodes; turns a word count into minutes
    min_s, max_s = 480, 540   # JP call 2026-10-12: every video 8-9 minutes
    white_bg = False          # stills must sit on plain white (QC checks the border)
    seed0 = 30000
    banned = ()               # words the script may not say
    needs_disclaimer = needs_facts = False
    max_shot_s = 20           # longest a single picture may stay up
    max_checker = 0.02        # share of tiles with the transparent-background checkerboard
    min_hero_color = 0.0      # a ref shot must carry this share of the hero's main colour (0 = off)

    def prop(self, tag, scene, seed, video):
        raise NotImplementedError

    def ref(self, tag, scene, seed, video, shot):
        raise NotImplementedError

    def hero_jobs(self, video, seed):
        return []

    def voice_jobs(self, paras, prefix):
        return []

    def jobs(self, video):
        """Every picture job the episode needs, heroes first (later jobs upload them)."""
        seed = video.get("seed", self.seed0)
        jobs = self.hero_jobs(video, seed); seed += len(jobs)
        made = set()
        for s in video["shots"]:
            if s.get("reuse") or s.get("file") or s["tag"] in made:
                continue
            made.add(s["tag"]); seed += 1
            tag = f"{video['prefix']}_{s['tag']}"
            jobs.append(self.ref(tag, s["scene"], seed, video, s) if s.get("kind") == "ref" else self.prop(tag, s["scene"], seed, video))
        return jobs

    def plan(self, video, n_vo, pilot):
        """The plan.json assemble_clips.py reads."""
        def still(s):
            if s.get("file"): return s["file"]
            return fname(f"{video['prefix']}_{s.get('reuse') or s['tag']}")
        shots = [{"still": still(s), "start": [s["para"], s.get("cue", "")],
                  **{k: s[k] for k in ("sfx", "labels") if s.get(k)}} for s in video["shots"]]
        p = {"prefix": video["prefix"], "n_vo": n_vo, "gap": 0.25, "captions": self.captions, "upscaled": True,
             "size": [1920, 1080], "sfx_volume": 0.35, "voice": True, "out": video["out"], "shots": shots}
        if self.voice == "kokoro":
            p["voice_dir"] = f"{pilot}/voice"
        return p


class Simpsons(Format):
    """Barry Budgets (finance). Same guy and prompt recipe as finance-002..005."""
    name, voice, captions, wpm, white_bg, seed0 = "simpsons-finance", "chatterbox", True, 239, True, 15000
    needs_disclaimer = needs_facts = True
    CH = f"{HERE}/pilots/finance-002-simpsons/characters"
    CHAR = "simp002_char_simp002_char_00001_.png"
    EXPR = ("neutral", "happy", "worried", "panicked", "relieved")
    SIMP = ("in the classic Simpsons TV animation style: bright yellow skin, large round white eyes with small black pupils, "
            "slight overbite, four-finger hands, thin clean black outlines, flat colors")
    END = " Plain white background, static camera, single scene, wide 16:9 composition, no text, no words, no captions, no labels, no numbers."

    def prop(self, tag, scene, seed, video):
        return {"workflow": "workflows/qwen_t2i_lightning.json", "tag": tag,
                "set": {"10.seed": seed, "12.filename_prefix": tag, "6.prompt":
                        f"A simple flat cartoon prop drawing with thin clean black outlines and flat colors, an object only: {scene}. "
                        f"No people, no characters, no faces, no hands, no animals.{self.END}"}}

    def ref(self, tag, scene, seed, video, shot):
        e = shot.get("expr"); up = [f"{O}/{self.CHAR}"] + ([f"{self.CH}/{e}.png"] if e else [])
        face = f", with exactly the facial expression from image 2 ({e})" if e else ""
        return {"workflow": "workflows/qwen_style_ref_lightning.json", "tag": tag, "upload": up,
                "set": {"4.image": self.CHAR, "5.image": f"{e}.png" if e else self.CHAR, "10.seed": seed, "12.filename_prefix": tag,
                        "6.prompt": f"Draw the exact character from image 1 (same face, same brown hair with cowlick, same light blue t-shirt and jeans){face} "
                                    f"{self.SIMP}, in a new scene: {scene}.{self.END}"}}

    def voice_jobs(self, paras, prefix):
        """Chatterbox, the settings every finance episode used (seed 42, exaggeration 0.55)."""
        return [{"workflow": "workflows/chatterbox_builtin.json", "tag": f"{prefix}_vo{i}",
                 "set": {"2.text": t, "2.seed": 42, "2.exaggeration": 0.55, "2.max_new_tokens": 1500, "3.filename_prefix": f"{prefix}_vo{i}"}}
                for i, t in enumerate(paras, 1)]


class Stick(Format):
    """"Why It Sucks To Be..." stick-figure channel. Same doodle recipe as stick-004/005.
    "simple geometric shapes" is left OUT of the style: it gave block backgrounds on stick-005 (Henry, 2026-10-15)."""
    name, voice, captions, wpm, seed0 = "stick-doodle", "kokoro", False, 218, 21000
    banned = ("DC", "Marvel", "Warner", "HBO", "Disney")
    STYLE = ("minimal flat 2D cartoon in a simple doodle style: thick clean black outlines, flat muted colors "
             "(slate grey, beige, pale blue, dark navy, black) plus one bright accent color, no gradients, no textures, no shading, "
             "lots of empty space")
    NO = " No text, no letters, no numbers, no logos, no symbols on any clothing."

    def style(self, video):
        return video.get("style", self.STYLE)

    def hero_jobs(self, video, seed):
        jobs = []
        for k, h in video.get("heroes", {}).items():
            if h.get("file"):
                continue
            seed += 1
            jobs.append({"workflow": "workflows/qwen_t2i_lightning.json", "tag": h["tag"],
                         "set": {"10.seed": seed, "12.filename_prefix": h["tag"], "6.prompt": f"{self.style(video)}. {h['scene']}.{self.NO}"}})
        return jobs

    def hero_file(self, video, key):
        h = video["heroes"][key]
        return h.get("file") or fname(h["tag"])

    def prop(self, tag, scene, seed, video):
        return {"workflow": "workflows/qwen_t2i_lightning.json", "tag": tag,
                "set": {"10.seed": seed, "12.filename_prefix": tag, "6.prompt": f"{self.style(video)}. {scene}.{self.NO}"}}

    def ref(self, tag, scene, seed, video, shot):
        key = shot.get("hero", "char"); hero = self.hero_file(video, key)
        return {"workflow": "workflows/qwen_style_ref_lightning.json", "tag": tag, "upload": [f"{O}/{hero}"],
                "set": {"4.image": hero, "5.image": hero, "10.seed": seed, "12.filename_prefix": tag,
                        "6.prompt": f"Using the exact style and {video['heroes'][key]['desc']}, {self.style(video)}: {scene}. Wide 16:9.{self.NO}"}}


FORMATS = {f.name: f for f in (Simpsons(), Stick())}
# Episodes made before the harness: which format they are
LEGACY = {"finance": "simpsons-finance", "stick": "stick-doodle"}


def for_pilot(pilot, video=None):
    if video and video.get("format"):
        return FORMATS[video["format"]]
    kind = os.path.basename(pilot).split("-")[0]
    return FORMATS[LEGACY[kind]]

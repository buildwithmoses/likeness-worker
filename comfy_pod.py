#!/usr/bin/env python3
"""Run workflows against ComfyUI on a RunPod *pod* (not the serverless endpoint).

    python3 comfy_pod.py POD_ID jobs.json [--keep] [--skip-existing]   # jobs.json: [{"workflow": "...", "set": {...}, "tag": "..."}]

By default the pod is TERMINATED when the batch ends (success, failure or Ctrl-C), so a finished
batch can never sit idle and bill. Pass --keep only when another batch follows immediately.

Talks to https://POD_ID-8188.proxy.runpod.net (ComfyUI's own API), saves outputs to
outputs/, and prints wall-clock seconds per job so we can price a session.
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request

import atexit, subprocess
POD, JOBS = sys.argv[1], json.load(open(sys.argv[2]))
KEEP = "--keep" in sys.argv


def terminate_pod():
    """DELETE the pod through RunPod's REST API (key from the macOS Keychain), then confirm it's gone."""
    if KEEP:
        print(f"--keep: pod {POD} left RUNNING (it bills until terminated)", flush=True); return
    key = (os.environ.get("PS_RUNPOD_KEY") or os.environ.get("RUNPOD_API_KEY") or "").strip() or \
        subprocess.check_output(["security", "find-generic-password", "-s", "runpod-api", "-w"], text=True).strip()
    hdr = {"Authorization": f"Bearer {key}", "User-Agent": "likeness-worker/1.0"}
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://rest.runpod.io/v1/pods/{POD}", method="DELETE", headers=hdr), timeout=60)
    except Exception as e:
        print(f"!! terminate request failed: {e}", flush=True)
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://rest.runpod.io/v1/pods/{POD}", headers=hdr), timeout=60)
        print(f"!! pod {POD} still exists after terminate; delete it by hand", flush=True)
    except urllib.error.HTTPError as e:
        print(f"pod {POD} terminated (read-back {e.code})", flush=True)


atexit.register(terminate_pod)
BASE = f"https://{POD}-8188.proxy.runpod.net"
HERE = os.path.dirname(os.path.abspath(__file__))


def req(path, body=None, tries=6):
    """One ComfyUI API call. Transient network errors are retried: one reset connection killed a
    205-job batch on 2026-10-14. HTTP errors (a rejected workflow) are raised at once."""
    for k in range(tries):
        r = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None,
                                   headers={"Content-Type": "application/json",
                                            # RunPod's proxy 403s the default Python-urllib agent
                                            "User-Agent": "likeness-worker/1.0"})
        try:
            with urllib.request.urlopen(r, timeout=60) as f:
                return f.read()
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            if k == tries - 1: raise
            print(f"  network error on {path.split('?')[0]} ({e}); retry {k + 1}", flush=True); time.sleep(5 * (k + 1))


def wait_ready(limit=int(os.environ.get("COMFY_WAIT", 1800))):
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            req("/system_stats", tries=1); print(f"ComfyUI up after {int(time.time()-t0)}s", flush=True); return
        except Exception as e:
            print(f"  waiting for ComfyUI: {e}", flush=True)
            time.sleep(10)
    sys.exit("ComfyUI never came up")


def upload(path):
    """POST a local file to ComfyUI's input folder (multipart), keeping its basename."""
    boundary = "----likeness" + str(int(time.time() * 1000))
    name = os.path.basename(path)
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + open(path, "rb").read() + \
           f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n".encode()
    r = urllib.request.Request(BASE + "/upload/image", data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "likeness-worker/1.0"})
    urllib.request.urlopen(r, timeout=120).read()


wait_ready()
total = 0.0
MAX_MIN = float(os.environ.get("COMFY_MAX_MINUTES", 30))
batch_t0 = time.time()
SKIP = "--skip-existing" in sys.argv   # resume a batch: jobs whose output is already in outputs/ are skipped
done = set(os.listdir(os.path.join(HERE, "outputs"))) if SKIP else set()
for j in JOBS:
    if SKIP and any(f.startswith(j["tag"] + "_") and "ComfyUI_temp" not in f for f in done):
        continue
    if (time.time() - batch_t0) / 60 > MAX_MIN:
        print(f"!! {MAX_MIN:.0f}-minute cap reached; stopping before {j['tag']}. Re-run later with --skip-existing for the rest.", flush=True)
        KEEP = False   # whatever was asked, a capped run never leaves a pod billing
        break
    wf = json.load(open(os.path.join(HERE, j["workflow"])))
    for target, val in j.get("set", {}).items():
        node, inp = target.split(".", 1); wf[node]["inputs"][inp] = val
    for f in j.get("upload", []):
        upload(f)
    t0 = time.time()
    try:
        pid = json.loads(req("/prompt", {"prompt": wf}))["prompt_id"]
    except urllib.error.HTTPError as e:   # ComfyUI explains a rejected workflow in the body
        print(f"{j['tag']}: REJECTED {e.code} {e.read().decode(errors='replace')[:800]}", flush=True); continue
    while True:
        h = json.loads(req(f"/history/{pid}"))
        if pid in h and h[pid].get("status", {}).get("completed") is not None:
            break
        time.sleep(1)
    dt = time.time() - t0; total += dt
    st = h[pid]["status"]
    if st.get("status_str") != "success":
        print(f"{j['tag']}: FAILED {json.dumps(st)[:600]}"); continue
    for out in h[pid]["outputs"].values():
        for im in out.get("images", []) + out.get("audio", []) + out.get("gifs", []):
            q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im.get("subfolder", ""), "type": im["type"]})
            path = os.path.join(HERE, "outputs", f"{j['tag']}_{im['filename']}")
            open(path, "wb").write(req(f"/view?{q}"))
    print(f"{j['tag']}: {dt:.1f}s", flush=True)
print(f"TOTAL generation time {total:.0f}s over {len(JOBS)} jobs")

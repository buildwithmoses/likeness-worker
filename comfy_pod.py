#!/usr/bin/env python3
"""Run workflows against ComfyUI on a RunPod *pod* (not the serverless endpoint).

    python3 comfy_pod.py POD_ID jobs.json      # jobs.json: [{"workflow": "...", "set": {...}, "tag": "..."}]

Talks to https://POD_ID-8188.proxy.runpod.net (ComfyUI's own API), saves outputs to
outputs/, and prints wall-clock seconds per job so we can price a session.
"""
import json, os, sys, time, urllib.parse, urllib.request

POD, JOBS = sys.argv[1], json.load(open(sys.argv[2]))
BASE = f"https://{POD}-8188.proxy.runpod.net"
HERE = os.path.dirname(os.path.abspath(__file__))


def req(path, body=None):
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None,
                               headers={"Content-Type": "application/json",
                                        # RunPod's proxy 403s the default Python-urllib agent
                                        "User-Agent": "likeness-worker/1.0"})
    with urllib.request.urlopen(r, timeout=60) as f:
        return f.read()


def wait_ready(limit=1800):
    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            req("/system_stats"); print(f"ComfyUI up after {int(time.time()-t0)}s", flush=True); return
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
for j in JOBS:
    wf = json.load(open(os.path.join(HERE, j["workflow"])))
    for target, val in j.get("set", {}).items():
        node, inp = target.split(".", 1); wf[node]["inputs"][inp] = val
    for f in j.get("upload", []):
        upload(f)
    t0 = time.time()
    pid = json.loads(req("/prompt", {"prompt": wf}))["prompt_id"]
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

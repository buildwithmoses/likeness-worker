#!/usr/bin/env python3
"""Submit a workflow to the likeness endpoint and save its outputs to outputs/.

    python3 run.py workflows/qwen_edit.json [--upload inputs/me_01.png ...] [--set NODE.INPUT=VALUE ...]

The RunPod API key is read from the macOS Keychain (service "runpod-api"), never from argv.
Uploaded files keep their basename, which is what LoadImage/LoadAudio nodes reference.
"""
import argparse, base64, json, os, subprocess, sys, time, urllib.request

ENDPOINT = "8ms2lswyzp133u"
API = f"https://api.runpod.ai/v2/{ENDPOINT}"
HERE = os.path.dirname(os.path.abspath(__file__))


def api_key():
    return subprocess.check_output(
        ["security", "find-generic-password", "-s", "runpod-api", "-w"], text=True).strip()


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {api_key()}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workflow")
    ap.add_argument("--upload", nargs="*", default=[])
    ap.add_argument("--set", nargs="*", default=[], help="NODE.INPUT=VALUE (VALUE parsed as JSON if possible)")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()

    wf = json.load(open(a.workflow))
    for s in a.set:
        target, val = s.split("=", 1)
        node, inp = target.split(".", 1)
        try: val = json.loads(val)
        except json.JSONDecodeError: pass
        wf[node]["inputs"][inp] = val

    images = [{"name": os.path.basename(p), "image": base64.b64encode(open(p, "rb").read()).decode()}
              for p in a.upload]
    job = call("POST", "/run", {"input": {"workflow": wf, "images": images}})
    jid = job["id"]
    print(f"job {jid} submitted", flush=True)

    t0 = time.time()
    while True:
        st = call("GET", f"/status/{jid}")
        if st["status"] in ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"):
            break
        print(f"  {int(time.time()-t0)}s {st['status']}", flush=True)
        time.sleep(10)

    print(f"job {jid} {st['status']}  delay={st.get('delayTime')}ms exec={st.get('executionTime')}ms")
    out = st.get("output") or {}
    if st["status"] != "COMPLETED" or "error" in out:
        print(json.dumps({k: v for k, v in st.items() if k != "output"} | {"output": out}, indent=1)[:4000])
        sys.exit(1)
    os.makedirs(os.path.join(HERE, "outputs"), exist_ok=True)
    for item in out.get("images", []):
        name = (a.tag + "_" if a.tag else "") + item["filename"]
        path = os.path.join(HERE, "outputs", name)
        if item.get("type") == "base64":
            open(path, "wb").write(base64.b64decode(item["data"]))
            print(f"saved {path} ({os.path.getsize(path)//1024} KB)")
        else:
            print(f"output at {item.get('data')}")
    for e in out.get("errors", []) or []:
        print("worker warning:", e)


if __name__ == "__main__":
    main()

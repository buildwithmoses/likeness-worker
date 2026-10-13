#!/usr/bin/env bash
# Boot script for the stock image runpod/worker-comfyui:5.10.0-base (no custom image needed).
# ComfyUI and its venv stay in the container (fast local disk). Each boot: upgrade ComfyUI,
# clone the custom nodes, install their deps (~1-2 min). Only models live on the network
# volume, downloaded once. One worker max, so nothing writes to the volume concurrently.
set -uo pipefail
VOL=/runpod-volume
REPO_RAW="${LIKENESS_REPO_RAW:-https://raw.githubusercontent.com/buildwithmoses/likeness-worker/main}"
PY=/opt/venv/bin/python
log() { echo "likeness-boot: $(date +%T) $*"; }

# No network volume (throwaway pod): use a plain directory on the container disk instead.
[ -d "$VOL" ] || { mkdir -p "$VOL"; log "no network volume; models go on the container disk"; }

# Leftovers from the first design (ComfyUI + venv copied onto the volume): delete in the background.
for d in "$VOL/comfyui" "$VOL/venv"; do [ -e "$d" ] && { mv "$d" "$d.trash-$$" 2>/dev/null; (rm -rf "$d.trash-$$" &); }; done
rm -f "$VOL/.likeness-install-v1"

log "upgrading ComfyUI to v0.39.0 (Chatterbox needs >= 0.37)"
cd /comfyui && git fetch -q --depth 1 origin tag v0.39.0 && git checkout -q v0.39.0 \
  && uv pip install -q --python "$PY" -r requirements.txt || log "ComfyUI upgrade FAILED"

log "installing custom nodes"
cd /comfyui/custom_nodes
for r in kijai/ComfyUI-WanVideoWrapper kijai/ComfyUI-KJNodes Kosinkadink/ComfyUI-VideoHelperSuite \
         kijai/ComfyUI-MelBandRoFormer wildminder/ComfyUI-Chatterbox; do
  [ -d "${r#*/}" ] || git clone -q --depth 1 "https://github.com/$r.git" || log "clone FAILED $r"
done
reqs=(); for f in /comfyui/custom_nodes/*/requirements.txt; do reqs+=(-r "$f"); done
uv pip install -q --python "$PY" "${reqs[@]}" "transformers>=4.50.3,<5" "huggingface-hub<1.0" || log "node deps FAILED"

if [ -d "$VOL" ]; then
  mkdir -p "$VOL/models"
  rm -rf /comfyui/models && ln -s "$VOL/models" /comfyui/models
  log "checking models"
  wget -q -O /tmp/models.txt "$REPO_RAW/models.txt" || : > /tmp/models.txt
  # up to 4 downloads at once: boot time is dominated by these (~60 GB)
  while read -r rel url; do
    { [ -z "${rel:-}" ] || [ "${rel:0:1}" = "#" ]; } && continue
    dest="$VOL/models/$rel"
    [ -s "$dest" ] && continue
    mkdir -p "$(dirname "$dest")"
    log "fetching $rel"
    ( if wget -q -c -O "$dest.part" "$url"; then mv "$dest.part" "$dest"; else log "FAILED $rel"; fi ) &
    while [ "$(jobs -rp | wc -l)" -ge 4 ]; do sleep 1; done
  done < /tmp/models.txt
  wait
  log "models ready"
else
  log "no network volume at $VOL"
fi

log "patching handler to also return video and audio outputs"
"$PY" - <<'PYEOF'
import re
p = "/handler.py"
s = open(p).read()
anchor = "for node_id, node_output in outputs.items():"
add = ('\n{i}    for _k in ("gifs", "audio", "videos"):'
       '\n{i}        if _k in node_output:'
       '\n{i}            node_output.setdefault("images", []).extend(node_output.pop(_k))')
if "for _k in (\"gifs\"" in s:
    print("likeness-boot: handler already patched")
else:
    m = re.search(r"^([ \t]*)" + re.escape(anchor), s, re.M)
    if m:
        s = s[:m.end()] + add.format(i=m.group(1)) + s[m.end():]
        open(p, "w").write(s)
        print("likeness-boot: handler patched")
    else:
        print("likeness-boot: handler anchor NOT found; video/audio outputs will be dropped")
PYEOF

log "starting worker"
exec /start.sh

#!/usr/bin/env bash
# Boot script for the stock image runpod/worker-comfyui:5.10.0-base (no custom image needed).
# First boot: move ComfyUI + its venv onto the network volume, upgrade ComfyUI, add the
# custom nodes, download models. Later boots: symlink the volume copies back and start.
# One worker max on this endpoint, so nothing writes to the volume concurrently.
set -uo pipefail
VOL=/runpod-volume
STAMP="$VOL/.likeness-install-v1"
REPO_RAW="${LIKENESS_REPO_RAW:-https://raw.githubusercontent.com/buildwithmoses/likeness-worker/main}"
PY=/opt/venv/bin/python
log() { echo "likeness-boot: $*"; }

[ -d "$VOL" ] || { log "no network volume at $VOL; starting stock worker"; exec /start.sh; }

if [ ! -f "$STAMP" ]; then
  log "first boot: copying ComfyUI and venv to the volume"
  rm -rf "$VOL/comfyui" "$VOL/venv"
  tar -C / --exclude=comfyui/.venv -cf - comfyui | tar -C "$VOL" -xf -
  cp -a /opt/venv "$VOL/venv"
fi
rm -rf /comfyui /opt/venv
ln -s "$VOL/comfyui" /comfyui
ln -s "$VOL/venv" /opt/venv

if [ ! -f "$STAMP" ]; then
  set -e
  log "upgrading ComfyUI to v0.39.0 (Chatterbox needs >= 0.37)"
  cd /comfyui
  git fetch --depth 1 origin tag v0.39.0 && git checkout -q v0.39.0
  uv pip install --python "$PY" -r requirements.txt
  log "installing custom nodes"
  cd /comfyui/custom_nodes
  for r in kijai/ComfyUI-WanVideoWrapper kijai/ComfyUI-KJNodes Kosinkadink/ComfyUI-VideoHelperSuite \
           kijai/ComfyUI-MelBandRoFormer wildminder/ComfyUI-Chatterbox; do
    [ -d "${r#*/}" ] || git clone --depth 1 "https://github.com/$r.git"
  done
  for req in /comfyui/custom_nodes/*/requirements.txt; do uv pip install --python "$PY" -r "$req"; done
  uv pip install --python "$PY" "transformers>=4.50.3,<5" "huggingface-hub<1.0"
  cd /comfyui && timeout 300 "$PY" main.py --quick-test-for-ci --cpu
  set +e
  touch "$STAMP"
  log "install done"
fi

log "checking models"
wget -q -O /tmp/models.txt "$REPO_RAW/models.txt" || log "could not fetch models.txt; skipping model check"
while read -r rel url; do
  { [ -z "${rel:-}" ] || [ "${rel:0:1}" = "#" ]; } && continue
  dest="/comfyui/models/$rel"
  [ -s "$dest" ] && continue
  mkdir -p "$(dirname "$dest")"
  log "fetching $rel"
  if wget -q -c -O "$dest.part" "$url"; then mv "$dest.part" "$dest"; else log "FAILED $rel"; fi
done < /tmp/models.txt 2>/dev/null
du -sh "$VOL" 2>/dev/null | sed 's/^/likeness-boot: volume used /'

exec /start.sh

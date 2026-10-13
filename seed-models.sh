#!/usr/bin/env bash
# Point ComfyUI's whole models/ tree at the network volume, fetch any model in
# /models.txt that is missing, then hand off to the stock worker start script.
# Pointing the whole tree (not just extra_model_paths) also catches the folders
# custom nodes download into themselves: models/tts, models/wav2vec2.
set -uo pipefail
VOL=/runpod-volume
if [ -d "$VOL" ]; then
  mkdir -p "$VOL/models"
  rm -rf /comfyui/models && ln -s "$VOL/models" /comfyui/models
  export HF_HOME="$VOL/hf-cache" HF_HUB_ENABLE_HF_TRANSFER=1
  while read -r rel url; do
    [ -z "$rel" ] || [ "${rel:0:1}" = "#" ] && continue
    dest="$VOL/models/$rel"
    [ -s "$dest" ] && continue
    mkdir -p "$(dirname "$dest")"
    echo "seed-models: fetching $rel"
    if curl -fL --retry 5 --retry-delay 5 -o "$dest.part" "$url"; then
      mv "$dest.part" "$dest"
    else
      echo "seed-models: FAILED $rel" >&2; rm -f "$dest.part"
    fi
  done < /models.txt
  echo "seed-models: done"; du -sh "$VOL/models" 2>/dev/null
else
  echo "seed-models: no network volume at $VOL, models must be baked in" >&2
fi
exec /start.sh

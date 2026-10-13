#!/usr/bin/env bash
# Upscale stills 2x with Real-ESRGAN (anime/cartoon model) on the Mac GPU. Free, ~3 s per picture.
#   tools/upscale.sh outputs/drg_*.png      -> writes outputs/up/<same name>.png (2560x1440 from 1280x720)
# Skips pictures that are already upscaled.
set -euo pipefail
BIN=~/.cache/likeness-upscale/realesrgan/realesrgan-ncnn-vulkan
cd "$(dirname "$0")/.."
mkdir -p outputs/up
for f in "$@"; do
  out="outputs/up/$(basename "$f")"
  [ -s "$out" ] && continue
  ( cd "$(dirname "$BIN")" && ./realesrgan-ncnn-vulkan -i "$OLDPWD/$f" -o "$OLDPWD/$out" -n realesr-animevideov3-x2 -s 2 >/dev/null 2>&1 ) \
    && echo "up: $(basename "$f")" || echo "FAILED: $f"
done

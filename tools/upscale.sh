#!/usr/bin/env bash
# Upscale stills 2x with Real-ESRGAN (anime/cartoon model) on the Mac GPU. Free, ~3 s per picture.
# No Real-ESRGAN here (a cloud worker): ffmpeg Lanczos 2x instead.
#   tools/upscale.sh outputs/drg_*.png      -> writes outputs/up/<same name>.png (2560x1440 from 1280x720)
# Skips pictures that are already upscaled.
set -euo pipefail
BIN=~/.cache/likeness-upscale/realesrgan/realesrgan-ncnn-vulkan
cd "$(dirname "$0")/.."
mkdir -p outputs/up
for f in "$@"; do
  out="outputs/up/$(basename "$f")"
  [ -s "$out" ] && continue
  # A cloud worker has no GPU and no Real-ESRGAN: a Lanczos 2x keeps the flat
  # art's edges clean enough for the 1920x1080 cut (2026-10-22).
  if [ ! -x "$BIN" ]; then
    ffmpeg -nostdin -v error -y -i "$f" -vf "scale=iw*2:ih*2:flags=lanczos" "$out" \
      && echo "up (lanczos): $(basename "$f")" || echo "FAILED: $f"
    continue
  fi
  ( cd "$(dirname "$BIN")" && ./realesrgan-ncnn-vulkan -i "$OLDPWD/$f" -o "$OLDPWD/$out" -n realesr-animevideov3-x2 -s 2 >/dev/null 2>&1 ) \
    && echo "up: $(basename "$f")" || echo "FAILED: $f"
done

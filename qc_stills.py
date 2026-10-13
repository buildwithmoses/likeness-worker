#!/usr/bin/env python3
"""QC helper: for each still, write a full-size copy plus 2x zoomed crops of every face, so faces are
reviewed up close (the half-closed-eye miss happened on thumbnails).

    python3 qc_stills.py OUT_DIR still1.png still2.png ...

Faces are found by the character's flat yellow skin (Simpsons style); each yellow blob in the upper part
of a figure becomes a crop. Writes OUT_DIR/<name>__full.png and OUT_DIR/<name>__face<N>.png.
"""
import os, sys
import numpy as np
from PIL import Image

def find_blobs(mask, step=4):
    """Connected yellow regions on a 1/step grid (4-neighbour flood fill); no scipy needed."""
    small = mask[::step, ::step]; H, W = small.shape; seen = np.zeros_like(small, bool); blobs = []
    for y0 in range(H):
        for x0 in range(W):
            if not small[y0, x0] or seen[y0, x0]:
                continue
            stack, pts = [(y0, x0)], []; seen[y0, x0] = True
            while stack:
                y, x = stack.pop(); pts.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W and small[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True; stack.append((ny, nx))
            ys = np.array([p[0] for p in pts]) * step; xs = np.array([p[1] for p in pts]) * step
            blobs.append((len(pts) * step * step, ys, xs))
    return sorted(blobs, key=lambda b: -b[0])


out = sys.argv[1]; os.makedirs(out, exist_ok=True)
for path in sys.argv[2:]:
    im = Image.open(path).convert("RGB"); a = np.asarray(im).astype(int)
    name = os.path.splitext(os.path.basename(path))[0]
    im.save(f"{out}/{name}__full.png")
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    yellow = (r > 200) & (g > 160) & (b < 110) & (r - b > 120)
    blobs = find_blobs(yellow, step=4)            # [(pixel_count, ys, xs)], largest first
    faces = 0
    for count, ys, xs in blobs[:4]:
        if count < 0.004 * yellow.size:
            break
        top = ys.min(); h = ys.max() - top
        face_h = min(h, int((xs.max() - xs.min()) * 1.3))   # head = top part of the yellow blob
        x0, x1 = xs.min(), xs.max()
        pad = int(face_h * 0.25)
        box = (max(0, x0 - pad), max(0, top - pad * 2), min(im.width, x1 + pad), min(im.height, top + face_h + pad))
        crop = im.crop(box); crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
        faces += 1; crop.save(f"{out}/{name}__face{faces}.png")
    print(f"{name}: {faces} face crop(s)")

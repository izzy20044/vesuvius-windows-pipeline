"""Score one screened winding for ink: side asymmetry per tile, plus a thumbnail.

Off-sheet mesh drift lights up both sides alike; ink lights up one side. The score is therefore
the per-tile mean of (reverse - forward) ink probability over CT-valid pixels, with tiles of
~1.4 x 1.4 cm (1500 px at 9.362 um). Prints one TSV line; writes <out>/<winding>.png.

Usage: python score_winding.py <render.zarr> <maps_dir> <winding> <model> <out_dir>
"""
import sys
from pathlib import Path

import cv2
import numpy as np
import tifffile
import zarr

TILE = 1500


def prob(path):
    m = tifffile.imread(path).astype(np.float32)
    return np.clip((m - 64.0) / 128.0, 0, 1)      # villa label-smoothing convention


def main(render, maps, winding, model, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    ct = np.asarray(zarr.open(render, mode="r")["0"][13])
    valid = ct > 0
    fwd = prob(Path(maps) / f"{winding}__{model}__d+0_forward.tif")
    rev = prob(Path(maps) / f"{winding}__{model}__d+0_reverse.tif")
    diff = rev - fwd
    H, W = diff.shape
    best = (0.0, 0, 0, 0.0)
    for y in range(0, max(1, H - TILE // 2), TILE // 2):
        for x in range(0, max(1, W - TILE // 2), TILE // 2):
            v = valid[y:y + TILE, x:x + TILE]
            if v.mean() < 0.5:
                continue
            a = float(diff[y:y + TILE, x:x + TILE][v].mean())
            if abs(a) > abs(best[0]):
                best = (a, y, x, float(v.mean()))
    whole = float(diff[valid].mean()) if valid.any() else 0.0
    print(f"{winding}\t{whole:+.4f}\t{best[0]:+.4f}\t{best[1]}\t{best[2]}\t{best[3]:.2f}\t{W}x{H}", flush=True)

    def to8(a, lo, hi):
        b = (np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1) * 255).astype(np.uint8)
        b[~valid] = 0
        return b
    lo, hi = np.percentile(ct[valid], [1, 99.5]) if valid.any() else (0, 255)
    rows = [to8(ct.astype(np.float32), lo, hi), to8(fwd, 0, 1), to8(rev, 0, 1),
            to8(diff, -0.5, 0.5)]
    sep = np.full((6, W), 128, np.uint8)
    img = np.vstack([r for pair in zip(rows, [sep] * 4) for r in pair][:-1])
    s = 3
    cv2.imwrite(str(out / f"{winding}.png"),
                cv2.resize(img, (W // s, img.shape[0] // s), interpolation=cv2.INTER_AREA))


if __name__ == "__main__":
    main(*sys.argv[1:6])

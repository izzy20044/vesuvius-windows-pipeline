"""Readability-enhanced ink maps for one winding, processed identically on both sides of the sheet.

1. per model: pool both sides and all depths to one mean/sd (as ensemble_maps.py does), z-score;
2. average depths and models per side;
3. remove the broad trend (masked Gaussian, sigma ~2.8 mm) so whole-side brightness does not dominate;
4. light smoothing (sigma ~0.075 mm, below stroke width), one shared stretch for both sides;
5. also a top-k% view with one shared threshold.
Only villa maps (render grid) are used; Hecate maps are on a resampled grid and skipped here.

Usage: python enhance_sides.py <render.zarr> <maps_dir> <out.png> [top_percent]
"""
import glob
import re
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import tifffile
import zarr

UM = 9.362


def masked_blur(a, mask, sigma):
    num = cv2.GaussianBlur(a * mask, (0, 0), sigma)
    den = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), sigma)
    return num / np.maximum(den, 1e-3)


def main(render, maps, out, top="8", orient="raw", um=str(UM)):
    global UM
    UM = float(um)
    ct = np.asarray(zarr.open(render, mode="r")["0"][33]).astype(np.float32)
    valid = ct > 0
    m32 = valid.astype(np.float32)
    files = defaultdict(dict)   # model -> {(s, side): path}
    for f in glob.glob(str(Path(maps) / "*.tif")):
        mm = re.search(r"__(.+?)__L66s(\d+)(_reverse)?\.tif$", f)
        if mm:
            files[mm.group(1)][(int(mm.group(2)), "rev" if mm.group(3) else "fwd")] = f
    sides = {"fwd": [], "rev": []}
    used = []
    for model, fs in sorted(files.items()):
        depths = sorted({s for s, side in fs if (s, "fwd") in fs and (s, "rev") in fs})
        if not depths:
            continue
        maps_ = {k: np.clip((tifffile.imread(fs[k]).astype(np.float32) - 64) / 128, 0, 1)
                 for k in [(s, sd) for s in depths for sd in ("fwd", "rev")]}
        pool = np.concatenate([a[valid] for a in maps_.values()])
        mu, sd = float(pool.mean()), float(pool.std()) + 1e-6
        for side in ("fwd", "rev"):
            sides[side].append(np.mean([(maps_[(s, side)] - mu) / sd for s in depths], axis=0))
        used.append(f"{model} d={[s - 25 for s in depths]}")
    print("models used:", "; ".join(used))

    sig_bg = 2800 / UM          # ~2.8 mm
    sig_dn = 75 / UM            # ~0.075 mm
    proc = {}
    for side in ("fwd", "rev"):
        a = np.mean(sides[side], axis=0)
        a = a - masked_blur(a, m32, sig_bg)
        proc[side] = masked_blur(a, m32, sig_dn)
    both = np.concatenate([proc["fwd"][valid], proc["rev"][valid]])
    lo, hi = np.percentile(both, [2, 99.7])
    thr = np.percentile(both, 100 - float(top))
    corr = float(np.corrcoef(proc["fwd"][valid], proc["rev"][valid])[0, 1])
    print(f"shared stretch {lo:.3f}..{hi:.3f}, top-{top}% threshold {thr:.3f}, "
          f"forward/reverse correlation after processing {corr:+.3f}")

    def to8(a, lo_, hi_):
        b = (np.clip((a - lo_) / (hi_ - lo_), 0, 1) * 255).astype(np.uint8)
        b[~valid] = 0
        return b

    cl, ch = np.percentile(ct[valid], [1, 99.5])
    panels = [("CT surface (layer 33)", to8(ct, cl, ch)),
              ("FORWARD, enhanced", to8(proc["fwd"], lo, hi)),
              ("REVERSE, enhanced (same processing)", to8(proc["rev"], lo, hi)),
              (f"FORWARD, strongest {top}% only", ((proc["fwd"] > thr) & valid).astype(np.uint8) * 255),
              (f"REVERSE, strongest {top}% only (same cutoff)", ((proc["rev"] > thr) & valid).astype(np.uint8) * 255)]
    s = 4
    bar = int(round(2500 / UM / s))
    rows = []
    for name, img in panels:
        if orient == "rot180":       # reading orientation, as in run_ink.sh / ensemble_maps.py
            img = np.rot90(img, 2)
        im = cv2.cvtColor(cv2.resize(img, (img.shape[1] // s, img.shape[0] // s), interpolation=cv2.INTER_AREA),
                          cv2.COLOR_GRAY2BGR)
        cv2.putText(im, name, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
        cv2.rectangle(im, (10, im.shape[0] - 8 - bar), (18, im.shape[0] - 8), (0, 200, 255), -1)
        cv2.putText(im, "2.5 mm", (24, im.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
        rows += [im, np.full((6, im.shape[1], 3), 90, np.uint8)]
    cv2.imwrite(out, np.vstack(rows[:-1]))
    print("wrote", out)


if __name__ == "__main__":
    main(*sys.argv[1:])

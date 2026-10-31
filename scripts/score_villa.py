"""Score villa sweep outputs against registered ground truth; per model + z-score ensemble.

GT footprints come from scripts/register_rescore.py (CT-to-CT template match).
Usage: python score_villa.py <case> <sweep_dir>
"""
import glob
import os
from pathlib import Path
import re
import sys
from collections import defaultdict

import cv2
import numpy as np
import tifffile

DATA = str(Path(os.environ.get("VESUVIUS_ROOT", Path.home() / "vesuvius")) / "data")
CASES = {
    # registered L0 (2.4 um) footprint of the low-res crop: y0, y1, x0, x1
    "p09b": (os.path.join(DATA, "test864", "ref.tif"), (14784, 17548, 10160, 12924)),
    "w047": (os.path.join(DATA, "control", "w047_ref.tif"), (14476, 17956, 9976, 12960)),
}
PAT = re.compile(r"(?P<model>.+)_S(?P<s>\d+)_(?P<dir>forward|reverse)\.tif$")


def auc(pred, pos):
    v = pred.ravel()
    ranks = np.empty(v.size)
    ranks[np.argsort(v, kind="stable")] = np.arange(1, v.size + 1)
    npos = float(pos.sum())
    nneg = float(v.size - npos)
    return float((ranks[pos.ravel()].sum() - npos * (npos + 1) / 2) / (npos * nneg + 1e-9))


def main(case, sweep):
    gt_path, (y0, y1, x0, x1) = CASES[case]
    gt_full = tifffile.imread(gt_path)[y0:y1, x0:x1]
    maps = {}
    for p in sorted(glob.glob(os.path.join(sweep, "*.tif"))):
        m = PAT.search(os.path.basename(p))
        if not m:
            continue
        maps[(m["model"], int(m["s"]), m["dir"])] = tifffile.imread(p).astype(np.float32)
    if not maps:
        sys.exit("no sweep outputs found")
    shape = next(iter(maps.values())).shape
    gt = cv2.resize(gt_full, (shape[1], shape[0]), interpolation=cv2.INTER_AREA)
    pos = gt > 153
    print(f"{case}: {len(maps)} maps, grid {shape}, GT ink {100 * pos.mean():.1f}%")

    per_model = defaultdict(list)
    for (model, s, d), m in maps.items():
        per_model[model].append(((s, d), auc(m, pos)))
    print(f"\n{'model':10s} {'best':>16s} {'AUC':>7s}  fwd>0.5  rev>0.5")
    for model, rows in sorted(per_model.items()):
        (s, d), best = max(rows, key=lambda t: t[1])
        fwd = sum(1 for (k, a) in rows if k[1] == "forward" and a > 0.5)
        rev = sum(1 for (k, a) in rows if k[1] == "reverse" and a > 0.5)
        nf = sum(1 for (k, _) in rows if k[1] == "forward")
        nr = len(rows) - nf
        print(f"{model:10s} {f'S{s:02d} {d}':>16s} {best:7.4f}  {fwd:3d}/{nf:<3d}  {rev:3d}/{nr}")

    # ensemble: z-score each model over all its maps, average models per (S, dir)
    stats = {}
    for model in per_model:
        vals = np.concatenate([m.ravel() for (mm, _, _), m in maps.items() if mm == model])
        stats[model] = (float(vals.mean()), float(vals.std()) + 1e-6)
    keys = sorted({(s, d) for (_, s, d) in maps})
    models = sorted(per_model)
    ens_rows = []
    for s, d in keys:
        zs = [(maps[(mm, s, d)] - stats[mm][0]) / stats[mm][1]
              for mm in models if (mm, s, d) in maps]
        if len(zs) == len(models):
            ens_rows.append(((s, d), auc(np.mean(zs, axis=0), pos)))
    if ens_rows:
        print(f"\nENSEMBLE of {len(models)} models (per-model z-score, then mean):")
        for (s, d), a in sorted(ens_rows, key=lambda t: -t[1])[:8]:
            print(f"  S{s:02d} {d:8s} AUC {a:.4f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

"""Register low-res surface-volume crops to the 2.4 um render by CT texture,
then re-score ink predictions against the correctly aligned ground truth.

Earlier scoring assumed a coordinate mapping and stretched a larger low-res
footprint onto a smaller ground-truth tile. This measures the footprint from
the CT data itself instead.
"""
import glob
import json
import os
from pathlib import Path

import cv2
import numpy as np
import tifffile

ROOT = str(Path(os.environ.get("VESUVIUS_ROOT", Path.home() / "vesuvius")) / "data")

CASES = {
    "w047_9.362um": dict(
        low_dir=os.path.join(ROOT, "head2head", "r93", "sv", "0"),
        low_chunks=(29, 36, 20, 26),          # y0,y1,x0,x1 (exclusive)
        low_um=9.362,
        l2_dir=os.path.join(ROOT, "reg", "w047L2", "0"),
        l2_chunks=(27, 37, 18, 27),
        l2_um=9.596,
        gt_tif=os.path.join(ROOT, "control", "w047_ref.tif"),
        preds=os.path.join(ROOT, "head2head", "r93", "sweep_out", "*.png"),
    ),
    "p09b_8.64um": dict(
        low_dir=os.path.join(ROOT, "test864", "r864", "sv", "0"),
        low_chunks=(32, 38, 22, 28),
        low_um=8.64,
        l2_dir=os.path.join(ROOT, "reg", "p09bL2", "0"),
        l2_chunks=(27, 36, 18, 27),
        l2_um=9.604,
        gt_tif=os.path.join(ROOT, "test864", "ref.tif"),
        preds=os.path.join(ROOT, "test864", "out864", "*.png"),
    ),
}


def load_chunks(zdir, chunks):
    meta = json.load(open(os.path.join(zdir, ".zarray")))
    _, cy, cx = meta["chunks"]
    depth = meta["chunks"][0]
    y0, y1, x0, x1 = chunks
    vol = np.zeros((depth, (y1 - y0) * cy, (x1 - x0) * cx), np.uint8)
    for by in range(y0, y1):
        for bx in range(x0, x1):
            p = os.path.join(zdir, "0", str(by), str(bx))
            if not os.path.exists(p):
                continue
            d = np.fromfile(p, np.uint8)
            if d.size != depth * cy * cx:
                continue
            vol[:, (by - y0) * cy:(by - y0 + 1) * cy,
                (bx - x0) * cx:(bx - x0 + 1) * cx] = d.reshape(depth, cy, cx)
    return vol, (y0 * cy, x0 * cx)


def texture(img):
    img = img.astype(np.float32)
    hp = img - cv2.GaussianBlur(img, (0, 0), 6)
    return cv2.GaussianBlur(hp, (0, 0), 1)


def central_mean(vol, frac=0.3):
    z = vol.shape[0]
    a = int(z * (0.5 - frac / 2))
    b = max(a + 1, int(z * (0.5 + frac / 2)))
    return vol[a:b].astype(np.float32).mean(axis=0)


def auc_pearson(pred, gt):
    a = pred - pred.mean()
    b = gt - gt.mean()
    r = float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-9))
    pos = gt.ravel() > 0.6
    v = pred.ravel()
    ranks = np.empty(v.size)
    ranks[np.argsort(v, kind="stable")] = np.arange(1, v.size + 1)
    npos = float(pos.sum())
    nneg = float(v.size - npos)
    auc = float((ranks[pos].sum() - npos * (npos + 1) / 2) / (npos * nneg + 1e-9))
    return r, auc


def run(name, c):
    low, low_origin = load_chunks(c["low_dir"], c["low_chunks"])
    l2, l2_origin = load_chunks(c["l2_dir"], c["l2_chunks"])
    low_img = texture(central_mean(low))
    l2_img = texture(central_mean(l2))

    base = c["low_um"] / c["l2_um"]
    expected = ((low_origin[0] * base) - l2_origin[0],
                (low_origin[1] * base) - l2_origin[1])

    best = None
    for s in base * np.linspace(0.97, 1.03, 13):
        th = int(round(low_img.shape[0] * s))
        tw = int(round(low_img.shape[1] * s))
        if th >= l2_img.shape[0] or tw >= l2_img.shape[1]:
            continue
        tmpl = cv2.resize(low_img, (tw, th), interpolation=cv2.INTER_AREA)
        res = cv2.matchTemplate(l2_img, tmpl, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(res)
        # peak sharpness: best vs 2nd-best outside a 20px neighbourhood
        masked = res.copy()
        x, y = loc
        masked[max(0, y - 20):y + 21, max(0, x - 20):x + 21] = -1
        second = float(masked.max())
        if best is None or mx > best["ncc"]:
            best = dict(scale=float(s), ncc=float(mx), second=second,
                        y=int(y), x=int(x), th=th, tw=tw)

    assert best is not None, "template larger than search area at every scale"
    print(f"\n=== {name} ===")
    print(f"expected L2 offset (y,x) from assumed mapping: "
          f"({expected[0]:.1f}, {expected[1]:.1f}) at scale {base:.4f}")
    print(f"measured  L2 offset (y,x): ({best['y']}, {best['x']}) at scale "
          f"{best['scale']:.4f}   NCC peak {best['ncc']:.3f} "
          f"(next best {best['second']:.3f})")

    # ground truth footprint in L0 (2.4um) pixels: L2 px * 4
    gy0 = (l2_origin[0] + best["y"]) * 4
    gx0 = (l2_origin[1] + best["x"]) * 4
    gh, gw = best["th"] * 4, best["tw"] * 4
    gt_full = tifffile.imread(c["gt_tif"])
    gt = gt_full[gy0:gy0 + gh, gx0:gx0 + gw]
    print(f"GT footprint L0 y{gy0}:{gy0 + gh} x{gx0}:{gx0 + gw}  "
          f"ink {100 * float((gt > 153).mean()):.1f}%")

    rows = []
    for p in sorted(glob.glob(c["preds"])):
        im = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
        if im is None:
            continue
        g = cv2.resize(gt, (im.shape[1], im.shape[0]),
                       interpolation=cv2.INTER_AREA).astype(np.float32) / 255
        r, auc = auc_pearson(im.astype(np.float32) / 255, g)
        rows.append((os.path.basename(p), r, auc, 100 * float((im > 127).mean())))
    print(f"{'file':22s} {'pearson':>8s} {'AUC':>7s} {'pred%':>6s}")
    for f, r, auc, pc in sorted(rows, key=lambda t: -t[2]):
        print(f"{f:22s} {r:+8.4f} {auc:7.4f} {pc:6.2f}")
    above = sum(1 for row in rows if row[2] > 0.5)
    print(f"depths above chance: {above}/{len(rows)}")


if __name__ == "__main__":
    for k, v in CASES.items():
        run(k, v)

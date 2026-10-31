"""Quantify agreement between our reproduced ensemble and Nieuwlaar's published submission image.

His PNG = dimmed grey CT + light-yellow ink overlay, 1:1 render pixels plus margins, reading orientation.
Ink strength is recovered as yellowness = (R + G) / 2 - B (zero on grey CT). Our ensemble PNG (his
ensemble_maps.py, reading orientation) is located inside his image by normalised cross-correlation,
then compared: Pearson r, and AUC of our ensemble against his ink mask (yellowness > 40).
The blind-side ensemble is scored at the same location as a control.
"""
import sys

import cv2
import numpy as np


def auc(pred, pos):
    v = pred.ravel()
    ranks = np.empty(v.size)
    ranks[np.argsort(v, kind="stable")] = np.arange(1, v.size + 1)
    npos = float(pos.sum())
    nneg = float(v.size - npos)
    return float((ranks[pos.ravel()].sum() - npos * (npos + 1) / 2) / (npos * nneg + 1e-9))


def read(path, flags):
    img = cv2.imread(path, flags)
    if img is None:
        raise FileNotFoundError(path)
    return img.astype(np.float32)


def main(sub_png, ens_png, blind_png, out_png):
    sub = read(sub_png, cv2.IMREAD_COLOR)
    b, g, r = sub[..., 0], sub[..., 1], sub[..., 2]
    yellow = np.clip((r + g) / 2 - b, 0, 255)
    ens = read(ens_png, cv2.IMREAD_GRAYSCALE)
    blind = read(blind_png, cv2.IMREAD_GRAYSCALE)

    # claimed area in reading orientation: raw x 380..6021, y 105..2560 of a 6720x2560 render
    H, W = ens.shape
    x0, x1 = W - 6021, W - 380
    y0, y1 = H - 2560, H - 105
    tmpl = ens[y0:y1, x0:x1]
    blind_t = blind[y0:y1, x0:x1]

    # register at 1/4 scale, then refine at full scale around the coarse peak
    q = 4
    ys, ts = cv2.resize(yellow, None, fx=1 / q, fy=1 / q), cv2.resize(tmpl, None, fx=1 / q, fy=1 / q)
    res = cv2.matchTemplate(ys, ts, cv2.TM_CCOEFF_NORMED)
    _, mx, _, (cx, cy) = cv2.minMaxLoc(res)
    cx, cy = cx * q, cy * q
    pad = 3 * q
    sx0, sy0 = max(0, cx - pad), max(0, cy - pad)
    win = yellow[sy0:cy + tmpl.shape[0] + pad, sx0:cx + tmpl.shape[1] + pad]
    res2 = cv2.matchTemplate(win, tmpl, cv2.TM_CCOEFF_NORMED)
    _, mx2, _, (fx, fy) = cv2.minMaxLoc(res2)
    ox, oy = sx0 + fx, sy0 + fy
    print(f"template found at ({ox},{oy}) in submission, NCC coarse {mx:.3f} fine {mx2:.3f}")

    ref = yellow[oy:oy + tmpl.shape[0], ox:ox + tmpl.shape[1]]
    valid = tmpl > 0
    pos = (ref > 40) & valid
    for name, m in (("reading-side ensemble", tmpl), ("blind-side ensemble (control)", blind_t)):
        a, bb = m[valid] - m[valid].mean(), ref[valid] - ref[valid].mean()
        rr = float((a * bb).sum() / np.sqrt((a * a).sum() * (bb * bb).sum() + 1e-9))
        print(f"{name:32s} Pearson r {rr:+.3f}   AUC vs his ink mask {auc(m[valid], pos[valid]):.3f}")
    print(f"his ink mask covers {100 * pos[valid].mean():.1f}% of valid pixels")

    vis = np.zeros(tmpl.shape + (3,), np.uint8)
    vis[..., 1] = np.clip(ref * 1.5, 0, 255).astype(np.uint8)      # his ink: green
    t8 = np.clip(tmpl, 0, 255).astype(np.uint8)
    vis[..., 2] = t8                                                  # ours: magenta
    vis[..., 0] = t8
    vis = cv2.resize(vis, (vis.shape[1] // 3, vis.shape[0] // 3), interpolation=cv2.INTER_AREA)
    cv2.imwrite(out_png, vis)
    print("overlay (his=green, ours=magenta, agreement=white):", out_png)


if __name__ == "__main__":
    main(*sys.argv[1:5])

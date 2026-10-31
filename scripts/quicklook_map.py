"""Quick look at one villa ink map in Nieuwlaar's display convention.

villa uint8 v -> clip((v - 64) / 128, 0, 1); stretch p1..p99.5 over valid pixels;
reading orientation = rotate 180 degrees. Writes a downscaled PNG.
Usage: python quicklook_map.py <map.tif> <render.zarr> <out.png> [downscale]
"""
import sys

import cv2
import numpy as np
import tifffile
import zarr


def main(map_path: str, zarr_path: str, out: str, down_arg: str = "3") -> None:
    down = int(down_arg)
    m = tifffile.imread(map_path).astype(np.float32)
    p = np.clip((m - 64.0) / 128.0, 0, 1)
    ct = zarr.open(zarr_path, mode="r")["0"]
    valid = np.asarray(ct[33]) > 0
    lo, hi = np.percentile(p[valid], [1.0, 99.5])
    img = np.clip((p - lo) / max(hi - lo, 1e-6), 0, 1) * 255
    img[~valid] = 0
    img = np.rot90(img, 2).astype(np.uint8)
    img = cv2.resize(img, (img.shape[1] // down, img.shape[0] // down), interpolation=cv2.INTER_AREA)
    cv2.imwrite(out, img)
    print(out, img.shape, f"stretch {lo:.3f}..{hi:.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:])

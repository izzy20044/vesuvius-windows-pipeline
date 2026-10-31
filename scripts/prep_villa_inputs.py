"""Rebuild the dense_native checkpoint and write compact Zarr crops for villa infer."""
import json
import os
from pathlib import Path

import numpy as np
import torch
import zarr
from safetensors.torch import load_file

MODELS = str(Path(os.environ.get("VESUVIUS_ROOT", Path.home() / "vesuvius")) / "models")
DATA = str(Path(os.environ.get("VESUVIUS_ROOT", Path.home() / "vesuvius")) / "data")

# 1) dense_native: only safetensors + config are published; wrap as villa .pth
dn = os.path.join(MODELS, "dense_native")
out = os.path.join(dn, "dense_native_016000.pth")
if not os.path.exists(out):
    torch.save({
        "model": load_file(os.path.join(dn, "dense_native_016000.safetensors")),
        "config": json.load(open(os.path.join(dn, "train_dense_native.json"))),
        "step": 16000,
    }, out)
print("dense_native pth:", os.path.getsize(out), "bytes")


def crop_to_zarr(src_dir, chunks, dst):
    meta = json.load(open(os.path.join(src_dir, ".zarray")))
    depth, cy, cx = meta["chunks"]
    y0, y1, x0, x1 = chunks
    vol = np.zeros((depth, (y1 - y0) * cy, (x1 - x0) * cx), np.uint8)
    got = 0
    for by in range(y0, y1):
        for bx in range(x0, x1):
            p = os.path.join(src_dir, "0", str(by), str(bx))
            if not os.path.exists(p):
                continue
            d = np.fromfile(p, np.uint8)
            if d.size != depth * cy * cx:
                continue
            vol[:, (by - y0) * cy:(by - y0 + 1) * cy,
                (bx - x0) * cx:(bx - x0 + 1) * cx] = d.reshape(depth, cy, cx)
            got += 1
    root = zarr.open_group(dst, mode="w")
    root.create_dataset("0", data=vol, chunks=(depth, 128, 128),
                        dtype="u1", compressor=None, overwrite=True)
    print(f"{dst}: {vol.shape} from {got} chunks, nonzero "
          f"{100 * float((vol > 0).mean()):.1f}%")


# 2) PHerc0009B 8.64um crop (31 layers) and PHerc0139 w047 9.362um crop (28 layers)
crop_to_zarr(os.path.join(DATA, "test864", "r864", "sv", "0"), (32, 38, 22, 28),
             os.path.join(DATA, "villa_in", "p09b_864.zarr"))
crop_to_zarr(os.path.join(DATA, "head2head", "r93", "sv", "0"), (29, 36, 20, 26),
             os.path.join(DATA, "villa_in", "w047_9362.zarr"))

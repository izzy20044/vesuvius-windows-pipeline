"""Screen many rendered windings with one villa ink model, loading the model once.

Inputs are 26-layer renders (layer k samples the CT at k - 12.5 voxels along the normal), so depth d
(Nieuwlaar convention, d = 0 at offset +0.5) uses the 17-layer window starting at S = d + 5.
Output: <out>/<winding>__<model>__d<d>_<forward|reverse>.tif (uint8 p*255).

Usage: python screen_ink.py <out_dir> <model> <depths e.g. 0 or -1,0,1> <render.zarr> [<render.zarr> ...]
"""
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

import torch

from vesuvius.ink_detection.inference import infer as villa

W = Path(os.environ.get("W", "/workspace/vesuvius"))
CKPT = {
    "dnative": W / "models/dense_native_016000.pth",
    "ink9_s42": W / "models/ink9_s42.pth",
    "ink9_s43": W / "models/ink9_s43.pth",
}


def main(out, model, depths, *zarrs):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    ds = [int(d) for d in depths.split(",")]
    torch.set_float32_matmul_precision("high")
    args = villa.normalize_inference_paths(villa.parse_args([
        zarrs[0], str(CKPT[model]), str(out / "unused.tif"), "--no-compile",
        "--num-workers", os.environ.get("INK_WORKERS", "12"),
        "--batch-size", os.environ.get("INK_BATCH", "32"),
        "--overlap", "0.5", "--blend-mode", "hann"]))
    configured = villa.configure_model(args)
    net, device = villa.prepare_model_for_inference(
        configured.model, gpu_ids=args.gpu_ids, compile_model=False, compile_mode=args.compile_mode)
    configured = replace(configured, model=net)
    for z in zarrs:
        name = Path(z).stem
        for d in ds:
            args.layer_start, args.layer_end = d + 5, d + 5 + 17
            for direction in ("forward", "reverse"):
                dst = out / f"{name}__{model}__d{d:+d}_{direction}.tif"
                if dst.exists():
                    continue
                t = time.time()
                villa.infer_single_zarr(args=args, input_zarr=z, configured_model=configured,
                                        device=device, output_tiff=dst, layer_direction=direction)
                print(f"{dst.name} {time.time() - t:.0f}s", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])

"""Depth x orientation sweep for villa flat ink models, loading each model once.

Mirrors vesuvius.ink_detection.inference.infer.main() but loops layer windows
in-process. Output: <out>/<model>_S<start>_<direction>.tif (uint8, p*255).

Usage:
  python villa_sweep.py <surface.zarr> <out_dir> [--models a,b] [--starts 0-14]
"""
import os
import argparse
import logging
import time
from dataclasses import replace
from pathlib import Path

import torch

from vesuvius.ink_detection.inference import infer as villa

MODELS_DIR = Path(os.environ.get("VESUVIUS_ROOT", Path.home() / "vesuvius")) / "models"
MODELS = {
    "ink9_s42": MODELS_DIR / "ink_9um" / "hybrid_3d2d-seed42" / "step-075000.pth",
    "ink9_s43": MODELS_DIR / "ink_9um" / "hybrid_3d2d-seed43" / "step-075000.pth",
    "dnative": MODELS_DIR / "dense_native" / "dense_native_016000.pth",
    "reader_v2": MODELS_DIR / "reader_v2" / "reader-v2-step040000.pth",
}


def parse_range(text, depth, input_depth):
    if text is None:
        return list(range(0, depth - input_depth + 1))
    lo, _, hi = text.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zarr")
    ap.add_argument("out")
    ap.add_argument("--models", default=",".join(MODELS))
    ap.add_argument("--starts")
    ap.add_argument("--batch-size", default="8")
    ap.add_argument("--directions", default="forward,reverse")
    a = ap.parse_args()

    logging.basicConfig(level=logging.WARNING)
    torch.set_float32_matmul_precision("high")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    depth = villa.select_volume_level(
        villa.open_volume_root(a.zarr), "0", source=a.zarr).shape[0]

    for name in a.models.split(","):
        ckpt = MODELS[name]
        args = villa.normalize_inference_paths(villa.parse_args([
            a.zarr, str(ckpt), str(out / "unused.tif"),
            "--no-compile", "--num-workers", "0",
            "--batch-size", a.batch_size,
            "--overlap", "0.5", "--blend-mode", "hann",
        ]))
        t0 = time.time()
        configured = villa.configure_model(args)
        model, device = villa.prepare_model_for_inference(
            configured.model, gpu_ids=args.gpu_ids,
            compile_model=False, compile_mode=args.compile_mode)
        configured = replace(configured, model=model)
        k = configured.input_depth
        starts = parse_range(a.starts, depth, k)
        print(f"[{name}] input_depth={k} patch={configured.patch_size} "
              f"preprocessing={configured.preprocessing} starts={starts[0]}..{starts[-1]} "
              f"load {time.time() - t0:.1f}s", flush=True)

        for s in starts:
            args.layer_start, args.layer_end = s, s + k
            for direction in a.directions.split(","):
                dst = out / f"{name}_S{s:02d}_{direction}.tif"
                if dst.exists():
                    continue
                t1 = time.time()
                villa.infer_single_zarr(
                    args=args, input_zarr=args.input_zarr,
                    configured_model=configured, device=device,
                    output_tiff=dst, layer_direction=direction)
                print(f"  {dst.name} {time.time() - t1:.1f}s", flush=True)

        del configured, model
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()

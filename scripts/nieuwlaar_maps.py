"""Produce ink maps for a 66-layer render under Nieuwlaar's run_ink.sh naming, so his
ensemble_maps.py can be run unchanged on them.

villa:  <name>__<mk>__L66s<s>.tif (forward = blind) and ..._reverse.tif (reading), s = d + 25
hecate: <name>__hecate__L66zc<zc>.png and ..._reverse.png, zc = 32.5 + d

Usage: python nieuwlaar_maps.py <render.zarr> <maps_dir> --depths -1..3 [--models ...] [--native-um 8.64]
"""
import argparse
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import torch

from vesuvius.ink_detection.inference import infer as villa

VES = Path(os.environ.get("VESUVIUS_ROOT", Path.home() / "vesuvius"))
CKPT = {
    "dnative": VES / "models/dense_native/dense_native_016000.pth",
    "hybrid_3d2d-seed42": VES / "models/ink_9um/hybrid_3d2d-seed42/step-075000.pth",
    "hybrid_3d2d-seed43": VES / "models/ink_9um/hybrid_3d2d-seed43/step-075000.pth",
}
HECATE_PY = VES / "models/hecate.py"
HECATE_CK = VES / "models/hecate_9.6um.pth"
PREP_PY = VES / "nieuwlaar/ink/scripts/hecate_prep.py"


def depths(text):
    lo, hi = text.split("..")
    return list(range(int(lo), int(hi) + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zarr")
    ap.add_argument("maps")
    ap.add_argument("--depths", default="1..1")
    ap.add_argument("--models", default="dnative,hecate,hybrid_3d2d-seed42,hybrid_3d2d-seed43")
    ap.add_argument("--native-um", default="8.64")
    ap.add_argument("--batch-size", default="4")
    a = ap.parse_args()

    name = Path(a.zarr).stem
    out = Path(a.maps)
    out.mkdir(parents=True, exist_ok=True)
    ds = depths(a.depths)
    models = a.models.split(",")
    torch.set_float32_matmul_precision("high")

    for mk in [m for m in models if m != "hecate"]:
        args = villa.normalize_inference_paths(villa.parse_args([
            a.zarr, str(CKPT[mk]), str(out / "unused.tif"), "--no-compile",
            "--num-workers", "0", "--batch-size", a.batch_size,
            "--overlap", "0.5", "--blend-mode", "hann"]))
        configured = villa.configure_model(args)
        model, device = villa.prepare_model_for_inference(
            configured.model, gpu_ids=args.gpu_ids, compile_model=False,
            compile_mode=args.compile_mode)
        configured = replace(configured, model=model)
        for d in ds:
            s = d + 25
            args.layer_start, args.layer_end = s, s + 17
            for direction, suf in (("forward", ""), ("reverse", "_reverse")):
                dst = out / f"{name}__{mk}__L66s{s}{suf}.tif"
                if dst.exists():
                    continue
                t = time.time()
                villa.infer_single_zarr(args=args, input_zarr=args.input_zarr,
                                        configured_model=configured, device=device,
                                        output_tiff=dst, layer_direction=direction)
                print(f"{dst.name} {time.time() - t:.0f}s", flush=True)
        del configured, model
        torch.cuda.empty_cache()

    if "hecate" in models:
        tmp = out / "_hecate_tmp"
        tmp.mkdir(exist_ok=True)
        for d in ds:
            zc = f"{32.5 + d:.2f}"
            prep = tmp / f"prep_zc{zc}.zarr"
            if not prep.exists():
                subprocess.run([sys.executable, str(PREP_PY), "--src", a.zarr, "--out", str(prep),
                                "--native-um", a.native_um, "--native-um-z", a.native_um,
                                "--target-um", "9.6", "--z-center", zc, "--nz", "16"], check=True)
            for flag, suf in (([], ""), (["--reverse"], "_reverse")):
                dst = out / f"{name}__hecate__L66zc{zc}{suf}.png"
                if dst.exists():
                    continue
                t = time.time()
                env = dict(os.environ, TMPDIR=str(tmp), TEMP=str(tmp), TMP=str(tmp))
                subprocess.run([sys.executable, str(HECATE_PY), "--checkpoint", str(HECATE_CK),
                                "--input", str(prep), "--spacing-um", "9.6", "--output", str(dst),
                                "--device", "cuda", "--batch-size", "4", *flag],
                               check=True, env=env, stdout=subprocess.DEVNULL)
                print(f"{dst.name} {time.time() - t:.0f}s", flush=True)


if __name__ == "__main__":
    main()

#!/bin/bash
# setup_pod.sh - recreate the validated PHerc0358 pipeline on a Linux GPU pod (RunPod, Ubuntu, CUDA 12.8+).
#
#   bash setup_pod.sh            # everything below, idempotent; re-run after interruptions
#
# Mirrors what was validated on the Windows workstation on 2026-10-30:
#   - villa 0fb38c45 (Nieuwlaar's PHerc0343 commit): vesuvius ink inference + volume-cartographer/scripts/spiral
#   - fit_spiral shell-optional patch, native vc.track_crossings (+ track_store, which builds on Linux)
#   - ink checkpoints with published sha256 (ink9 s42/s43, dense_native, Hecate 9.6um)
#   - PHerc0358 inputs for z 8700-10200: tracks + crossings cache, lasagna nx/ny/grad_mag g2, m7 L0/L1, CT L4
set -euo pipefail
W=${W:-/workspace/vesuvius}
mkdir -p "$W" && cd "$W"
log() { echo "[$(date +%T)] $*"; }
# nproc reports the host's cores; the container's real share is the cgroup CPU quota
read -r q p < /sys/fs/cgroup/cpu.max 2>/dev/null || q=max
CPUS=${CPUS:-$([[ $q != max ]] && echo $(( q / p )) || nproc)}
export OMP_NUM_THREADS=$CPUS MKL_NUM_THREADS=$CPUS
log "using $CPUS CPUs (cgroup quota)"

log "system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq git cmake build-essential curl unzip pigz rsync >/dev/null
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; }
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.14.2 >/dev/null

log "villa @ 0fb38c45 (sparse) + shell-optional patch"
if [[ ! -d villa ]]; then
  git clone --filter=blob:none --no-checkout -q https://github.com/ScrollPrize/villa.git villa
  git -C villa sparse-checkout init --cone
  git -C villa sparse-checkout set vesuvius volume-cartographer/scripts/spiral volume-cartographer/python
  git -C villa checkout -q 0fb38c45b488e192566ea83ae36369cb6db92652
fi
[[ -d nieuwlaar ]] || git clone -q --depth 1 https://github.com/Nieuwlaar/pherc343-first-letters.git nieuwlaar
git -C villa apply --check ../nieuwlaar/mesh/fit_spiral_shell_optional.patch 2>/dev/null \
  && git -C villa apply ../nieuwlaar/mesh/fit_spiral_shell_optional.patch || log "  patch already applied"

log "venv_spiral (torch <2.13 cu128, native triton) + native vc modules"
if [[ ! -x venv_spiral/bin/python ]]; then
  uv venv -q --seed --python 3.14.2 venv_spiral
  venv_spiral/bin/pip install -q "torch>=2.11,<2.13" --index-url https://download.pytorch.org/whl/cu128
  venv_spiral/bin/pip install -q click crackle-codec edt einops imageio "kimimaro[all]" kornia libigl matplotlib \
    networkx numpy opencv-python-headless pillow pyro-ppl rustworkx s3fs scipy tifffile tensorstore threadpoolctl \
    torchdiffeq tqdm trimesh wandb "zarr>=3.2.1" nanobind
fi
SP=$(venv_spiral/bin/python -c 'import site; print(site.getsitepackages()[0])')
if ! venv_spiral/bin/python -c 'import vc.track_crossings, vc.track_store' 2>/dev/null; then
  mkdir -p build_vc && cat > build_vc/CMakeLists.txt <<'EOF'
cmake_minimum_required(VERSION 3.26)
project(vc_native CXX)
find_package(Python 3.14 COMPONENTS Interpreter Development.Module REQUIRED)
execute_process(COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
                OUTPUT_STRIP_TRAILING_WHITESPACE OUTPUT_VARIABLE nanobind_ROOT)
find_package(nanobind CONFIG REQUIRED)
find_package(OpenMP REQUIRED)
foreach(m track_crossings track_store)
  nanobind_add_module(${m} NOMINSIZE ${SRC}/vc/${m}.cpp)
  target_compile_features(${m} PRIVATE cxx_std_23)
  target_compile_options(${m} PRIVATE -O3)
  target_link_libraries(${m} PRIVATE OpenMP::OpenMP_CXX)
endforeach()
EOF
  cmake -S build_vc -B build_vc/build -DPython_EXECUTABLE="$W/venv_spiral/bin/python" \
    -DSRC="$W/villa/volume-cartographer/python" -DCMAKE_BUILD_TYPE=Release >/dev/null
  cmake --build build_vc/build -j "$CPUS" >/dev/null
  mkdir -p "$SP/vc"
  printf '"""Minimal vc package: native track kernels only (vc.volume not built)."""\n' > "$SP/vc/__init__.py"
  cp build_vc/build/track_*.so "$SP/vc/"
fi
venv_spiral/bin/python - <<'EOF'
import numpy as np, vc.track_crossings as t
a = np.random.default_rng(0).integers(0, 2**60, 3_000_000, dtype=np.uint64); a[::5] = a[1]
o = np.asarray(t.parallel_argsort(a, workers=16))
assert np.array_equal(a[o], np.sort(a)), "native radix sort wrong"
print("  vc.track_crossings OK (60-bit sort verified, 16 threads)")
EOF


# ---- everything below runs as concurrent jobs, each with its own log: setup_<job>.log ----
DS=$W/spiral/PHerc0358; mkdir -p "$DS/tracks" "$DS/lasagna_inputs" "$DS/src" models
HF=https://huggingface.co

job_ink() {   # villa ink inference env (torch cu130, as validated locally)
  if [[ ! -x venv_ink/bin/python ]] || ! venv_ink/bin/python -c "import vesuvius.ink_detection.inference.infer" 2>/dev/null; then
    rm -rf venv_ink; uv venv -q --seed --python 3.14.2 venv_ink
    venv_ink/bin/pip install -q "torch>=2.12,<3" torchvision --index-url https://download.pytorch.org/whl/cu130
    venv_ink/bin/pip install -q numpy pillow "zarr<3" "numcodecs<0.17" tifffile imagecodecs fsspec s3fs timm einops \
      opencv-python-headless scipy tqdm huggingface-hub cachetools safetensors requests pynrrd pyyaml edt nest-asyncio \
      accelerate pytorch-lightning pytorch-optimizer monai dynamic-network-architectures numba batchgenerators \
      fft-conv-pytorch fvcore scikit-image connected-components-3d pandas typed-argument-parser psutil aiohttp blosc2 \
      dask lxml tensorstore
    venv_ink/bin/pip install -q --no-deps -e villa/vesuvius
  fi
  venv_ink/bin/python -c "import vesuvius.ink_detection.inference.infer; import torch; print('ink env OK, torch', torch.__version__, 'cuda', torch.cuda.is_available())"
}

job_models() {   # checkpoints, sha256-verified, fetched concurrently
  cd models
  fetch() { [[ -s $2 ]] || curl -sL --retry 5 -o "$2" "$1"; echo "$3  $2" | sha256sum -c --quiet; }
  fetch $HF/scrollprize/ink_9um/resolve/main/hybrid_3d2d-seed42/step-075000.pth ink9_s42.pth e635558ae6a1a807a7e5ec1e83adfd45bc3c0ac53883ea43f1d4e085d62a9cab &
  fetch $HF/scrollprize/ink_9um/resolve/main/hybrid_3d2d-seed43/step-075000.pth ink9_s43.pth 2aeaa85a35ef28d7bc7bf3e848c4a6a91385e9132710927fdba41133c4ecb28f &
  fetch $HF/scrollprize/hecate/resolve/main/hecate_9.6um.pth hecate_9.6um.pth 809f4f10f7cb7afa19b4bee0f7d2ab31edd7e11b664f9f210cc9c17f22fcfe5d &
  fetch $HF/scrollprize/hecate/resolve/main/hecate.py hecate.py c232c18a1a86cfb91257a00db13288202bb8ae33732ba26f7291a9b8adb8da59 &
  fetch $HF/Nieuwlaar/ink9um-dense-native/resolve/main/weights/dense_native_016000.safetensors dense_native.safetensors d3d95dc41dcb24ed76b84b5e12ca5dae25d7fb34edf1dfbb93e0186f91e6fc6d &
  fetch $HF/Nieuwlaar/ink9um-dense-native/resolve/main/training/configs/train_dense_native.json dense_native.json 5d8459030b36cd3980a03610c684365a7407d497173eff433efdb37f75840c86 &
  local rc=0; for p in $(jobs -p); do wait "$p" || rc=1; done; [[ $rc == 0 ]] && echo "6 checkpoints OK (sha256)"; return $rc
}

job_vc3d() {   # Linux VC3D AppImage, extracted (no FUSE needed)
  if [[ ! -x vc3d/AppRun ]]; then
    url=$(curl -s https://api.github.com/repos/ScrollPrize/villa/releases/tags/latest \
      | grep -oE '"browser_download_url": *"[^"]+linux-x86_64\.AppImage"' | head -1 | sed 's/.*"\(http[^"]*\)"/\1/')
    curl -sL -o vc3d.AppImage "$url" && chmod +x vc3d.AppImage
    rm -rf squashfs-root && ./vc3d.AppImage --appimage-extract >/dev/null && mv squashfs-root vc3d
  fi
  ls vc3d/usr/bin | grep -c vc_ | xargs echo "VC3D tools:"
}

job_data() {   # PHerc0358 inputs for z 8700-10200, all downloads concurrent, then the distance field
  local TU=https://dl.ash2txt.org/datasets/spiral_datasets/PHerc0358/20250821151737/tracks
  local TF=PHerc0358_20250821151737_surface_m7_L0_th0.2
  local L=PHerc0358/representations/predictions/lasagna/20250821151737-lasagna-20260419180421
  local S=PHerc0358/representations/predictions/surfaces/20250821151737-surface-20260413222639-surface-m7-L0-th0.2.zarr
  local V=PHerc0358/volumes/20250821151737-9.362um-1.2m-113keV-masked.zarr
  local FZ="python3 pod/fetch_zarr_band.py"   # stdlib only
  for f in $TF.dbm $TF.dbm.crossings.npz; do curl -s -C - --retry 10 -o "$DS/tracks/$f" "$TU/$f" & done
  for a in nx ny grad_mag; do $FZ "$L/PHerc0358_$a.ome.zarr" 2 2112 2624 "$DS/lasagna_inputs/las_008_$a.ome.zarr" & done
  $FZ "$S" 1 4224 5376 "$DS/src/m7.zarr" &
  $FZ "$V" 4 512 768 "$DS/src/ct.zarr" &
  local rc=0; for p in $(jobs -p); do wait "$p" || rc=1; done; [[ $rc == 0 ]] || return 1
  $FZ "$S" 0 8640 10368 "$DS/src/m7.zarr" &      # m7 L0 (for snapping) overlaps with the distance field build
  local m7l0=$!
  venv_spiral/bin/python - "$DS/tracks/$TF.dbm" <<'EOF'
import json, os, sys, numpy as np
p = sys.argv[1]
with np.load(p + '.crossings.npz', allow_pickle=False) as s:
    sig = json.loads(str(s['metadata'].item()))['db_signature'][0]
assert os.path.getsize(p) == sig[1], 'track file size differs from cache signature'
os.utime(p, ns=(os.stat(p).st_atime_ns, sig[2])); print('tracks mtime restored; cache signature matches')
EOF
  cp pod/umbilicus.json pod/spiral-scroll.json pod/spiral-scroll-cw.json "$DS/"
  if [[ ! -d $DS/lasagna_inputs/las_008_surf_sdt.ome.zarr/1 ]]; then
    (cd "$DS" && "$W/venv_spiral/bin/python" "$W/villa/volume-cartographer/scripts/spiral/make_surf_sdt.py" \
      --surf src/m7.zarr --group 1 --out lasagna_inputs/las_008_surf_sdt.ome.zarr --threshold 128 --scale 2 \
      --working-voxel-um 9.362 --z-range 8636:10264 --ct src/ct.zarr --ct-group 4 --ct-dilate 1 --no-ct-zero \
      --workers "$CPUS")
  fi
  wait "$m7l0"; echo "dataset + distance field OK"
}

declare -A PIDS
for j in ink models vc3d data; do ( set -euo pipefail; "job_$j" ) > "$W/setup_$j.log" 2>&1 & PIDS[$j]=$!; log "started job $j (setup_$j.log)"; done
fail=0
for j in ink models vc3d data; do
  if wait "${PIDS[$j]}"; then log "job $j OK: $(tail -1 "$W/setup_$j.log")"; else log "job $j FAILED: $(tail -3 "$W/setup_$j.log" | tr '\n' ' ')"; fail=1; fi
done
[[ $fail == 0 ]] || exit 1

[[ -s models/dense_native_016000.pth ]] || (cd models && ../venv_ink/bin/python -c "
import json, torch; from safetensors.torch import load_file
torch.save({'model': load_file('dense_native.safetensors'), 'config': json.load(open('dense_native.json')), 'step': 16000}, 'dense_native_016000.pth')")
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
log "SETUP COMPLETE"

# Native Windows setup

Tested on Windows 10, RTX 3070 Ti (8 GB), driver 610.74, Python 3.14.2 (uv), MSVC 2022, CMake 4.2.

## 1. Ink inference (villa `vesuvius.ink_detection`)

* PyPI `vesuvius` (0.2.4) has **no** `ink_detection`; it only exists in the villa monorepo.
  Commit `0fb38c45` is the one Nieuwlaar used for PHerc. 343.
* villa's `models` extra cannot resolve on Windows (Linux-only `required-environments`, monorepo path
  dependencies, `cucim-cu13`). Install the package with `--no-deps` and add runtime deps yourself:

```powershell
venv314\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
venv314\Scripts\python -m pip install numpy pillow "zarr<3" "numcodecs<0.17" tifffile imagecodecs fsspec s3fs ^
  timm einops opencv-python-headless scipy tqdm huggingface-hub cachetools safetensors requests pynrrd pyyaml ^
  edt nest-asyncio accelerate pytorch-lightning pytorch-optimizer monai dynamic-network-architectures numba ^
  batchgenerators fft-conv-pytorch fvcore scikit-image connected-components-3d pandas typed-argument-parser ^
  psutil aiohttp blosc2 dask lxml tensorstore
venv314\Scripts\python -m pip install --no-deps -e villa\vesuvius
```

* Run inference with `--no-compile` (no Triton for Inductor on Windows) and `--num-workers 0` on 8 GB
  cards. `scripts/villa_sweep.py` loads each model once and loops depth windows in-process; a 768x768
  window takes ~2 s after a ~1.5 s model load.
* `dense_native` is published as safetensors + config; `scripts/prep_villa_inputs.py` wraps it into a
  villa-loadable `.pth`.

## 2. Hecate

* Inputs must be pre-resampled to exactly 9.6 um (16 planes) or 2.4 um (64 planes); Hecate refuses
  anything else.
* On Windows, a failure inside `predict()` is hidden behind a `PermissionError` from
  `TemporaryDirectory` cleanup (the memmap is still open). `patches/hecate_windows_memmap.patch`
  closes the memmap before cleanup so real errors surface.

## 3. Rendering (VC3D)

* Use the official `VC3D-*-win64.zip` release; `vc_render_tifxyz.exe --volume <https URL> ...` streams
  from the open-data bucket.
* On Windows the renderer **does not exit** after writing its outputs. Watch the log / last write
  time and stop the process once all pyramid levels are written (it exits normally on Linux).
* villa reads level 0; present renders as a level-0-only zarr group (a directory junction to `0/`
  plus a `.zgroup`) so its occupancy scan selects the same patches as on Linux.

## 4. Spiral fitting

* Use `volume-cartographer/scripts/spiral` at villa `0fb38c45`. Current `main` moved it to
  `spiral-fitting/` and added `vc-object-store`, a C++ package that needs SQLite3 dev libraries.
* Environment: Python 3.14.2, `torch>=2.11,<2.13` from the cu128 index (newer torch needs much
  more VRAM), `triton-windows>=3.6,<3.7`, and the package list in `pod/setup_pod.sh`.
* The default `track_walk` crossing mode needs the native `vc.track_crossings` module. Build it
  standalone with `native/CMakeLists.txt`:

```powershell
cmake -S native -B native/build -G "Visual Studio 17 2022" -A x64 `
  -DPython_EXECUTABLE=<venv>\Scripts\python.exe -DVC_OPENMP=OFF
cmake --build native/build --config Release
# copy track_crossings.cp314-win_amd64.pyd into <venv>\Lib\site-packages\vc\ next to a minimal __init__.py
```

  * Build it **without OpenMP** (`VC_OPENMP=OFF`). An `/openmp:llvm` build loads `libomp140` while
    torch loads Intel's `libiomp5md`, and the process aborts with `OMP: Error #15`. The suggested
    `KMP_DUPLICATE_LIB_OK=TRUE` is documented as able to give silently wrong results; don't use it.
  * Its radix sort is designed for 60-bit packed voxel keys. Testing it with 62-bit random keys
    looks like a bug but is outside its contract; it is exact at 59 and 60 bits with duplicates.
  * `track_store.cpp` uses POSIX `mmap`; the fitter falls back to Python memory-mapping.
* Published `*.dbm.crossings.npz` caches record the DBM's `mtime_ns`. A byte-identical download has a
  new mtime, and NTFS (100 ns ticks) cannot hold the original value, so the 1.4 GB cache is rejected
  and recomputed. `scripts/rebind_crossing_cache.py` rewrites only the signature after checking name and
  size (on Linux, restoring the mtime with `os.utime(ns=...)` is enough).
* **8 GB is not enough** for a 1,500-slice band with lasagna normals and the surface distance field
  (4.6 GiB resident). Windows does not fail with out-of-memory; it spills to system RAM and the fit
  slows to an estimated ~389 h. Use a >= 24 GB card for full bands (see [POD.md](POD.md)).

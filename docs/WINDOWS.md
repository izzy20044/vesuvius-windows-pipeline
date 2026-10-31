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
* On Windows, an error inside `predict()` (for example "Insufficient depth") is followed by a long
  `PermissionError` traceback from `TemporaryDirectory` cleanup, because the memmap is still open.
  The real error is the **first** traceback; read the head of the output, not the tail.
  `patches/hecate_windows_memmap.patch` closes the memmap explicitly; it is optional.

## 3. Rendering (VC3D)

* Use the official `VC3D-*-win64.zip` release; `vc_render_tifxyz.exe --volume <https URL> ...` streams
  from the open-data bucket.
* On the test machine (Windows 10, build `32a4958`), `vc_render_tifxyz.exe` processes did not fully
  terminate: the process reports an exit code, but its kernel object (~270 MB working set) stays
  listed in `Win32_Process`, cannot be killed, and clears only on reboot. A full render still wrote
  all outputs; small cropped renders wrote none. It could not be attributed to VC3D rather than the
  machine (security software or network drivers can cause this), so it was not reported upstream.
  Watch the log and the output files rather than the process. On Linux the renderer exits normally.
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

  * (On villa `main` as of 2026-10-30, `track_crossings.cpp` no longer uses OpenMP, so this point and
    villa issue #1633 only apply to `0fb38c45`-era sources.)
  * Build it **without OpenMP** (`VC_OPENMP=OFF`). An `/openmp:llvm` build loads `libomp140` while
    torch loads Intel's `libiomp5md`, and the process aborts with `OMP: Error #15`. The suggested
    `KMP_DUPLICATE_LIB_OK=TRUE` is documented as able to give silently wrong results; don't use it.
  * Its radix sort is designed for 60-bit packed voxel keys. Testing it with 62-bit random keys
    looks like a bug but is outside its contract; it is exact at 59 and 60 bits with duplicates.
  * `track_store.cpp` uses POSIX `mmap`; the fitter falls back to Python memory-mapping.
* Published `*.dbm.crossings.npz` caches record the DBM's `mtime_ns`. A byte-identical download has a
  new mtime, and NTFS (100 ns ticks) cannot hold the original value, so the 1.4 GB cache is rejected
  and recomputed. `scripts/rebind_crossing_cache.py` rewrites only the signature after checking name and
  size (on Linux, restoring the mtime with `os.utime(ns=...)` is enough). villa `main` now falls back
  to a content check when the signature differs, so newer fitter versions accept the cache directly.
* **8 GB is not enough** for a 1,500-slice band with lasagna normals and the surface distance field
  (4.6 GiB resident). Windows does not fail with out-of-memory; it spills to system RAM and the fit
  slows to an estimated ~389 h. Use a >= 24 GB card for full bands (see [POD.md](POD.md)).

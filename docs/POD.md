# Unattended GPU pod pipeline (Linux, RunPod-tested)

Takes an unread scroll from published spiral tracks to a ranked ink screen. Tested on a RunPod A100
SXM 80 GB (Community Cloud), image `runpod/pytorch:1.5.0-cu1281-torch2121-ubuntu2404`, 300 GB volume.
Configured here for PHerc0358 (`20250821151737`, 9.362 um); change the dataset ids in the scripts for
another scroll.

```bash
scp pod/* root@<pod>:/workspace/vesuvius/pod/
ssh root@<pod> 'cd /workspace/vesuvius && nohup bash pod/setup_pod.sh > setup.log 2>&1 &
                nohup bash pod/pipeline.sh > /dev/null 2>&1 & nohup bash pod/after_fits.sh > /dev/null 2>&1 &'
# progress: STATUS, BAND2_STATUS, SCREEN_STATUS, pipeline.log, screen/<run>/screen.log
```

| stage | script | notes |
|---|---|---|
| setup | `setup_pod.sh` | idempotent; ink env, checkpoints (sha256), VC3D, data downloads and the distance field run as **concurrent jobs** (~10 min) |
| fit | `pipeline.sh` -> `run_fit.sh` | 2,000-step ACW and CW tests, then a main fit sized from the measured step time to finish before `FIT_DEADLINE` (budget control) |
| second band | `band2.sh` | fits an adjacent z band **on the same GPU** concurrently (spiral fitting leaves ~half the GPU idle) |
| screen | `after_fits.sh` -> `screen.sh` | snap (Nieuwlaar's `snap_meshes.py`), render 26 layers per winding, dense_native both sides, score |
| scoring | `score_winding.py` | per ~1.4 x 1.4 cm tile: mean(reverse - forward) ink probability; drift artifacts cancel |

Recipe = Nieuwlaar's PHerc0343 chain: tracks + lasagna normals (group 2, `lasagna_scale` 4) + a capped
surface distance field from the m7 prediction, `dense_spacing_mode: phase`, patches off, his
shell-optional patch. Data are fetched for the fit band only (`fetch_zarr_band.py` lists the chunks
that exist per z layer and downloads them with a thread pool).

Linux notes:

* `nproc` reports the host's cores in a container; the scripts use the cgroup quota (`/sys/fs/cgroup/cpu.max`).
* On Linux the published crossings cache validates once the DBM's original `mtime_ns` is restored.
* The cu128 index has no torch >= 2.12 for Python 3.14; the ink env uses cu130 (driver >= CUDA 13).
* The container disk (`/`, 50 GB on RunPod) fills up silently: VC3D caches every streamed chunk in
  `~/.VC3D/remote_cache` (47 GB after ~80 winding renders) and villa writes full-size temp zarrs to
  `$TMPDIR`. `setup_pod.sh` symlinks the cache to the volume and `screen.sh` sets `TMPDIR` there;
  without that, ink inference fails with `OSError: [Errno 28] No space left on device`.
* **Idle billing.** A pod keeps billing at full GPU rate after the work ends. `after_fits.sh` and
  `screen_pre.sh` finish with `autostop.sh`, which stops the pod after a 20-minute grace period for
  copying results (`touch KEEP_ALIVE` cancels it). Without it, a dropped session left an A100 idle
  for ~2h20m in testing. Stopping keeps the volume; terminate in the console when done.
* `pkill -f <script>` from an ssh command line matches the ssh shell itself; `relaunch.sh` uses
  bracketed patterns.

Measured on the A100: test fit 2,000 steps in 14-21 min (first run includes Triton compilation),
one 1,500-slice winding render ~46 s, one 13 Mpx ink map ~40 s.

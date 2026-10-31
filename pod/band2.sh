#!/bin/bash
# band2.sh - second z band (7200-8700) fitted alongside the main fit, using the GPU's idle half.
# Same recipe and inputs as band 1; data fetched for this band only, SDT tiles appended with --resume.
# Progress: BAND2_STATUS, band2.log
set -uo pipefail
W=/workspace/vesuvius; cd "$W"
DS=$W/spiral/PHerc0358
say() { echo "[$(date +%T)] $*" | tee -a "$W/band2.log"; echo "$*" > "$W/BAND2_STATUS"; }
read -r q p < /sys/fs/cgroup/cpu.max; CPUS=$(( q / p ))
L=PHerc0358/representations/predictions/lasagna/20250821151737-lasagna-20260419180421
S=PHerc0358/representations/predictions/surfaces/20250821151737-surface-20260413222639-surface-m7-L0-th0.2.zarr
V=PHerc0358/volumes/20250821151737-9.362um-1.2m-113keV-masked.zarr
FZ="python3 pod/fetch_zarr_band.py"

say "band2 fetch (z 7200-8700)"
for a in nx ny grad_mag; do $FZ "$L/PHerc0358_$a.ome.zarr" 2 1728 2240 "$DS/lasagna_inputs/las_008_$a.ome.zarr" >> band2.log 2>&1 & done
$FZ "$S" 1 3456 4608 "$DS/src/m7.zarr" >> band2.log 2>&1 &
$FZ "$V" 4 384 640 "$DS/src/ct.zarr" >> band2.log 2>&1 &
rc=0; for j in $(jobs -p); do wait "$j" || rc=1; done
[[ $rc == 0 ]] || { say "BAND2 FAILED in fetch"; exit 1; }
$FZ "$S" 0 7104 8832 "$DS/src/m7.zarr" >> band2.log 2>&1 &     # for snapping later, overlaps the SDT build
m7l0=$!

say "band2 distance field (resume, z 7136:8764)"
(cd "$DS" && "$W/venv_spiral/bin/python" "$W/villa/volume-cartographer/scripts/spiral/make_surf_sdt.py" \
  --surf src/m7.zarr --group 1 --out lasagna_inputs/las_008_surf_sdt.ome.zarr --threshold 128 --scale 2 \
  --working-voxel-um 9.362 --z-range 7136:8764 --ct src/ct.zarr --ct-group 4 --ct-dilate 1 --no-ct-zero \
  --workers $(( CPUS - 6 )) --resume) >> band2.log 2>&1 || { say "BAND2 FAILED in distance field"; exit 1; }
wait "$m7l0" || { say "BAND2 FAILED fetching m7 L0"; exit 1; }

say "band2 fit ACW 10000 steps"
bash pod/run_fit.sh ACW 10000 7200 8700 band2-ACW >> band2.log 2>&1 \
  && say "BAND2 FIT DONE" || say "BAND2 FIT FAILED - see spiral/runs/band2-ACW/fit.log"

#!/bin/bash
# render_winding.sh <mesh.tifxyz dir> <out.zarr> [num_slices]  - VC3D render streamed from S3, level 0 only.
# Layer k samples the CT at k - (N-1)/2 voxels along the mesh normal (N = num_slices, default 26).
set -euo pipefail
MESH=$1; OUT=$2; N=${3:-26}
W=/workspace/vesuvius
VOL=https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com/PHerc0358/volumes/20250821151737-9.362um-1.2m-113keV-masked.zarr
[[ -f $OUT/0/.zarray ]] && exit 0
tmp=$OUT.part; rm -rf "$tmp"
QT_QPA_PLATFORM=offscreen OMP_NUM_THREADS=${RENDER_THREADS:-8} \
  timeout 1800 "$W/vc3d/AppRun" vc_render_tifxyz --volume "$VOL" --group-idx 0 --scale 1 \
  --segmentation "$MESH" --num-slices "$N" --slice-step 1 --cache-gb 16 --zarr-output "$tmp" > "$tmp.log" 2>&1
# villa reads level 0; drop pyramid levels and keep a plain zarr group
for l in 1 2 3 4 5; do rm -rf "$tmp/$l"; done
mv "$tmp" "$OUT"

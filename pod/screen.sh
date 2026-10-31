#!/bin/bash
# screen.sh <run_tag> <z0> <z1> - snap, render and ink-screen windings w030..w110 (every other) of a fit.
# Two workers: each renders a snapped winding (26 layers) then runs dense_native at d=0 on both sides
# and scores side asymmetry. Results: screen/<tag>/scores.tsv (+ ranked.tsv) and thumbs/<winding>.png.
set -uo pipefail
TAG=$1; Z0=$2; Z1=$3
W=/workspace/vesuvius; cd "$W"
# keep temp files (villa writes full-size probability zarrs) on the volume, not the 50 GB container disk
export TMPDIR=$W/tmp; mkdir -p "$TMPDIR"
OUT=$W/screen/$TAG; mkdir -p "$OUT"/{renders,maps,thumbs}
LOG=$OUT/screen.log
say() { echo "[$(date +%T)] $*" | tee -a "$LOG"; }
MESHDIR=$(ls -d spiral/runs/$TAG/*/meshes/fitted_$TAG | head -1)
[[ -d $MESHDIR ]] || { say "no meshes for $TAG"; exit 1; }

for i in ${WINDINGS:-$(seq 30 2 110)}; do printf 'w%03d_spliced_%s\n' "$i" "$TAG"; done > "$OUT/windings.txt"
say "snap $(wc -l < "$OUT/windings.txt") windings from $MESHDIR"
SURF_ZARR=$W/spiral/PHerc0358/src/m7.zarr "$W/venv_spiral/bin/python" nieuwlaar/mesh/snap_meshes.py \
  "$MESHDIR" PHerc0358 "$OUT/snapped" --windings "$OUT/windings.txt" --z0 "$Z0" --z1 "$Z1" --level 0 \
  --procs 12 >> "$LOG" 2>&1 || { say "SNAP FAILED"; exit 1; }
say "snap done"

worker() {   # $1 = list file
  while read -r w; do
    [[ -f $OUT/snapped/$w/x.tif ]] || continue
    r=$OUT/renders/$w.zarr
    RENDER_THREADS=6 bash pod/render_winding.sh "$OUT/snapped/$w" "$r" 26 || { say "render failed $w"; continue; }
    INK_WORKERS=6 venv_ink/bin/python pod/screen_ink.py "$OUT/maps" dnative 0 "$r" >> "$LOG" 2>&1 || { say "ink failed $w"; continue; }
    # screen_ink names maps after the render's stem
    venv_ink/bin/python pod/score_winding.py "$r" "$OUT/maps" "$w" dnative "$OUT/thumbs" >> "$OUT/scores.tsv" 2>>"$LOG" \
      && say "scored $w: $(tail -1 "$OUT/scores.tsv" | cut -f2-3)"
  done < "$1"
}
awk 'NR % 2 == 1' "$OUT/windings.txt" > "$OUT/list_a"; awk 'NR % 2 == 0' "$OUT/windings.txt" > "$OUT/list_b"
worker "$OUT/list_a" & worker "$OUT/list_b" & wait
sort -t$'\t' -k3,3gr "$OUT/scores.tsv" | awk -F'\t' '{a=$3<0?-$3:$3; print a"\t"$0}' | sort -gr | cut -f2- > "$OUT/ranked.tsv"
say "SCREEN DONE $TAG: $(wc -l < "$OUT/scores.tsv") windings scored; top: $(head -1 "$OUT/ranked.tsv" | cut -f1,3)"

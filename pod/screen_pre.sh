#!/bin/bash
# screen_pre.sh <tag> <mesh_dir> <volume_url> - screen pre-snapped tifxyz windings (no fit, no snap).
# Windings: $WINDINGS (default w030..w110 every 4th). Two workers: render 26 layers -> dense_native d=0
# both sides -> score_winding.py side asymmetry. Results: screen/<tag>/{scores,ranked}.tsv, thumbs/.
set -uo pipefail
TAG=$1; MESHDIR=$2; export VOL=$3
W=/workspace/vesuvius; cd "$W"
export TMPDIR=$W/tmp; mkdir -p "$TMPDIR"
OUT=$W/screen/$TAG; mkdir -p "$OUT"/{renders,maps,thumbs}
LOG=$OUT/screen.log
say() { echo "[$(date +%T)] $*" | tee -a "$LOG"; echo "$*" > "$W/SCREEN_PRE_STATUS"; }
for i in ${WINDINGS:-$(seq 30 4 110)}; do printf 'w%03d\n' "$i"; done > "$OUT/windings.txt"
say "screen $(wc -l < "$OUT/windings.txt") pre-snapped windings from $MESHDIR"

worker() {   # $1 = list file
  while read -r w; do
    [[ -f $MESHDIR/$w/x.tif ]] || { say "missing $w"; continue; }
    r=$OUT/renders/$w.zarr
    RENDER_THREADS=6 bash pod/render_winding.sh "$MESHDIR/$w" "$r" 26 || { say "render failed $w"; continue; }
    INK_WORKERS=6 venv_ink/bin/python pod/screen_ink.py "$OUT/maps" dnative 0 "$r" >> "$LOG" 2>&1 || { say "ink failed $w"; continue; }
    venv_ink/bin/python pod/score_winding.py "$r" "$OUT/maps" "$w" dnative "$OUT/thumbs" >> "$OUT/scores.tsv" 2>>"$LOG" \
      && say "scored $w: $(tail -1 "$OUT/scores.tsv" | cut -f2-3)"
  done < "$1"
}
awk 'NR % 2 == 1' "$OUT/windings.txt" > "$OUT/list_a"; awk 'NR % 2 == 0' "$OUT/windings.txt" > "$OUT/list_b"
worker "$OUT/list_a" & worker "$OUT/list_b" & wait
awk -F'\t' '{a = $3 < 0 ? -$3 : $3; print a "\t" $0}' "$OUT/scores.tsv" | sort -gr | cut -f2- > "$OUT/ranked.tsv"
say "SCREEN DONE $TAG: $(wc -l < "$OUT/scores.tsv") scored"

#!/bin/bash
# screen_local.sh <run_tag> <z0> <z1> - local (Windows, 8 GB) version of pod/screen.sh:
# snap every second winding w030..w110, render 26 layers each from S3, dense_native d=0 on both sides
# (model loaded once), score reading-minus-blind tile asymmetry. Results: screen/<tag>/{scores,ranked}.tsv, thumbs/.
set -uo pipefail
TAG=$1; Z0=$2; Z1=$3
V=${VESUVIUS_ROOT:-$HOME/vesuvius}; cd "$V"
OUT=$V/screen/$TAG; mkdir -p "$OUT"/{renders,maps,thumbs}
LOG=$OUT/screen.log
say() { echo "[$(date +%T)] $*" | tee -a "$LOG"; }
VOL=https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com/PHerc0358/volumes/20250821151737-9.362um-1.2m-113keV-masked.zarr
MESHDIR=$(ls -d spiral/runs/$TAG/*/meshes/fitted_$TAG | head -1)
for i in ${WINDINGS:-$(seq 30 2 110)}; do printf 'w%03d_spliced_%s\n' "$i" "$TAG"; done > "$OUT/windings.txt"

say "snap $(wc -l < "$OUT/windings.txt") windings (6 single-process jobs; snap_meshes.py has no __main__ guard)"
rm -f "$OUT"/snaplist_*; split -n l/6 -d --additional-suffix=.lst "$OUT/windings.txt" "$OUT/snaplist_"
for f in "$OUT"/snaplist_*.lst; do
  SURF_ZARR="$(cygpath -w "$V/spiral/PHerc0358/src/m7.zarr")" ./venv_spiral/Scripts/python.exe scripts/snap_meshes_local.py \
    "$MESHDIR" PHerc0358 "$OUT/snapped" --windings "$f" --z0 "$Z0" --z1 "$Z1" --level 0 --procs 1 \
    >> "$f.log" 2>&1 &
done
wait
say "snapped $(ls -d "$OUT"/snapped/w* 2>/dev/null | wc -l) windings"

say "render"
renders=()
while read -r w; do
  [[ -f $OUT/snapped/$w/x.tif ]] || { say "no snapped mesh $w"; continue; }
  r=$OUT/renders/$w.zarr
  [[ -f $r/0/.zarray ]] || pwsh -NoProfile -File "$(cygpath -w scripts/render_local.ps1)" "$(cygpath -w "$OUT/snapped/$w")" \
      "$(cygpath -w "$r")" "$VOL" 26 >> "$LOG" 2>&1
  [[ -f $r/.zgroup ]] || echo '{"zarr_format": 2}' > "$r/.zgroup"
  [[ -f $r/0/.zarray ]] && renders+=("$(cygpath -w "$r")") || say "render failed $w"
done < "$OUT/windings.txt"
say "rendered ${#renders[@]}"

say "ink (dense_native d=0, both sides)"
./venv314/Scripts/python.exe scripts/screen_ink_local.py "$(cygpath -w "$OUT/maps")" dnative 0 "${renders[@]}" >> "$LOG" 2>&1 \
  || say "ink step reported an error"

say "score"
: > "$OUT/scores.tsv"
while read -r w; do
  r=$OUT/renders/$w.zarr
  [[ -f $OUT/maps/${w}__dnative__d+0_reverse.tif ]] || continue
  ./venv314/Scripts/python.exe scripts/score_winding.py "$(cygpath -w "$r")" "$(cygpath -w "$OUT/maps")" "$w" dnative \
    "$(cygpath -w "$OUT/thumbs")" >> "$OUT/scores.tsv" 2>> "$LOG"
done < "$OUT/windings.txt"
awk -F'\t' '{a = $3 < 0 ? -$3 : $3; print a "\t" $0}' "$OUT/scores.tsv" | sort -gr | cut -f2- > "$OUT/ranked.tsv"
say "SCREEN DONE $TAG: $(wc -l < "$OUT/scores.tsv") scored"

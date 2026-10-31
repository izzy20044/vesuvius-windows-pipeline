#!/bin/bash
# screen_pre_local.sh <tag> <mesh_dir> <volume_url> - local screen of published pre-snapped windings (no fit, no snap):
# render 26 layers each, dense_native d=0 on both sides (model loaded once), side-asymmetry score per tile.
# Windings: $WINDINGS (default w030..w110 every other). Results: screen/<tag>/{scores,ranked}.tsv, thumbs/.
set -uo pipefail
TAG=$1; MESHDIR=$2; VOL=$3
V=${VESUVIUS_ROOT:-$HOME/vesuvius}; cd "$V"
OUT=$V/screen/$TAG; mkdir -p "$OUT"/{renders,maps,thumbs}
LOG=$OUT/screen.log
say() { echo "[$(date +%T)] $*" | tee -a "$LOG"; }
for i in ${WINDINGS:-$(seq 30 2 110)}; do printf 'w%03d\n' "$i"; done > "$OUT/windings.txt"
say "render $(wc -l < "$OUT/windings.txt") windings from $MESHDIR"
renders=()
while read -r w; do
  [[ -f $MESHDIR/$w/x.tif ]] || { say "missing $w"; continue; }
  r=$OUT/renders/$w.zarr
  [[ -f $r/0/.zarray ]] || pwsh -NoProfile -File "$(cygpath -w scripts/render_local.ps1)" "$(cygpath -w "$MESHDIR/$w")" \
      "$(cygpath -w "$r")" "$VOL" 26 >> "$LOG" 2>&1
  [[ -f $r/.zgroup ]] || echo '{"zarr_format": 2}' > "$r/.zgroup"
  [[ -f $r/0/.zarray ]] && renders+=("$(cygpath -w "$r")") || say "render failed $w"
done < "$OUT/windings.txt"
say "rendered ${#renders[@]}; ink (dense_native d=0, both sides)"
./venv314/Scripts/python.exe scripts/screen_ink_local.py "$(cygpath -w "$OUT/maps")" dnative 0 "${renders[@]}" >> "$LOG" 2>&1 \
  || say "ink step reported an error"
say "score"
: > "$OUT/scores.tsv"
while read -r w; do
  [[ -f $OUT/maps/${w}__dnative__d+0_reverse.tif ]] || continue
  ./venv314/Scripts/python.exe scripts/score_winding.py "$(cygpath -w "$OUT/renders/$w.zarr")" "$(cygpath -w "$OUT/maps")" \
    "$w" dnative "$(cygpath -w "$OUT/thumbs")" >> "$OUT/scores.tsv" 2>> "$LOG"
done < "$OUT/windings.txt"
awk -F'\t' '{a = $3 < 0 ? -$3 : $3; print a "\t" $0}' "$OUT/scores.tsv" | sort -gr | cut -f2- > "$OUT/ranked.tsv"
say "SCREEN DONE $TAG: $(wc -l < "$OUT/scores.tsv") scored"
# free disk: renders are ~0.2 GB each and can be regenerated from the mesh
rm -rf "$OUT/renders"

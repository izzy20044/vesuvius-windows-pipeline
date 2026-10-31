#!/bin/bash
# pipeline.sh - unattended PHerc0358 run: wait for setup -> ACW/CW 2k-step test -> 30k fit in the better sense.
# Progress: /workspace/vesuvius/pipeline.log (one line per stage), STATUS file holds the current stage.
set -uo pipefail
W=/workspace/vesuvius; cd "$W"
L=$W/pipeline.log
say() { echo "[$(date +%T)] $*" | tee -a "$L"; echo "$*" > "$W/STATUS"; }

say "waiting for setup"
until grep -q "SETUP COMPLETE" setup.log 2>/dev/null; do
  if ! pgrep -f setup_pod.sh >/dev/null; then say "SETUP FAILED - see setup.log"; exit 1; fi
  sleep 30
done
say "setup complete"

score() {  # satisfied track fraction of a finished run
  local f; f=$(find "$W/spiral/runs/$1" -name 'satisfaction_metrics*.json' 2>/dev/null | head -1)
  [[ -n $f ]] && "$W/venv_spiral/bin/python" -c "import json,sys; print(json.load(open(sys.argv[1]))['summary']['satisfied_tracks_fraction'])" "$f" || echo 0
}

DEADLINE=$(date -d "${FIT_DEADLINE:-2026-10-31 02:20 UTC}" +%s)   # main fit must end by then (budget)
for s in ACW CW; do
  say "test fit $s 2000 steps"
  t0=$(date +%s)
  bash pod/run_fit.sh "$s" 2000 8700 10200 "test-$s" >> "$L" 2>&1 || say "test fit $s FAILED (rc=$?)"
  dur=$(( $(date +%s) - t0 )); echo "$dur" > "$W/test_dur_$s"; say "test fit $s took ${dur}s"
done
acw=$(score test-ACW); cw=$(score test-CW)
best=$("$W/venv_spiral/bin/python" -c "print('ACW' if $acw >= $cw else 'CW')")
say "test result: ACW $acw  CW $cw  -> using $best"

dur=$(cat "$W/test_dur_$best"); left=$(( DEADLINE - $(date +%s) - 600 ))
steps=$(( left * 2000 / (dur > 0 ? dur : 1) )); (( steps > 30000 )) && steps=30000; (( steps < 2000 )) && steps=2000
say "main fit $best $steps steps (test ${dur}s/2000 steps, ${left}s to deadline)"
bash pod/run_fit.sh "$best" "$steps" 8700 10200 "main-$best" >> "$L" 2>&1 && say "MAIN FIT DONE ($best) score $(score main-$best)" \
  || say "MAIN FIT FAILED - see spiral/runs/main-$best/fit.log"

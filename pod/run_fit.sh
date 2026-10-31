#!/bin/bash
# run_fit.sh (pod) - PHerc0358 spiral fit with Nieuwlaar's PHerc0343 recipe (villa 0fb38c45 + shell-optional patch).
#
#   run_fit.sh <ACW|CW> <steps> <z_begin> <z_end> <run_tag>
#
# Recipe differences from PHerc0343: scroll, z band, sense; everything else as in nieuwlaar/mesh/README.md.
set -euo pipefail
SENSE=$1; STEPS=$2; Z0=$3; Z1=$4; TAG=$5
W=${W:-/workspace/vesuvius}
DS=$W/spiral/PHerc0358
SPEC=$DS/spiral-scroll.json
[[ $SENSE == CW ]] && SPEC=$DS/spiral-scroll-cw.json
export FIT_SPIRAL_OUT_DIR="$W/spiral/runs/$TAG"
export FIT_SPIRAL_RUN_TAG="$TAG"
export FIT_SPIRAL_CACHE_DIR="$W/spiral/cache"
export WANDB_MODE=disabled
read -r q p < /sys/fs/cgroup/cpu.max 2>/dev/null || q=max
export OMP_NUM_THREADS=$([[ $q != max ]] && echo $(( q / p )) || nproc)
export FIT_SPIRAL_CONFIG_OVERRIDES="{\"z_begin\": $Z0, \"z_end\": $Z1, \"input_disable_patches\": true, \"loss_weight_shell_outer\": 0, \"loss_weight_shell_patch_radius\": 0, \"dense_spacing_mode\": \"phase\", \"optimizer_num_training_steps\": $STEPS}"
mkdir -p "$FIT_SPIRAL_OUT_DIR"
cd "$W/villa/volume-cartographer/scripts/spiral"
echo "[$(date +%T)] fit $TAG sense=$SENSE steps=$STEPS z=$Z0..$Z1"
rc=0
"$W/venv_spiral/bin/python" fit_spiral.py --dataset "$DS" --scroll-spec "$SPEC" \
  > "$FIT_SPIRAL_OUT_DIR/fit.log" 2>&1 || rc=$?
echo "[$(date +%T)] exit=$rc ; outputs:"; ls "$FIT_SPIRAL_OUT_DIR"
exit $rc

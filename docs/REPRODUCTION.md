# Reproducing the PHerc. 343 First Letters result

Goal: an end-to-end correctness check of render + ink + ensemble on independent hardware, before
spending GPU time on an unread scroll.

## Inputs

* Mesh: `outputs/concat_w047-w048_R5B2_z9500-11000.tifxyz` from
  [Nieuwlaar/pherc343-first-letters](https://github.com/Nieuwlaar/pherc343-first-letters).
* Volume: `PHerc0343/volumes/20250521140437-8.640um-1.2m-116keV-masked.zarr` (open-data bucket, streamed).
* Models (sha256 verified against Nieuwlaar's `ink/models.tsv`): ink_9um seed42 and seed43
  `step-075000.pth`, `hecate_9.6um.pth`, dense_native rebuilt from its safetensors + config.

## Steps

```powershell
# 1. render 66 layers (layer k samples the CT at k - 32.5 voxels along the normal)
vc_render_tifxyz.exe --volume https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com/PHerc0343/volumes/20250521140437-8.640um-1.2m-116keV-masked.zarr `
  --group-idx 0 --scale 1 --segmentation <concat mesh> --num-slices 66 --slice-step 1 --cache-gb 4 `
  --zarr-output concat_66.zarr          # stop the process once all levels are written (see WINDOWS.md)

# 2. level-0-only view, as run_ink.sh does on Linux
mkdir concat_66_L0only.zarr; '{"zarr_format": 2}' > concat_66_L0only.zarr\.zgroup
New-Item -ItemType Junction -Path concat_66_L0only.zarr\0 -Target concat_66.zarr\0

# 3. ink maps at d = +1 under run_ink.sh naming (villa window s = d + 25; Hecate zc = 32.5 + d)
python scripts\nieuwlaar_maps.py concat_66_L0only.zarr maps --depths 1..1

# 4. Nieuwlaar's ensemble, unchanged
python nieuwlaar\ink\scripts\ensemble_maps.py --surface concat_66_L0only.zarr --maps maps --out ens `
  --stat-depths 1 --write-depths 1

# 5. score against the submitted image
python scripts\compare_submission.py nieuwlaar\outputs\concat_w047-w048_R5B2_z9500-11000.png `
  ens\concat_66_L0only__ensemble__d+01.png ens\concat_66_L0only__ensemble_blind__d+01.png overlay.png
```

## Scoring method

`compare_submission.py` recovers the ink layer of the submission PNG as yellowness
`(R+G)/2 - B` (zero on the grey CT), locates our ensemble inside it by normalised cross-correlation
(coarse at 1/4 scale, then full-scale refinement), and reports Pearson r and AUC of our map against
the submitted ink mask (yellowness > 40). The blind side is scored at the same location as a control.

## Result

Template NCC 0.831; reading-side ensemble r = +0.859, AUC = 0.990; blind side r = +0.194,
AUC = 0.669. Statistics were pooled over one depth (d = +1) instead of Nieuwlaar's 31, which changes
the contrast stretch but not the ink locations.

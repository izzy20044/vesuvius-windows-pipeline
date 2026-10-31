# Evaluation pitfalls (each produced a wrong conclusion before it was caught)

1. **Downsampled previews fake letters.** A 4100x2840 published ink map viewed at screen size looked
   like crisp Greek text; at native resolution the same regions are diffuse blobs. Judge legibility
   only at native resolution, and score against the full-precision `.tif`, not the `-ds8.jpg`.

2. **Cross-resolution crops must be registered.** Comparing a 9.362 um render crop to a 2.4 um
   reference crop by assumed coordinates scored 0/7 depths above chance and suggested survey scans
   carry no ink. The low-res crop covered ~2x the reference footprint. After registering the two
   renders CT-to-CT (`scripts/register_rescore.py`, NCC 0.83/0.89) and cropping the reference to the
   measured footprint, the same maps scored 6/7 above chance.

3. **Brightness-ranked "find the text" searches find damage.** Picking windows by ink fraction selects
   saturated blobs. Pick by letter-sized connected components without giant components, or by eye on a
   gridded overview, then verify at native resolution.

4. **Threshold-based IoU can be gamed by sparse maps.** A near-black prediction scored a top IoU. Use a
   threshold-free AUC, and always look at an overlay.

5. **Depth orientation and placement dominate.** The same model and segment moved from AUC 0.47 to 0.65
   by depth window alone, and the reversed orientation sits below chance. Sweep depth and run both
   orientations, with a known-ink and a known-blank control.

6. **Over drifting mesh, ink models light up both sides.** Score reading-minus-blind asymmetry, not raw
   ink probability.

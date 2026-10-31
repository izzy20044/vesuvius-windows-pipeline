"""Rebind a published track-crossing cache (.dbm.crossings.npz) to a local copy of its tracks DBM.

The cache stores the DBM signature (name, size, mtime_ns). A byte-identical download has a new mtime,
and NTFS cannot hold nanosecond mtimes (100 ns ticks), so restoring the original timestamp is not
possible on Windows. This rewrites only metadata.db_signature, after checking that name and size are
unchanged; every array is copied as stored. The original is kept as <cache>.orig.

Usage: python rebind_crossing_cache.py <tracks.dbm>
"""
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

import numpy as np

sys.path.insert(0, os.environ.get("VILLA_SPIRAL", str(Path(os.environ.get("VESUVIUS_ROOT", Path.home() / "vesuvius")) / "villa" / "volume-cartographer" / "scripts" / "spiral")))
import tracks  # noqa: E402


def main(dbm):
    cache = dbm + ".crossings.npz"
    orig = cache + ".orig"
    if not os.path.exists(orig):
        shutil.copy2(cache, orig)
    with zipfile.ZipFile(orig) as z:
        compressed = any(i.compress_type != zipfile.ZIP_STORED for i in z.infolist())
    with np.load(orig, allow_pickle=False) as stored:
        meta = json.loads(str(stored["metadata"].item()))
        arrays = {k: stored[k] for k in stored.files if k != "metadata"}
    old = meta["db_signature"]
    new = [list(s) for s in tracks._tracks_db_signature(dbm)]
    if [s[:2] for s in old] != [s[:2] for s in new]:
        sys.exit(f"refusing: name/size differ, old={old} new={new}")
    meta["db_signature"] = new
    meta["rebound_from_signature"] = old
    save = np.savez_compressed if compressed else np.savez
    tmp = cache + ".tmp.npz"
    save(tmp, metadata=np.array(json.dumps(meta)), **arrays)
    os.replace(tmp, cache)
    print(f"rebound {os.path.basename(cache)}: mtime {old[0][2]} -> {new[0][2]} "
          f"({len(arrays)} arrays, compressed={compressed})")
    print("accepted by fitter:", tracks.load_track_crossing_cache(dbm) is not None)


if __name__ == "__main__":
    main(sys.argv[1])

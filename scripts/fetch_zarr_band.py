"""Copy one group of a public OME-Zarr (open-data S3) for a z band to a local store.

Lists the chunk keys that exist per z chunk layer (sparse stores skip empty chunks),
then downloads them with a thread pool. Copies .zgroup/.zattrs and the group .zarray.

Usage: python fetch_zarr_band.py <s3 key prefix of .zarr> <group> <z0> <z1> <local .zarr>
       z0/z1 are in that group's own voxel units.
"""
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

BASE = "https://vesuvius-challenge-open-data.s3.amazonaws.com"
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


def get(url: str, tries: int = 5) -> bytes:
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except Exception as exc:
            last = exc
    raise RuntimeError(f"GET failed after {tries} tries: {url}") from last


def list_keys(prefix):
    keys, token = [], None
    while True:
        url = f"{BASE}/?list-type=2&max-keys=1000&prefix={quote(prefix)}"
        if token:
            url += f"&continuation-token={quote(token)}"
        root = ET.fromstring(get(url))
        keys += [c.findtext(f"{NS}Key") or "" for c in root.findall(f"{NS}Contents")]
        if root.findtext(f"{NS}IsTruncated") != "true":
            return keys
        token = root.findtext(f"{NS}NextContinuationToken")


def main(prefix, group, z0, z1, dst):
    z0, z1 = int(z0), int(z1)
    for meta in (".zgroup", ".zattrs"):
        try:
            data = get(f"{BASE}/{prefix}/{meta}")
            os.makedirs(dst, exist_ok=True)
            open(os.path.join(dst, meta), "wb").write(data)
        except Exception:
            pass
    zarray = get(f"{BASE}/{prefix}/{group}/.zarray")
    os.makedirs(os.path.join(dst, group), exist_ok=True)
    open(os.path.join(dst, group, ".zarray"), "wb").write(zarray)
    meta = json.loads(zarray)
    cz = meta["chunks"][0]
    sep = meta.get("dimension_separator", ".")
    layers = range(z0 // cz, (z1 - 1) // cz + 1)

    keys = []
    for zc in layers:
        keys += list_keys(f"{prefix}/{group}/{zc}{sep}")
    print(f"{prefix.split('/')[-1]}/{group}: z chunk layers {layers.start}..{layers.stop - 1}, "
          f"{len(keys)} chunks", flush=True)

    def fetch(key):
        rel = key[len(prefix) + 1:]
        path = os.path.join(dst, *rel.split("/"))
        if os.path.exists(path):
            return 0
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = get(f"{BASE}/{quote(key)}")
        open(path + ".part", "wb").write(data)
        os.replace(path + ".part", path)
        return len(data)

    with ThreadPoolExecutor(32) as pool:
        total = sum(pool.map(fetch, keys))
    print(f"  done, {total / 1e6:.1f} MB", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:6])

"""Read-only integrity snapshot of the offline archive.

Records file count, total bytes, and the newest mtime for each protected
directory plus the SQLite database. Run before and after the audit to prove
that no cached HTML/assets/database files were modified.

Usage:
    python -m quran_offline.audit_tools.snapshot_manifest [label]
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TARGETS = {
    "cache/index.json": ROOT / "cache" / "index.json",
    "cache/assets.json": ROOT / "cache" / "assets.json",
    "cache/pages": ROOT / "cache" / "pages",
    "cache/assets": ROOT / "cache" / "assets",
    "data/quran_corpus.sqlite3": ROOT / "data" / "quran_corpus.sqlite3",
    "data/quranic-corpus-morphology-0.4.txt": ROOT / "data" / "quranic-corpus-morphology-0.4.txt",
}


def dir_stats(p: Path) -> dict:
    count = 0
    total = 0
    newest = 0.0
    for f in p.glob("*"):
        if f.is_file():
            st = f.stat()
            count += 1
            total += st.st_size
            newest = max(newest, st.st_mtime)
    return {"kind": "dir", "files": count, "bytes": total, "newest_mtime": newest}


def file_stats(p: Path, hash_small: bool = False) -> dict:
    st = p.stat()
    out = {"kind": "file", "bytes": st.st_size, "mtime": st.st_mtime}
    if hash_small and st.st_size <= 64 * 1024 * 1024:
        out["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def build() -> dict:
    snap = {"taken_at": time.time(), "root": str(ROOT), "targets": {}}
    for name, p in TARGETS.items():
        if not p.exists():
            snap["targets"][name] = {"kind": "missing"}
        elif p.is_dir():
            snap["targets"][name] = dir_stats(p)
        else:
            # hash the json index files (small, content-meaningful)
            snap["targets"][name] = file_stats(p, hash_small=name.endswith(".json"))
    return snap


def main(argv: list[str]) -> int:
    label = argv[0] if argv else "snapshot"
    out_dir = Path(__file__).resolve().parent / "snapshots"
    out_dir.mkdir(exist_ok=True)
    snap = build()
    out_path = out_dir / f"{label}.json"
    out_path.write_text(json.dumps(snap, indent=2), "utf-8")
    print(json.dumps(snap, indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

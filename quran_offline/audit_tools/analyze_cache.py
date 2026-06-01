"""Read-only completeness analysis of the offline cache.

Categorises every mapped HTML page and asset by Corpus page type, counts
files on disk, detects orphans / missing / zero-byte files, and reports
SQLite coverage. Pure read-only; writes nothing to cache/ or data/.

Usage:
    python -m quran_offline.audit_tools.analyze_cache
"""
from __future__ import annotations

import collections
import json
import sqlite3
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_INDEX = ROOT / "cache" / "index.json"
ASSET_INDEX = ROOT / "cache" / "assets.json"
CACHE_PAGES = ROOT / "cache" / "pages"
CACHE_ASSETS = ROOT / "cache" / "assets"
DB_PATH = ROOT / "data" / "quran_corpus.sqlite3"


def load(path: Path) -> dict:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def page_type(url: str) -> str:
    p = urllib.parse.urlparse(url)
    path = p.path.rsplit("/", 1)[-1] or "(root)"
    if p.path.startswith("/documentation"):
        return "documentation/" + path
    return path


def analyze_index(name: str, index: dict, folder: Path, ext: str | None):
    print(f"\n## {name}")
    print(f"mapped entries: {len(index):,}")
    files = [f for f in folder.glob("*") if f.is_file()]
    print(f"files on disk:  {len(files):,}")
    mapped_names = set()
    missing = 0
    zero = 0
    for url, rel in index.items():
        fp = ROOT / rel
        mapped_names.add(fp.name.lower())
        if not fp.exists():
            missing += 1
        elif fp.stat().st_size == 0:
            zero += 1
    orphans = [f for f in files if f.name.lower() not in mapped_names]
    print(f"missing mapped files: {missing:,}")
    print(f"zero-byte mapped files: {zero:,}")
    print(f"orphan files on disk: {len(orphans):,}")
    return orphans


def main() -> int:
    index = load(CACHE_INDEX)
    assets = load(ASSET_INDEX)

    page_orphans = analyze_index("cache/index.json (HTML pages)", index, CACHE_PAGES, ".html")
    analyze_index("cache/assets.json (assets)", assets, CACHE_ASSETS, None)

    print("\n## HTML page-type breakdown (mapped)")
    types = collections.Counter(page_type(u) for u in index)
    for t, n in types.most_common():
        print(f"  {t:40s} {n:>8,}")

    print("\n## Asset extension breakdown (mapped, by URL path suffix)")
    aexts = collections.Counter(
        (Path(urllib.parse.urlparse(u).path).suffix.lower() or "(none)") for u in assets
    )
    for e, n in aexts.most_common():
        print(f"  {e:12s} {n:>8,}")

    print("\n## Asset stored-file extension breakdown (on disk via mapping)")
    sexts = collections.Counter(Path(rel).suffix.lower() for rel in assets.values())
    for e, n in sexts.most_common():
        print(f"  {e:12s} {n:>8,}")

    # Orphan page details
    print("\n## Orphan HTML files (not referenced by index.json)")
    print(f"  count: {len(page_orphans):,}")
    for f in sorted(page_orphans)[:40]:
        print(f"    {f.name}  ({f.stat().st_size:,} bytes)")

    # SQLite coverage
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        c = conn.execute
        print("\n## SQLite counts")
        print(f"  surahs:   {c('SELECT COUNT(*) FROM surahs').fetchone()[0]:,}")
        print(f"  verses:   {c('SELECT COUNT(*) FROM (SELECT DISTINCT chapter,verse FROM words)').fetchone()[0]:,}")
        print(f"  words:    {c('SELECT COUNT(*) FROM words').fetchone()[0]:,}")
        print(f"  segments: {c('SELECT COUNT(*) FROM segments').fetchone()[0]:,}")
        print(f"  roots:    {c(chr(34)).fetchone()[0] if False else c('SELECT COUNT(DISTINCT root_buck) FROM segments WHERE root_buck IS NOT NULL AND root_buck != \"\"').fetchone()[0]:,}")
        print(f"  lemmas:   {c('SELECT COUNT(DISTINCT lemma_buck) FROM segments WHERE lemma_buck IS NOT NULL AND lemma_buck != \"\"').fetchone()[0]:,}")
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Fetch ONLY the 5 missing wordmorphology.jsp pages and integrate them into
the existing content-addressed cache, using the exact convention of
cache_corpus_pages.py (key = normalised URL, file = sha256(key)+'.html').

Safety:
  * fetch + validate all 5 in memory FIRST; write nothing unless ALL pass
  * respectful 2.0s throttle between live requests
  * atomic index.json write (tmp + replace), same format as the builder
  * reports referenced assets that are NOT already cached (does not fetch them
    unless --fetch-missing-assets is passed)
  * never touches unrelated pages/assets/db

Usage:
    python -m quran_offline.audit_tools.fetch_missing_morphology [--commit] [--delay 2.0]
Without --commit it is a dry run (fetch + validate + report only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = ROOT / "cache" / "pages"
ASSET_DIR = ROOT / "cache" / "assets"
INDEX_PATH = ROOT / "cache" / "index.json"
ASSET_INDEX_PATH = ROOT / "cache" / "assets.json"
BASE = "https://corpus.quran.com/"
UA = "QuranCorpusOfflineBuilder/1.0 (+local personal offline cache)"

TARGETS = [(6, 119, 4), (6, 122, 7), (6, 125, 15), (6, 126, 7), (7, 157, 25)]
ASSET_EXTS = {".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico"}


def normalise_url(url: str) -> str:
    url = urllib.parse.urljoin(BASE, url)
    p = urllib.parse.urlparse(url)
    if p.scheme == "http" and p.netloc == "corpus.quran.com":
        p = p._replace(scheme="https")
    q = urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(p.query, keep_blank_values=True)))
    return urllib.parse.urlunparse((p.scheme, p.netloc, p.path or "/", "", q, ""))


def key_to_relpath(url: str) -> str:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"cache/pages/{h}.html"


def target_url(c, v, w) -> str:
    loc = urllib.parse.quote(f"({c}:{v}:{w})", safe="")
    return f"https://corpus.quran.com/wordmorphology.jsp?location={loc}"


def fetch(url: str, timeout: int = 60) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def validate(c, v, w, status: int, text: str) -> list[str]:
    """Return a list of problems; empty list == valid."""
    probs = []
    if status != 200:
        probs.append(f"HTTP status {status}")
    if "The Quranic Arabic Corpus" not in text:
        probs.append("missing Corpus title marker")
    if "<title>" not in text.lower():
        probs.append("no <title> tag")
    # The page should reference this verse/word location somewhere.
    if f"({c}:{v}:{w})" not in text and f"Word {w}" not in text and f"verse ({c}:{v})" not in text:
        probs.append(f"location ({c}:{v}:{w}) markers not found in body")
    if len(text) < 2000:
        probs.append(f"suspiciously small body ({len(text)} bytes)")
    if "wordmorphology" not in text.lower() and "morphological segment" not in text.lower():
        probs.append("no morphology content markers")
    return probs


def extract_assets(text: str, base_url: str) -> set[str]:
    assets = set()
    for m in re.finditer(r"href=[\"']([^\"']+)[\"']", text, re.I):
        href = m.group(1)
        if href.startswith(("#", "mailto:", "javascript:")):
            continue
        full = normalise_url(urllib.parse.urljoin(base_url, href))
        if urllib.parse.urlparse(full).netloc == "corpus.quran.com":
            if Path(urllib.parse.urlparse(full).path).suffix.lower() in ASSET_EXTS:
                assets.add(full)
    for m in re.finditer(r"src=[\"']([^\"']+)[\"']", text, re.I):
        full = normalise_url(urllib.parse.urljoin(base_url, m.group(1)))
        if urllib.parse.urlparse(full).netloc == "corpus.quran.com":
            assets.add(full)
    return assets


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="Actually write files + index (default: dry run).")
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--fetch-missing-assets", action="store_true")
    args = ap.parse_args(argv)
    delay = max(1.0, args.delay)

    index = json.loads(INDEX_PATH.read_text("utf-8"))
    asset_index = json.loads(ASSET_INDEX_PATH.read_text("utf-8"))

    # Phase A: fetch + validate ALL before writing anything.
    fetched = []
    for i, (c, v, w) in enumerate(TARGETS):
        url = target_url(c, v, w)
        key = normalise_url(url)
        rel = key_to_relpath(key)
        if key in index:
            print(f"ABORT: {key} already in index — refusing to overwrite.")
            return 2
        if (ROOT / rel).exists():
            print(f"ABORT: target file already exists: {rel}")
            return 2
        if i:
            time.sleep(delay)
        print(f"[fetch {i+1}/5] {url}")
        try:
            status, data = fetch(url)
        except Exception as exc:
            print(f"ABORT: fetch failed for {url}: {type(exc).__name__}: {exc}")
            return 1
        text = data.decode("utf-8", errors="replace")
        probs = validate(c, v, w, status, text)
        title = re.search(r"(?is)<title>(.*?)</title>", text)
        print(f"    status={status} bytes={len(data)} title={title.group(1).strip() if title else '?'}")
        if probs:
            print(f"ABORT: validation failed for ({c}:{v}:{w}): {probs}")
            return 1
        assets = extract_assets(text, key)
        missing_assets = sorted(a for a in assets if a not in asset_index)
        fetched.append({"loc": (c, v, w), "url": url, "key": key, "rel": rel,
                        "text": text, "bytes": len(data), "title": title.group(1).strip() if title else "",
                        "n_assets": len(assets), "missing_assets": missing_assets})

    print("\nAll 5 fetched and validated OK.")
    all_missing = sorted({a for f in fetched for a in f["missing_assets"]})
    print(f"Referenced assets not already cached: {len(all_missing)}")
    for a in all_missing:
        print(f"  MISSING ASSET: {a}")

    if not args.commit:
        print("\nDRY RUN — nothing written. Re-run with --commit to integrate.")
        for f in fetched:
            print(f"  would write {f['rel']}  ({f['bytes']} bytes)  key={f['key']}")
        return 0

    # Phase B: optionally fetch missing assets
    if all_missing and args.fetch_missing_assets:
        for a in all_missing:
            ext = Path(urllib.parse.urlparse(a).path).suffix.lower() or ".bin"
            ah = hashlib.sha256(a.encode("utf-8")).hexdigest()
            arel = f"cache/assets/{ah}{ext}"
            time.sleep(delay)
            print(f"[asset] {a}")
            try:
                st, ad = fetch(a, timeout=45)
                (ROOT / arel).write_bytes(ad)
                asset_index[a] = arel
            except Exception as exc:
                print(f"  asset error (continuing): {exc}")
    elif all_missing:
        print("\nNOTE: missing assets present but --fetch-missing-assets not set; leaving assets untouched.")

    # Phase C: write page files, then atomically write index.json
    for f in fetched:
        (ROOT / f["rel"]).write_text(f["text"], "utf-8")
        index[f["key"]] = f["rel"]
        print(f"wrote {f['rel']}")

    tmp = INDEX_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), "utf-8")
    tmp.replace(INDEX_PATH)
    print(f"\nindex.json updated: now {len(index):,} entries")

    if all_missing and args.fetch_missing_assets:
        atmp = ASSET_INDEX_PATH.with_suffix(".tmp")
        atmp.write_text(json.dumps(asset_index, ensure_ascii=False, indent=2, sort_keys=True), "utf-8")
        atmp.replace(ASSET_INDEX_PATH)
        print(f"assets.json updated: now {len(asset_index):,} entries")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

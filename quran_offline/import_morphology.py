from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path
from typing import Iterable

from .buckwalter import buck_to_ar, strip_buck_diacritics, strip_ar_diacritics
from .surah_data import SURAHS

DEFAULT_URLS = [
    # Mirrors of the public v0.4 morphology file. The official Corpus site requires an email form.
    "https://raw.githubusercontent.com/cltk/arabic_morphology_quranic-corpus/master/quranic-corpus-morphology-0.4.txt",
    "https://raw.githubusercontent.com/bnjasim/quranic-corpus/master/quranic-corpus-morphology-0.4.txt",
]

LOC_RE = re.compile(r"^\((\d+):(\d+):(\d+):(\d+)\)$")

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS surahs(
  id INTEGER PRIMARY KEY,
  name_translit TEXT NOT NULL,
  name_en TEXT NOT NULL,
  ayah_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS segments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chapter INTEGER NOT NULL,
  verse INTEGER NOT NULL,
  word INTEGER NOT NULL,
  segment INTEGER NOT NULL,
  form_buck TEXT NOT NULL,
  form_ar TEXT NOT NULL,
  form_buck_plain TEXT NOT NULL,
  form_ar_plain TEXT NOT NULL,
  tag TEXT NOT NULL,
  segment_type TEXT,
  pos TEXT,
  lemma_buck TEXT,
  lemma_ar TEXT,
  lemma_buck_plain TEXT,
  lemma_ar_plain TEXT,
  root_buck TEXT,
  root_ar TEXT,
  root_buck_plain TEXT,
  root_ar_plain TEXT,
  features TEXT NOT NULL,
  feature_flags TEXT NOT NULL,
  UNIQUE(chapter, verse, word, segment)
);
CREATE TABLE IF NOT EXISTS words(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chapter INTEGER NOT NULL,
  verse INTEGER NOT NULL,
  word INTEGER NOT NULL,
  form_buck TEXT NOT NULL,
  form_ar TEXT NOT NULL,
  form_buck_plain TEXT NOT NULL,
  form_ar_plain TEXT NOT NULL,
  tag_chain TEXT NOT NULL,
  primary_tag TEXT,
  lemma_buck TEXT,
  lemma_ar TEXT,
  root_buck TEXT,
  root_ar TEXT,
  features TEXT,
  UNIQUE(chapter, verse, word)
);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_segments_loc ON segments(chapter, verse, word, segment);
CREATE INDEX IF NOT EXISTS idx_segments_tag ON segments(tag);
CREATE INDEX IF NOT EXISTS idx_segments_root ON segments(root_buck_plain, root_ar_plain);
CREATE INDEX IF NOT EXISTS idx_segments_lemma ON segments(lemma_buck_plain, lemma_ar_plain);
CREATE INDEX IF NOT EXISTS idx_words_loc ON words(chapter, verse, word);
CREATE INDEX IF NOT EXISTS idx_words_root ON words(root_buck, root_ar);
CREATE INDEX IF NOT EXISTS idx_words_lemma ON words(lemma_buck, lemma_ar);
"""


def download_first(urls: list[str], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for url in urls:
        try:
            print(f"Downloading morphology file from {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "QuranCorpusOfflineBuilder/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r, out_path.open("wb") as f:
                while True:
                    chunk = r.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            print(f"Saved {out_path} ({out_path.stat().st_size:,} bytes)")
            return out_path
        except Exception as exc:  # pragma: no cover - network variability
            errors.append(f"{url}: {exc}")
            print(f"Failed: {exc}")
    raise RuntimeError("Could not download morphology file. Errors:\n" + "\n".join(errors))


def parse_features(features: str) -> dict[str, str | bool]:
    out: dict[str, str | bool] = {}
    parts = [p for p in features.split("|") if p]
    if parts:
        out["segment_type"] = parts[0]
    for part in parts:
        if ":" in part:
            key, value = part.split(":", 1)
            out[key.upper()] = value
        else:
            out[part.upper()] = True
    return out


def iter_rows(path: Path) -> Iterable[tuple[int, int, int, int, str, str, str]]:
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        header_seen = False
        for line_no, line in enumerate(f, start=1):
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            if line.startswith("LOCATION"):
                header_seen = True
                continue
            if not header_seen:
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                # Some mirrors may have spaces; fall back to maxsplit.
                parts = re.split(r"\s+", line, maxsplit=3)
            if len(parts) != 4:
                raise ValueError(f"Bad morphology row at line {line_no}: {line!r}")
            loc, form, tag, features = parts
            m = LOC_RE.match(loc.strip())
            if not m:
                raise ValueError(f"Bad location at line {line_no}: {loc!r}")
            chapter, verse, word, segment = map(int, m.groups())
            yield chapter, verse, word, segment, form.strip(), tag.strip(), features.strip()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM surahs")
    conn.executemany(
        "INSERT INTO surahs(id, name_translit, name_en, ayah_count) VALUES (?, ?, ?, ?)",
        [(i, translit, en, count) for i, translit, en, count in SURAHS],
    )
    conn.execute("DELETE FROM segments")
    conn.execute("DELETE FROM words")
    conn.execute("DELETE FROM meta")


def import_file(src: Path, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        segment_rows = []
        count = 0
        for chapter, verse, word, segment, form, tag, features in iter_rows(src):
            info = parse_features(features)
            segment_type = str(info.get("segment_type") or "")
            pos = str(info.get("POS") or tag or "")
            lemma_buck = str(info.get("LEM") or "") or None
            root_buck = str(info.get("ROOT") or "") or None
            form_ar = buck_to_ar(form)
            lemma_ar = buck_to_ar(lemma_buck) if lemma_buck else None
            root_ar = buck_to_ar(root_buck) if root_buck else None
            flags = "|".join(sorted(k for k, v in info.items() if v is True))
            segment_rows.append((
                chapter, verse, word, segment,
                form, form_ar, strip_buck_diacritics(form), strip_ar_diacritics(form_ar),
                tag, segment_type, pos,
                lemma_buck, lemma_ar,
                strip_buck_diacritics(lemma_buck), strip_ar_diacritics(lemma_ar),
                root_buck, root_ar,
                strip_buck_diacritics(root_buck), strip_ar_diacritics(root_ar),
                features, flags,
            ))
            count += 1
            if len(segment_rows) >= 5000:
                conn.executemany("""
                    INSERT INTO segments(
                      chapter, verse, word, segment, form_buck, form_ar, form_buck_plain, form_ar_plain,
                      tag, segment_type, pos, lemma_buck, lemma_ar, lemma_buck_plain, lemma_ar_plain,
                      root_buck, root_ar, root_buck_plain, root_ar_plain, features, feature_flags
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, segment_rows)
                segment_rows.clear()
        if segment_rows:
            conn.executemany("""
                INSERT INTO segments(
                  chapter, verse, word, segment, form_buck, form_ar, form_buck_plain, form_ar_plain,
                  tag, segment_type, pos, lemma_buck, lemma_ar, lemma_buck_plain, lemma_ar_plain,
                  root_buck, root_ar, root_buck_plain, root_ar_plain, features, feature_flags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, segment_rows)

        # Build word-level table by grouping segments.
        cursor = conn.execute("""
            SELECT chapter, verse, word, form_buck, form_ar, form_buck_plain, form_ar_plain, tag, lemma_buck, lemma_ar, root_buck, root_ar, features
            FROM segments ORDER BY chapter, verse, word, segment
        """)
        current_key = None
        bundle = []
        word_rows = []

        def flush() -> None:
            if not bundle:
                return
            chapter, verse, word = current_key
            form_buck = "".join(row[0] for row in bundle).replace("+", "")
            form_ar = "".join(row[1] for row in bundle).replace("+", "")
            form_buck_plain = strip_buck_diacritics(form_buck)
            form_ar_plain = strip_ar_diacritics(form_ar)
            tags = [row[4] for row in bundle if row[4] and row[4] != "DET"]
            tag_chain = "-".join(row[4] for row in bundle if row[4])
            primary_tag = tags[0] if tags else (bundle[0][4] if bundle else None)
            lemmas = [row[5] for row in bundle if row[5]]
            lemmas_ar = [row[6] for row in bundle if row[6]]
            roots = [row[7] for row in bundle if row[7]]
            roots_ar = [row[8] for row in bundle if row[8]]
            features_joined = " || ".join(row[9] for row in bundle)
            word_rows.append((chapter, verse, word, form_buck, form_ar, form_buck_plain, form_ar_plain,
                              tag_chain, primary_tag, lemmas[-1] if lemmas else None, lemmas_ar[-1] if lemmas_ar else None,
                              roots[-1] if roots else None, roots_ar[-1] if roots_ar else None, features_joined))

        for chapter, verse, word, fb, fa, fbp, fap, tag, lem_b, lem_a, root_b, root_a, features in cursor:
            key = (chapter, verse, word)
            if current_key is None:
                current_key = key
            if key != current_key:
                flush()
                bundle.clear()
                current_key = key
            bundle.append((fb, fa, fbp, fap, tag, lem_b, lem_a, root_b, root_a, features))
        flush()
        conn.executemany("""
            INSERT INTO words(chapter, verse, word, form_buck, form_ar, form_buck_plain, form_ar_plain,
                              tag_chain, primary_tag, lemma_buck, lemma_ar, root_buck, root_ar, features)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, word_rows)

        conn.execute("INSERT INTO meta(key,value) VALUES('source_file', ?)", (str(src),))
        conn.execute("INSERT INTO meta(key,value) VALUES('segment_count', ?)", (str(count),))
        conn.execute("INSERT INTO meta(key,value) VALUES('word_count', ?)", (str(len(word_rows)),))
        conn.execute("INSERT INTO meta(key,value) VALUES('builder_version', '1.0')")
        conn.commit()
        print(f"Imported {count:,} segments and {len(word_rows):,} words into {db_path}")
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import Quranic Arabic Corpus morphology v0.4 into SQLite.")
    parser.add_argument("--input", type=Path, help="Path to quranic-corpus-morphology-0.4.txt. If omitted, downloads a public mirror.")
    parser.add_argument("--db", type=Path, default=Path("data/quran_corpus.sqlite3"), help="Output SQLite DB path.")
    parser.add_argument("--download-to", type=Path, default=Path("data/quranic-corpus-morphology-0.4.txt"), help="Where to save downloaded morphology file.")
    args = parser.parse_args(argv)

    src = args.input
    if src is None:
        src = args.download_to
        if not src.exists():
            src = download_first(DEFAULT_URLS, src)
    if not src.exists():
        print(f"Input file not found: {src}", file=sys.stderr)
        return 2
    import_file(src, args.db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

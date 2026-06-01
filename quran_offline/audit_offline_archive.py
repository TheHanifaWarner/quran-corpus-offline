from __future__ import annotations

import argparse
import collections
import html.parser
import json
import re
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Iterable

from .surah_data import AYAH_COUNTS, TREEBANK_CHAPTERS

ROOT = Path(__file__).resolve().parent.parent
CACHE_INDEX = ROOT / "cache" / "index.json"
ASSET_INDEX = ROOT / "cache" / "assets.json"
CACHE_PAGES = ROOT / "cache" / "pages"
CACHE_ASSETS = ROOT / "cache" / "assets"
DB_PATH = ROOT / "data" / "quran_corpus.sqlite3"

EXPECTED_SURAHS = 114
EXPECTED_VERSES = sum(AYAH_COUNTS.values())
EXPECTED_WORDS = 77429
EXPECTED_SEGMENTS = 128219
CORPUS_HOST = "corpus.quran.com"
ACTIVE_ATTRS = {"href", "src", "action", "srcset"}


def normalise_corpus_url(url: str) -> str:
    url = urllib.parse.unquote(url or "")
    if not url:
        url = "https://corpus.quran.com/"
    elif url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = "https://corpus.quran.com" + url
    elif not urllib.parse.urlparse(url).scheme:
        url = urllib.parse.urljoin("https://corpus.quran.com/", url)
    if url.startswith("http://corpus.quran.com"):
        url = url.replace("http://", "https://", 1)
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = urllib.parse.urlencode(sorted(query))
    return urllib.parse.urlunparse((parsed.scheme or "https", parsed.netloc or CORPUS_HOST, parsed.path or "/", "", query, ""))


def corpus_url(path: str, **params: object) -> str:
    query = urllib.parse.urlencode(sorted((k, str(v)) for k, v in params.items()))
    return urllib.parse.urlunparse(("https", CORPUS_HOST, path, "", query, ""))


def word_morphology_url(chapter: int, verse: int, word: int) -> str:
    loc = urllib.parse.quote(f"({chapter}:{verse}:{word})", safe="")
    return f"https://corpus.quran.com/wordmorphology.jsp?location={loc}"


def is_word_morphology_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(normalise_corpus_url(url))
    return parsed.path.endswith("/wordmorphology.jsp") and "location=" in parsed.query


def is_safe_rel(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    p = PurePosixPath(rel)
    return not p.is_absolute() and ".." not in p.parts


def rel_to_path(rel: str) -> Path:
    rel = rel.replace("\\", "/")
    return ROOT.joinpath(*PurePosixPath(rel).parts)


def load_json(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8"))


class Audit:
    def __init__(self) -> None:
        self.facts: list[str] = []
        self.warnings: list[str] = []
        self.failures: list[str] = []

    def fact(self, message: str) -> None:
        self.facts.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def print_report(self) -> None:
        print("Offline Quran Corpus archive audit")
        print("=" * 41)
        for title, rows in (("Facts", self.facts), ("Warnings", self.warnings), ("Failures", self.failures)):
            print()
            print(title + ":")
            if rows:
                for row in rows:
                    print(f"  - {row}")
            else:
                print("  - none")


def check_index(name: str, index_path: Path, folder: Path, expected_ext: str | None, audit: Audit) -> dict[str, str]:
    data = load_json(index_path)
    audit.fact(f"{name}: {len(data):,} mapped entries")
    if not data:
        audit.fail(f"{name}: index is missing or empty at {index_path}")
        return data

    duplicate_values = [rel for rel, count in collections.Counter(data.values()).items() if count > 1]
    if duplicate_values:
        audit.fail(f"{name}: {len(duplicate_values):,} duplicate local file mappings")

    missing = []
    zero = []
    bad_rel = []
    bad_hosts = []
    wrong_ext = []
    mapped_names = set()
    for url, rel in data.items():
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != CORPUS_HOST:
            bad_hosts.append(url)
        if not is_safe_rel(rel):
            bad_rel.append(rel)
            continue
        p = rel_to_path(rel)
        mapped_names.add(p.name.lower())
        if expected_ext and p.suffix.lower() != expected_ext:
            wrong_ext.append(rel)
        if not p.exists():
            missing.append(rel)
        elif p.stat().st_size == 0:
            zero.append(rel)

    if bad_hosts:
        audit.fail(f"{name}: {len(bad_hosts):,} keys use an unexpected host or scheme")
    if bad_rel:
        audit.fail(f"{name}: {len(bad_rel):,} mappings have unsafe relative paths")
    if wrong_ext:
        audit.fail(f"{name}: {len(wrong_ext):,} mappings have an unexpected extension")
    if missing:
        audit.fail(f"{name}: {len(missing):,} mapped files are missing")
    if zero:
        audit.fail(f"{name}: {len(zero):,} mapped files are zero bytes")

    files = [p for p in folder.glob("*") if p.is_file()]
    orphans = [p for p in files if p.name.lower() not in mapped_names]
    if orphans:
        audit.warn(f"{name}: {len(orphans):,} orphan files exist in {folder}; leaving them untouched")
    audit.fact(f"{name}: {len(files):,} files on disk, {len(orphans):,} orphan files")
    return data


def open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def check_database_and_coverage(index: dict[str, str], audit: Audit) -> None:
    if not DB_PATH.exists():
        audit.fail(f"SQLite database is missing: {DB_PATH}")
        return

    with open_db() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        needed = {"meta", "surahs", "words", "segments"}
        missing_tables = needed - tables
        if missing_tables:
            audit.fail(f"SQLite database is missing tables: {', '.join(sorted(missing_tables))}")
            return

        surahs = conn.execute("SELECT COUNT(*) FROM surahs").fetchone()[0]
        verses = conn.execute("SELECT COUNT(*) FROM (SELECT DISTINCT chapter, verse FROM words)").fetchone()[0]
        words = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
        segments = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
        roots = conn.execute("SELECT COUNT(DISTINCT root_buck) FROM segments WHERE root_buck IS NOT NULL AND root_buck != ''").fetchone()[0]
        lemmas = conn.execute("SELECT COUNT(DISTINCT lemma_buck) FROM segments WHERE lemma_buck IS NOT NULL AND lemma_buck != ''").fetchone()[0]
        audit.fact(f"SQLite counts: {surahs:,} surahs, {verses:,} verses, {words:,} words, {segments:,} segments, {roots:,} roots, {lemmas:,} lemmas")

        if surahs != EXPECTED_SURAHS:
            audit.fail(f"SQLite surah count is {surahs:,}; expected {EXPECTED_SURAHS:,}")
        if verses != EXPECTED_VERSES:
            audit.fail(f"SQLite verse count is {verses:,}; expected {EXPECTED_VERSES:,}")
        if words != EXPECTED_WORDS:
            audit.fail(f"SQLite word count is {words:,}; expected {EXPECTED_WORDS:,}")
        if segments != EXPECTED_SEGMENTS:
            audit.fail(f"SQLite segment count is {segments:,}; expected {EXPECTED_SEGMENTS:,}")

        bad_surah_counts = conn.execute("""
            SELECT s.id, s.ayah_count, COUNT(DISTINCT w.verse) AS db_verses
            FROM surahs s LEFT JOIN words w ON w.chapter = s.id
            GROUP BY s.id, s.ayah_count HAVING s.ayah_count != db_verses
        """).fetchall()
        if bad_surah_counts:
            audit.fail(f"SQLite verse coverage mismatch in {len(bad_surah_counts):,} surahs")

        word_rows = conn.execute("SELECT chapter, verse, word FROM words ORDER BY chapter, verse, word").fetchall()
        root_rows = conn.execute("""
            SELECT DISTINCT root_buck FROM segments
            WHERE root_buck IS NOT NULL AND root_buck != ''
            ORDER BY root_buck
        """).fetchall()

    missing_wordbyword = []
    missing_translation = []
    for chapter, count in AYAH_COUNTS.items():
        for verse in range(1, count + 1):
            if corpus_url("/wordbyword.jsp", chapter=chapter, verse=verse) not in index:
                missing_wordbyword.append((chapter, verse))
            if corpus_url("/translation.jsp", chapter=chapter, verse=verse) not in index:
                missing_translation.append((chapter, verse))
    if missing_wordbyword:
        audit.fail(f"Missing {len(missing_wordbyword):,} word-by-word cached verse pages")
    else:
        audit.fact(f"Word-by-word cached verse pages: {EXPECTED_VERSES:,}/{EXPECTED_VERSES:,}")
    if missing_translation:
        audit.fail(f"Missing {len(missing_translation):,} translation cached verse pages")
    else:
        audit.fact(f"Translation cached verse pages: {EXPECTED_VERSES:,}/{EXPECTED_VERSES:,}")

    treebank_expected = sum(AYAH_COUNTS[c] for c in TREEBANK_CHAPTERS)
    treebank_present = sum(
        1
        for chapter in TREEBANK_CHAPTERS
        for verse in range(1, AYAH_COUNTS[chapter] + 1)
        if corpus_url("/treebank.jsp", chapter=chapter, verse=verse) in index
    )
    audit.fact(f"Treebank cached pages for configured chapters: {treebank_present:,}/{treebank_expected:,}")
    if treebank_present != treebank_expected:
        audit.fail(f"Missing {treebank_expected - treebank_present:,} treebank cached pages for configured chapters")

    exact_word_morphology = 0
    missing_exact_word_morphology = []
    for row in word_rows:
        url = word_morphology_url(row["chapter"], row["verse"], row["word"])
        if url in index:
            exact_word_morphology += 1
        else:
            missing_exact_word_morphology.append((row["chapter"], row["verse"], row["word"]))
    audit.fact(f"Exact cached word morphology pages: {exact_word_morphology:,}/{len(word_rows):,}")
    if missing_exact_word_morphology:
        audit.warn(f"{len(missing_exact_word_morphology):,} word morphology pages require SQLite fallback; first missing: {missing_exact_word_morphology[:5]}")
    if len(word_rows) != EXPECTED_WORDS:
        audit.fail("Word morphology fallback cannot cover all expected words because the DB word count is wrong")

    missing_roots = []
    for row in root_rows:
        url = corpus_url("/qurandictionary.jsp", q=row["root_buck"])
        if url not in index:
            missing_roots.append(row["root_buck"])
    if missing_roots:
        audit.fail(f"Missing {len(missing_roots):,} cached root dictionary pages")
    else:
        audit.fact(f"Root dictionary cached pages: {len(root_rows):,}/{len(root_rows):,}")


class RefParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if value is not None and name.lower() in ACTIVE_ATTRS:
                self.refs.append((name.lower(), value))


def css_urls(text: str) -> Iterable[str]:
    for match in re.finditer(r"url\(\s*(['\"]?)(.*?)\1\s*\)", text, flags=re.I | re.S):
        yield match.group(2).strip()


def split_srcset(srcset: str) -> Iterable[str]:
    for item in srcset.split(","):
        bits = item.strip().split()
        if bits:
            yield bits[0]


def is_ignored_ref(ref: str) -> bool:
    lower = ref.strip().lower()
    return not lower or lower.startswith(("#", "mailto:", "javascript:", "data:", "about:", "tel:"))


def active_remote_refs(base_url: str, body: str, ctype: str) -> list[str]:
    refs = []
    if "html" in ctype:
        parser = RefParser()
        parser.feed(body)
        for attr, raw in parser.refs:
            candidates = split_srcset(raw) if attr == "srcset" else [raw]
            for candidate in candidates:
                if is_ignored_ref(candidate):
                    continue
                parsed = urllib.parse.urlparse(urllib.parse.urljoin(base_url, candidate))
                if parsed.scheme in {"http", "https"} and parsed.hostname not in {"127.0.0.1", "localhost"}:
                    refs.append(candidate)
    if "html" in ctype or "css" in ctype:
        for raw in css_urls(body):
            if is_ignored_ref(raw):
                continue
            parsed = urllib.parse.urlparse(urllib.parse.urljoin(base_url, raw))
            if parsed.scheme in {"http", "https"} and parsed.hostname not in {"127.0.0.1", "localhost"}:
                refs.append(raw)
    return refs


def local_refs(base_url: str, body: str, ctype: str) -> set[str]:
    out: set[str] = set()
    if "html" in ctype:
        parser = RefParser()
        parser.feed(body)
        for attr, raw in parser.refs:
            candidates = split_srcset(raw) if attr == "srcset" else [raw]
            for candidate in candidates:
                if is_ignored_ref(candidate):
                    continue
                url = urllib.parse.urljoin(base_url, candidate)
                parsed = urllib.parse.urlparse(url)
                if parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost"}:
                    out.add(urllib.parse.urlunparse(("", "", parsed.path or "/", "", parsed.query, "")))
    if "html" in ctype or "css" in ctype:
        for raw in css_urls(body):
            if is_ignored_ref(raw):
                continue
            url = urllib.parse.urljoin(base_url, raw)
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost"}:
                out.add(urllib.parse.urlunparse(("", "", parsed.path or "/", "", parsed.query, "")))
    return out


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def get_local(base: str, path: str, timeout: float = 15) -> tuple[int, str, bytes]:
    url = urllib.parse.urljoin(base, path)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()
    except Exception as exc:
        return 0, "text/plain", f"{type(exc).__name__}: {exc}".encode("utf-8", errors="replace")


def ref_to_corpus_url(parsed: urllib.parse.ParseResult) -> str:
    return normalise_corpus_url(
        urllib.parse.urlunparse(("https", CORPUS_HOST, parsed.path or "/", "", parsed.query, ""))
    )


def classify_local_ref(ref: str, index: dict[str, str], assets: dict[str, str]) -> tuple[str, str | None]:
    parsed = urllib.parse.urlparse(ref)
    path = parsed.path or "/"
    query = urllib.parse.parse_qs(parsed.query)
    local_routes = {"/", "/search", "/dictionary", "/lemmas", "/mirror", "/status", "/graphimage"}
    asset_exts = {".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico"}
    dynamic_asset_paths = {"/wordimage"}
    ext = Path(path).suffix.lower()

    if path in local_routes:
        return "ok", None
    if path == "/asset":
        url = normalise_corpus_url(query.get("url", [""])[0])
        return ("ok", url) if url in assets else ("missing-asset", url)
    if path == "/cached":
        url = normalise_corpus_url(query.get("url", [""])[0])
        if url in index or (is_word_morphology_url(url) and DB_PATH.exists()):
            return "ok", url
        return "not-cached", url
    if ext in asset_exts or path in dynamic_asset_paths:
        url = ref_to_corpus_url(parsed)
        return ("ok", url) if url in assets else ("missing-asset", url)
    if ext in {".jsp", ".html", ".htm"} or path.startswith(("/documentation", "/java/")):
        url = ref_to_corpus_url(parsed)
        if url in index or (is_word_morphology_url(url) and DB_PATH.exists()):
            return "ok", url
        return "not-cached", url
    return "unknown", ref


def check_server(audit: Audit) -> None:
    index = load_json(CACHE_INDEX)
    assets = load_json(ASSET_INDEX)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    cmd = [sys.executable, "-m", "quran_offline.server", "--host", "127.0.0.1", "--port", str(port), "--no-browser"]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creationflags)
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                status, _, _ = get_local(base, "/status", timeout=1)
                if status == 200:
                    break
            except Exception:
                time.sleep(0.2)
        else:
            audit.fail("Local server did not start within 20 seconds")
            return

        smoke_paths = [
            "/",
            "/status",
            "/mirror",
            "/wordbyword.jsp?chapter=1&verse=1",
            "/wordbyword.jsp?chapter=55&verse=5",
            "/translation.jsp?chapter=1&verse=1",
            "/grammar.jsp?chapter=1&verse=1&token=1",
            "/treebank.jsp?chapter=1&verse=1",
            "/qurandictionary.jsp?q=rHm",
            "/lemmas.jsp",
            "/verbs.jsp",
            "/morphologicalsearch.jsp",
            "/ontology.jsp",
            "/documentation/tagset.jsp",
            "/search.jsp?q=3%3A6",
            "/search.jsp?q=56%3A4",
            "/wordmorphology.jsp?location=%286%3A119%3A4%29",
            "/wordmorphology.jsp?location=%286%3A122%3A7%29",
            "/wordmorphology.jsp?location=%286%3A125%3A15%29",
            "/wordmorphology.jsp?location=%286%3A126%3A7%29",
            "/wordmorphology.jsp?location=%287%3A157%3A25%29",
        ]
        checked_refs: set[str] = set()
        word_image_refs: set[str] = set()
        for path in smoke_paths:
            status, ctype, raw = get_local(base, path)
            if status != 200:
                audit.fail(f"Server smoke check failed for {path}: HTTP {status}")
                continue
            body = raw.decode("utf-8", errors="replace")
            remotes = active_remote_refs(base + path, body, ctype)
            if remotes:
                audit.fail(f"Server response for {path} contains active external references: {remotes[:5]}")
            refs = local_refs(base + path, body, ctype)
            if path == "/wordbyword.jsp?chapter=55&verse=5":
                word_image_refs.update(ref for ref in refs if "wordimage" in ref)
            for ref in refs:
                checked_refs.add(ref)

        broken_refs = []
        text_asset_refs = []
        not_cached_refs = 0
        for ref in sorted(checked_refs):
            outcome, target = classify_local_ref(ref, index, assets)
            if outcome == "missing-asset":
                broken_refs.append((ref, "missing mapped asset"))
            elif outcome == "unknown":
                broken_refs.append((ref, "unknown local route"))
            elif outcome == "not-cached":
                not_cached_refs += 1
            elif outcome == "ok" and target and Path(urllib.parse.urlparse(target).path).suffix.lower() in {".css", ".html", ".htm"}:
                text_asset_refs.append(ref)

        for ref in sorted(set(text_asset_refs)):
            status, ctype, raw = get_local(base, ref, timeout=5)
            body = raw.decode("utf-8", errors="replace") if ("html" in ctype or "css" in ctype) else ""
            if status != 200:
                broken_refs.append((ref, status))
                continue
            remotes = active_remote_refs(base + ref, body, ctype) if body else []
            if remotes:
                audit.fail(f"Local linked response for {ref} contains active external references: {remotes[:5]}")
        if broken_refs:
            audit.fail(f"{len(broken_refs):,} local linked resources returned non-200 responses; first: {broken_refs[:5]}")

        bad_word_images = []
        for ref in sorted(word_image_refs):
            status, ctype, raw = get_local(base, ref, timeout=5)
            if status != 200 or not ctype.startswith("image/png") or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                bad_word_images.append((ref, status, ctype, len(raw)))
        if bad_word_images:
            audit.fail(f"{len(bad_word_images):,} Arabic word images failed to render as PNG; first: {bad_word_images[:5]}")
        audit.fact(f"Server smoke pages: {len(smoke_paths):,}; local linked resources checked: {len(checked_refs):,}; Arabic word images checked: {len(word_image_refs):,}; deliberate not-cached diagnostics: {not_cached_refs:,}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def check_windows_launch(audit: Audit) -> None:
    batch_files = sorted(ROOT.glob("*.bat"))
    if not batch_files:
        audit.fail("No Windows batch launch/import/build scripts found")
        return
    for path in batch_files:
        text = path.read_text("utf-8", errors="replace")
        if 'cd /d "%~dp0"' not in text:
            audit.fail(f"{path.name} does not anchor execution to its own folder with cd /d \"%~dp0\"")
    start = ROOT / "Run Offline Corpus.bat"
    if start.exists():
        text = start.read_text("utf-8", errors="replace")
        if "if not exist data\\quran_corpus.sqlite3" not in text:
            audit.fail("Run Offline Corpus.bat does not guard database import behind the existing SQLite file check")
        if "/cached?url=https%%3A%%2F%%2Fcorpus.quran.com%%2F" not in text:
            audit.fail("Run Offline Corpus.bat does not open the cached Corpus homepage")
        elif DB_PATH.exists():
            audit.fact("Windows launcher will not trigger morphology import/download because data\\quran_corpus.sqlite3 exists")
    else:
        audit.fail("Run Offline Corpus.bat is missing")
    audit.fact(f"Windows batch scripts checked: {len(batch_files):,}")


def verify_db_only(audit: Audit) -> None:
    """Lightweight check: the SQLite morphology DB exists and has correct counts.
    Does not require any page cache."""
    if not DB_PATH.exists():
        audit.fail(f"SQLite database is missing: {DB_PATH}")
        return
    with open_db() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = {"meta", "surahs", "words", "segments"} - tables
        if missing:
            audit.fail(f"SQLite database is missing tables: {', '.join(sorted(missing))}")
            return
        surahs = conn.execute("SELECT COUNT(*) FROM surahs").fetchone()[0]
        verses = conn.execute("SELECT COUNT(*) FROM (SELECT DISTINCT chapter, verse FROM words)").fetchone()[0]
        words = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
        segments = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
    audit.fact(f"SQLite counts: {surahs:,} surahs, {verses:,} verses, {words:,} words, {segments:,} segments")
    if surahs != EXPECTED_SURAHS:
        audit.fail(f"SQLite surah count is {surahs:,}; expected {EXPECTED_SURAHS:,}")
    if verses != EXPECTED_VERSES:
        audit.fail(f"SQLite verse count is {verses:,}; expected {EXPECTED_VERSES:,}")
    if words != EXPECTED_WORDS:
        audit.fail(f"SQLite word count is {words:,}; expected {EXPECTED_WORDS:,}")
    if segments != EXPECTED_SEGMENTS:
        audit.fail(f"SQLite segment count is {segments:,}; expected {EXPECTED_SEGMENTS:,}")


def verify_core(audit: Audit) -> None:
    """Check db-only plus that all word-by-word, translation, and root dictionary
    pages exist in the cache index."""
    verify_db_only(audit)
    index = load_json(CACHE_INDEX)
    audit.fact(f"cache/index.json: {len(index):,} mapped entries")
    missing_wb = missing_tr = 0
    for c, n in AYAH_COUNTS.items():
        for v in range(1, n + 1):
            if corpus_url("/wordbyword.jsp", chapter=c, verse=v) not in index:
                missing_wb += 1
            if corpus_url("/translation.jsp", chapter=c, verse=v) not in index:
                missing_tr += 1
    if missing_wb:
        audit.fail(f"Missing {missing_wb:,} word-by-word cached pages")
    else:
        audit.fact(f"Word-by-word cached verse pages: {EXPECTED_VERSES:,}/{EXPECTED_VERSES:,}")
    if missing_tr:
        audit.fail(f"Missing {missing_tr:,} translation cached pages")
    else:
        audit.fact(f"Translation cached verse pages: {EXPECTED_VERSES:,}/{EXPECTED_VERSES:,}")
    if DB_PATH.exists():
        with open_db() as conn:
            roots = [r[0] for r in conn.execute(
                "SELECT DISTINCT root_buck FROM segments WHERE root_buck IS NOT NULL AND root_buck != '' ORDER BY root_buck")]
        miss = [r for r in roots if corpus_url("/qurandictionary.jsp", q=r) not in index]
        if miss:
            audit.fail(f"Missing {len(miss):,} root dictionary cached pages")
        else:
            audit.fact(f"Root dictionary cached pages: {len(roots):,}/{len(roots):,}")


def verify_morphology(audit: Audit) -> None:
    """Check db-only plus that every wordmorphology.jsp location is cached."""
    verify_db_only(audit)
    if not DB_PATH.exists():
        audit.fail("Word morphology verification requires the SQLite DB to enumerate locations")
        return
    index = load_json(CACHE_INDEX)
    with open_db() as conn:
        rows = conn.execute("SELECT chapter, verse, word FROM words ORDER BY chapter, verse, word").fetchall()
    exact = 0
    missing = []
    for row in rows:
        if word_morphology_url(row["chapter"], row["verse"], row["word"]) in index:
            exact += 1
        else:
            missing.append((row["chapter"], row["verse"], row["word"]))
    audit.fact(f"Exact cached word morphology pages: {exact:,}/{len(rows):,}")
    if missing:
        audit.warn(f"{len(missing):,} word morphology pages not cached (would use SQLite fallback); first: {missing[:5]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only audit of the offline Quran Corpus archive.")
    parser.add_argument("--skip-server", action="store_true", help="Skip localhost server smoke checks.")
    parser.add_argument("--verify", choices=["db-only", "core", "morphology", "full"], default="full",
                        help="Scope of verification. 'full' (default) is the complete archive audit; "
                             "'db-only' needs no page cache; 'core'/'morphology' check those page sets.")
    args = parser.parse_args(argv)

    audit = Audit()
    if args.verify == "db-only":
        verify_db_only(audit)
    elif args.verify == "core":
        verify_core(audit)
    elif args.verify == "morphology":
        verify_morphology(audit)
    else:
        index = check_index("cache/index.json", CACHE_INDEX, CACHE_PAGES, ".html", audit)
        check_index("cache/assets.json", ASSET_INDEX, CACHE_ASSETS, None, audit)
        check_database_and_coverage(index, audit)
        check_windows_launch(audit)
        if not args.skip_server:
            check_server(audit)

    audit.print_report()
    return 1 if audit.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

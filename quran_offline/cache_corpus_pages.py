from __future__ import annotations

"""Build a one-time, personal offline cache of Quranic Arabic Corpus pages.

This optimised builder adds:
  * build PROFILES (db-only / core / morphology / full) plus the legacy --mode
  * a respectful PARALLEL downloader (bounded workers + global rate limit)
  * RETRY with exponential backoff, Retry-After support, and adaptive slow-down
    on repeated 429/403/5xx responses
  * RESUMABILITY: existing index/asset entries are skipped; atomic checkpoints
  * --estimate / --dry-run planning with time + disk estimates
  * live PROGRESS (done/total, rate, ETA, failures, retries) and a build report

Politeness first: aggressive scraping is never the default. The defaults are a
small worker count and a conservative global request rate so we do not hammer
corpus.quran.com. Be a good citizen; build once and keep your cache.
"""

import argparse
import hashlib
import json
import queue
import random
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from .surah_data import AYAH_COUNTS, TREEBANK_CHAPTERS

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "pages"
ASSET_DIR = ROOT / "cache" / "assets"
CACHE_ROOT = ROOT / "cache"
INDEX_PATH = ROOT / "cache" / "index.json"
ASSET_INDEX_PATH = ROOT / "cache" / "assets.json"
DB_PATH = ROOT / "data" / "quran_corpus.sqlite3"
BASE = "https://corpus.quran.com/"
UA = "QuranCorpusOfflineBuilder/1.1 (+personal offline cache; respectful low-volume)"

ASSET_EXTS = {".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico"}

# Heuristic averages from a completed reference archive - used ONLY for --estimate.
AVG_PAGE_BYTES = 14700
AVG_ASSET_BYTES = 2060
# Approximate full-mirror totals (for planning/estimates only).
EXPECTED = {"verses": 6236, "morphology": 77429, "roots": 1642,
            "full_pages": 149905, "full_assets": 78119}

# Conservative, respectful defaults. Raise only if you know the site tolerates it.
# The default is deliberately gentle (2 req/s) so we never encourage hammering
# corpus.quran.com. Advanced users can opt into faster runs, e.g.
#   --workers 4 --rate-limit 6
DEFAULT_WORKERS = 4
DEFAULT_RATE = 2.0          # max requests/second globally (intentionally conservative)
MIN_RATE_FLOOR = 0.5        # adaptive slow-down never goes slower than this
DEFAULT_TIMEOUT = 45
DEFAULT_MAX_RETRIES = 4
CHECKPOINT_EVERY = 100      # atomic index/asset save cadence

PROFILES = ("db-only", "core", "morphology", "full")

START_PAGES = [
    "https://corpus.quran.com/",
    "https://corpus.quran.com/wordbyword.jsp",
    "https://corpus.quran.com/translation.jsp",
    "https://corpus.quran.com/treebank.jsp",
    "https://corpus.quran.com/grammar.jsp?chapter=1&verse=1&token=1",
    "https://corpus.quran.com/qurandictionary.jsp",
    "https://corpus.quran.com/lemmas.jsp",
    "https://corpus.quran.com/verbs.jsp",
    "https://corpus.quran.com/morphologicalsearch.jsp",
    "https://corpus.quran.com/ontology.jsp",
    "https://corpus.quran.com/ontologyconcept.jsp?id=concept",
    "https://corpus.quran.com/documentation/",
    "https://corpus.quran.com/documentation/tagset.jsp",
    "https://corpus.quran.com/documentation/features.jsp",
    "https://corpus.quran.com/documentation/dependencygraph.jsp",
    "https://corpus.quran.com/documentation/syntacticrelations.jsp",
    "https://corpus.quran.com/documentation/phrasetagset.jsp",
    "https://corpus.quran.com/java/",
]

SKIP_PATTERNS = [
    # Community/account/external/non-study areas. External domains are blocked by allowed_url().
    "messageboard", "feedback", "login", "signin", "mail-archive", "facebook", "waqt.org", "quranicaudio.com"
]


# --------------------------------------------------------------------------- #
# Index / URL helpers (cache convention preserved exactly)
# --------------------------------------------------------------------------- #
def load_index(path: Path) -> dict[str, str]:
    if path.exists():
        return json.loads(path.read_text("utf-8"))
    return {}


def save_index(index: dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), "utf-8")
    tmp.replace(path)


def normalise_url(url: str) -> str:
    url = urllib.parse.urljoin(BASE, url)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "http" and parsed.netloc == "corpus.quran.com":
        parsed = parsed._replace(scheme="https")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = urllib.parse.urlencode(sorted(query))
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", query, ""))


def allowed_url(url: str) -> bool:
    p = urllib.parse.urlparse(url)
    if p.netloc != "corpus.quran.com":
        return False
    lower = url.lower()
    if any(x in lower for x in SKIP_PATTERNS):
        return False
    if p.path.endswith(('.pdf', '.zip', '.jar')):
        return False
    return True


def key_to_path(url: str, asset: bool = False) -> Path:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    if asset:
        ext = Path(urllib.parse.urlparse(url).path).suffix.lower() or ".bin"
        return ASSET_DIR / f"{h}{ext}"
    return CACHE_DIR / f"{h}.html"


def is_asset_url(url: str) -> bool:
    return Path(urllib.parse.urlparse(url).path).suffix.lower() in ASSET_EXTS


def extract_links(html: str, base_url: str) -> tuple[set[str], set[str]]:
    hrefs: set[str] = set()
    assets: set[str] = set()
    for m in re.finditer(r"href=[\"']([^\"']+)[\"']", html, flags=re.I):
        href = m.group(1)
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
            continue
        full = normalise_url(urllib.parse.urljoin(base_url, href))
        if urllib.parse.urlparse(full).netloc == "corpus.quran.com":
            if is_asset_url(full):
                assets.add(full)
            elif allowed_url(full):
                hrefs.add(full)
    for m in re.finditer(r"src=[\"']([^\"']+)[\"']", html, flags=re.I):
        src = m.group(1)
        full = normalise_url(urllib.parse.urljoin(base_url, src))
        if urllib.parse.urlparse(full).netloc == "corpus.quran.com":
            assets.add(full)
    return hrefs, assets


# --------------------------------------------------------------------------- #
# Deterministic URL generators
# --------------------------------------------------------------------------- #
def wordbyword_urls() -> list[str]:
    return [f"https://corpus.quran.com/wordbyword.jsp?chapter={c}&verse={v}"
            for c, n in AYAH_COUNTS.items() for v in range(1, n + 1)]


def translation_urls() -> list[str]:
    return [f"https://corpus.quran.com/translation.jsp?chapter={c}&verse={v}"
            for c, n in AYAH_COUNTS.items() for v in range(1, n + 1)]


def grammar_urls() -> list[str]:
    return [f"https://corpus.quran.com/grammar.jsp?chapter={c}&verse={v}&token=1"
            for c, n in AYAH_COUNTS.items() for v in range(1, n + 1)]


def treebank_urls() -> list[str]:
    return [f"https://corpus.quran.com/treebank.jsp?chapter={c}&verse={v}"
            for c, n in AYAH_COUNTS.items() if c in TREEBANK_CHAPTERS for v in range(1, n + 1)]


def deterministic_verse_urls() -> list[str]:
    urls: list[str] = []
    for c, count in AYAH_COUNTS.items():
        for v in range(1, count + 1):
            urls.append(f"https://corpus.quran.com/wordbyword.jsp?chapter={c}&verse={v}")
            urls.append(f"https://corpus.quran.com/translation.jsp?chapter={c}&verse={v}")
            urls.append(f"https://corpus.quran.com/grammar.jsp?chapter={c}&verse={v}&token=1")
            if c in TREEBANK_CHAPTERS:
                urls.append(f"https://corpus.quran.com/treebank.jsp?chapter={c}&verse={v}")
    return urls


def dictionary_urls_from_db() -> list[str]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        roots = [r[0] for r in conn.execute(
            "SELECT DISTINCT root_buck FROM segments WHERE root_buck IS NOT NULL AND root_buck != '' ORDER BY root_buck")]
    finally:
        conn.close()
    return [f"https://corpus.quran.com/qurandictionary.jsp?q={urllib.parse.quote(root)}" for root in roots]


def word_morphology_urls_from_db() -> list[str]:
    """Every wordmorphology.jsp location, generated from the local DB words table."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("SELECT chapter, verse, word FROM words ORDER BY chapter, verse, word").fetchall()
    finally:
        conn.close()
    out = []
    for c, v, w in rows:
        loc = urllib.parse.quote(f"({c}:{v}:{w})", safe="")
        out.append(f"https://corpus.quran.com/wordmorphology.jsp?location={loc}")
    return out


def dedup_norm(urls: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for u in urls:
        nu = normalise_url(u)
        if allowed_url(nu):
            seen.setdefault(nu, None)
    return list(seen)


def page_list_for_mode(mode: str) -> list[str]:
    """Legacy --mode behaviour (preserved)."""
    urls = list(START_PAGES)
    if mode in {"verse-pages", "all"}:
        urls.extend(deterministic_verse_urls())
    if mode in {"dictionary", "all"}:
        urls.extend(dictionary_urls_from_db())
        urls.extend(["https://corpus.quran.com/qurandictionary.jsp",
                     "https://corpus.quran.com/lemmas.jsp",
                     "https://corpus.quran.com/verbs.jsp"])
    return dedup_norm(urls)


def seeds_for_profile(profile: str) -> tuple[list[str], bool]:
    """Return (seed urls, crawl?) for a profile. Assets are always followed unless disabled."""
    if profile == "db-only":
        return [], False
    if profile == "core":
        seeds = (["https://corpus.quran.com/", "https://corpus.quran.com/wordbyword.jsp",
                  "https://corpus.quran.com/translation.jsp", "https://corpus.quran.com/qurandictionary.jsp"]
                 + wordbyword_urls() + translation_urls() + dictionary_urls_from_db())
        return dedup_norm(seeds), False
    if profile == "morphology":
        seeds = (["https://corpus.quran.com/", "https://corpus.quran.com/wordbyword.jsp"]
                 + word_morphology_urls_from_db())
        return dedup_norm(seeds), False
    if profile == "full":
        seeds = (list(START_PAGES) + deterministic_verse_urls()
                 + dictionary_urls_from_db() + word_morphology_urls_from_db()
                 + ["https://corpus.quran.com/lemmas.jsp", "https://corpus.quran.com/verbs.jsp",
                    "https://corpus.quran.com/ontology.jsp"])
        return dedup_norm(seeds), True
    raise ValueError(f"Unknown profile: {profile}")


# --------------------------------------------------------------------------- #
# Respectful pacing + retry
# --------------------------------------------------------------------------- #
class Pacer:
    """Global rate limiter with adaptive slow-down and cooldown pauses."""

    def __init__(self, rate: float):
        self.lock = threading.Lock()
        self.base_interval = (1.0 / rate) if rate > 0 else 0.0
        self.interval = self.base_interval
        self.max_interval = 1.0 / MIN_RATE_FLOOR
        self.next_slot = time.monotonic()
        self.pause_until = 0.0
        self.consec_rate_limit = 0

    def acquire(self) -> None:
        now = time.monotonic()
        with self.lock:
            start = max(now, self.next_slot, self.pause_until)
            self.next_slot = start + self.interval
        wait = start - now
        if wait > 0:
            time.sleep(wait)

    def note_success(self) -> None:
        with self.lock:
            if self.consec_rate_limit:
                self.consec_rate_limit = 0
                # gently restore speed
                self.interval = max(self.base_interval, self.interval / 1.5)

    def note_rate_limit(self, retry_after: float | None) -> float:
        with self.lock:
            self.consec_rate_limit += 1
            self.interval = min(max(self.interval * 2, self.base_interval or 0.1), self.max_interval)
            cooldown = retry_after if retry_after else float(min(60, 2 ** min(self.consec_rate_limit, 6)))
            self.pause_until = max(self.pause_until, time.monotonic() + cooldown)
            return cooldown


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return min(float(value), 300.0)
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(value)
        if dt is not None:
            delta = (dt.timestamp() - time.time())
            return max(0.0, min(delta, 300.0))
    except Exception:
        return None
    return None


def backoff_sleep(attempt: int, pacer: Pacer, stop: threading.Event) -> None:
    delay = min(30.0, (2 ** (attempt - 1))) + random.uniform(0, 0.5)
    end = time.monotonic() + delay
    while time.monotonic() < end:
        if stop.is_set():
            return
        time.sleep(min(0.5, end - time.monotonic()))


def http_fetch(url: str, pacer: Pacer, timeout: int, max_retries: int,
               stats: "BuildStats", stop: threading.Event) -> tuple[bool, int, bytes]:
    attempt = 0
    while True:
        if stop.is_set():
            return False, 0, b""
        # honor any global cooldown set by note_rate_limit
        while time.monotonic() < pacer.pause_until and not stop.is_set():
            time.sleep(min(0.5, max(0.0, pacer.pause_until - time.monotonic())))
        pacer.acquire()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                status = getattr(r, "status", 200) or 200
            pacer.note_success()
            return True, status, data
        except urllib.error.HTTPError as e:
            code = e.code
            if code in (429, 403, 503) or 500 <= code < 600:
                attempt += 1
                stats.inc("retries")
                if code in (429, 403, 503):
                    ra = parse_retry_after(e.headers.get("Retry-After") if e.headers else None)
                    pacer.note_rate_limit(ra)
                if attempt > max_retries:
                    return False, code, b""
                backoff_sleep(attempt, pacer, stop)
                continue
            return False, code, b""  # permanent (404, etc.)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            attempt += 1
            stats.inc("retries")
            if attempt > max_retries:
                return False, 0, b""
            backoff_sleep(attempt, pacer, stop)
            continue


# --------------------------------------------------------------------------- #
# Stats + progress
# --------------------------------------------------------------------------- #
class BuildStats:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.start = time.monotonic()
        self.saved_pages = 0
        self.saved_assets = 0
        self.skipped = 0
        self.errors = 0
        self.retries = 0
        self.bytes = 0
        self.discovered = 0
        self.failures: list[tuple[str, int]] = []

    def inc(self, name: str, n: int = 1) -> None:
        with self.lock:
            setattr(self, name, getattr(self, name) + n)

    def add_failure(self, url: str, code: int) -> None:
        with self.lock:
            self.errors += 1
            if len(self.failures) < 200:
                self.failures.append((url, code))

    def snapshot(self) -> dict:
        with self.lock:
            elapsed = max(1e-6, time.monotonic() - self.start)
            done = self.saved_pages + self.saved_assets + self.skipped
            return {"saved_pages": self.saved_pages, "saved_assets": self.saved_assets,
                    "skipped": self.skipped, "errors": self.errors, "retries": self.retries,
                    "bytes": self.bytes, "discovered": self.discovered, "done": done,
                    "elapsed": elapsed, "rate": (self.saved_pages + self.saved_assets) / elapsed}


def fmt_hms(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def progress_reporter(stats: BuildStats, total_target: int | None, crawl: bool,
                      stop: threading.Event) -> None:
    while not stop.wait(2.0):
        s = stats.snapshot()
        rate = s["rate"]
        if total_target and not crawl:
            done_units = s["saved_pages"] + s["skipped"]
            remaining = max(0, total_target - done_units)
            eta = remaining / rate if rate > 0 else 0
            pct = 100.0 * done_units / total_target if total_target else 0
            sys.stdout.write(
                f"\r  {done_units:,}/{total_target:,} ({pct:4.1f}%) | "
                f"pages {s['saved_pages']:,} assets {s['saved_assets']:,} skip {s['skipped']:,} "
                f"err {s['errors']:,} retry {s['retries']:,} | {rate:4.1f} req/s | ETA {fmt_hms(eta)}   ")
        else:
            sys.stdout.write(
                f"\r  pages {s['saved_pages']:,} assets {s['saved_assets']:,} skip {s['skipped']:,} "
                f"discovered {s['discovered']:,} err {s['errors']:,} retry {s['retries']:,} | "
                f"{rate:4.1f} req/s | {fmt_hms(s['elapsed'])}   ")
        sys.stdout.flush()


# --------------------------------------------------------------------------- #
# Parallel build engine
# --------------------------------------------------------------------------- #
class Builder:
    def __init__(self, *, workers: int, rate: float, delay: float, timeout: int,
                 max_retries: int, assets: bool, crawl: bool, max_pages: int | None):
        # If a per-request delay is given, fold it into the global rate as an upper bound.
        effective_rate = rate
        if delay and delay > 0:
            effective_rate = min(rate, workers / delay)
        self.workers = max(1, workers)
        self.pacer = Pacer(effective_rate)
        self.timeout = timeout
        self.max_retries = max_retries
        self.assets_enabled = assets
        self.crawl = crawl
        self.max_pages = max_pages
        self.stats = BuildStats()
        self.stop = threading.Event()
        self.q: "queue.Queue[tuple[str, str] | None]" = queue.Queue()
        self.seen: set[str] = set()
        self.seen_lock = threading.Lock()
        self.data_lock = threading.Lock()
        self.save_lock = threading.Lock()
        self.index = load_index(INDEX_PATH)
        self.asset_index = load_index(ASSET_INDEX_PATH)
        self._since_checkpoint = 0

    def _maybe_enqueue(self, kind: str, url: str) -> None:
        # Dedup within a run; the handler performs the (resume) skip check so that
        # already-cached pages are counted as skipped and reported accurately.
        with self.seen_lock:
            if url in self.seen:
                return
            self.seen.add(url)
        self.q.put((kind, url))
        if kind == "page":
            self.stats.inc("discovered")

    def _checkpoint(self, force: bool = False) -> None:
        with self.save_lock:
            self._since_checkpoint += 1
            if force or self._since_checkpoint >= CHECKPOINT_EVERY:
                self._since_checkpoint = 0
                with self.data_lock:
                    idx = dict(self.index)
                    aidx = dict(self.asset_index)
                save_index(idx, INDEX_PATH)
                save_index(aidx, ASSET_INDEX_PATH)

    def _handle_page(self, url: str) -> None:
        path = key_to_path(url)
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if url in self.index and path.exists():
            self.stats.inc("skipped")
            return
        if self.max_pages is not None and self.stats.saved_pages >= self.max_pages:
            self.stop.set()
            return
        ok, code, data = http_fetch(url, self.pacer, self.timeout, self.max_retries, self.stats, self.stop)
        if not ok:
            self.stats.add_failure(url, code)
            return
        text = data.decode("utf-8", errors="replace")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, "utf-8")
        with self.data_lock:
            self.index[url] = rel
        self.stats.inc("saved_pages")
        self.stats.inc("bytes", len(data))
        links, asset_urls = extract_links(text, url)
        if self.assets_enabled:
            for a in asset_urls:
                self._maybe_enqueue("asset", a)
        if self.crawl:
            for link in links:
                self._maybe_enqueue("page", link)
        if self.max_pages is not None and self.stats.saved_pages >= self.max_pages:
            self.stop.set()
        self._checkpoint()

    def _handle_asset(self, url: str) -> None:
        path = key_to_path(url, asset=True)
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if url in self.asset_index and path.exists():
            self.stats.inc("skipped")
            return
        ok, code, data = http_fetch(url, self.pacer, self.timeout, self.max_retries, self.stats, self.stop)
        if not ok:
            self.stats.add_failure(url, code)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        with self.data_lock:
            self.asset_index[url] = rel
        self.stats.inc("saved_assets")
        self.stats.inc("bytes", len(data))
        self._checkpoint()

    def _worker(self) -> None:
        while True:
            item = self.q.get()
            try:
                if item is None:
                    return
                if self.stop.is_set():
                    continue
                kind, url = item
                try:
                    if kind == "page":
                        self._handle_page(url)
                    else:
                        self._handle_asset(url)
                except Exception as exc:  # never let one URL kill a worker
                    self.stats.add_failure(url, -1)
                    sys.stderr.write(f"\nworker error on {url}: {type(exc).__name__}: {exc}\n")
            finally:
                self.q.task_done()

    def run(self, seeds: list[str]) -> BuildStats:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ASSET_DIR.mkdir(parents=True, exist_ok=True)
        for s in seeds:
            kind = "asset" if is_asset_url(s) else "page"
            self._maybe_enqueue(kind, s)

        threads = [threading.Thread(target=self._worker, daemon=True) for _ in range(self.workers)]
        for t in threads:
            t.start()
        total_target = len(seeds) if not self.crawl else None
        reporter = threading.Thread(target=progress_reporter,
                                    args=(self.stats, total_target, self.crawl, self.stop), daemon=True)
        reporter.start()
        try:
            self.q.join()
        except KeyboardInterrupt:
            sys.stderr.write("\nInterrupted - saving checkpoint and stopping cleanly...\n")
            self.stop.set()
            # drain quickly
            try:
                while True:
                    self.q.get_nowait()
                    self.q.task_done()
            except queue.Empty:
                pass
        finally:
            self.stop.set()
            for _ in threads:
                self.q.put(None)
            for t in threads:
                t.join(timeout=5)
            self._checkpoint(force=True)
        return self.stats


# --------------------------------------------------------------------------- #
# Estimate / dry-run
# --------------------------------------------------------------------------- #
def count_cached(urls: list[str], asset: bool = False) -> int:
    idx = load_index(ASSET_INDEX_PATH if asset else INDEX_PATH)
    n = 0
    for u in urls:
        if u in idx and (ROOT / idx[u]).exists():
            n += 1
    return n


def estimate(profile: str | None, mode: str | None, workers: int, rate: float, delay: float) -> None:
    print("=== Build estimate (dry run - nothing will be downloaded) ===")
    if profile == "db-only":
        print("Profile: db-only - builds the SQLite morphology DB only. No pages are downloaded.")
        print("Run: python -m quran_offline.import_morphology")
        return

    if profile:
        seeds, crawl = seeds_for_profile(profile)
        label = f"profile={profile}"
    else:
        seeds, crawl = page_list_for_mode(mode or "start"), (mode == "all")
        label = f"mode={mode}"

    db_present = DB_PATH.exists()
    page_seeds = [s for s in seeds if not is_asset_url(s)]
    cached = count_cached(page_seeds)
    remaining_pages = len(page_seeds) - cached

    # crawl/full target uses known full-mirror totals as an upper-bound estimate
    if crawl:
        target_pages = max(len(page_seeds), EXPECTED["full_pages"])
        target_assets = EXPECTED["full_assets"]
        remaining_assets = max(0, target_assets - count_cached([], asset=True))
        note = "full/crawl: pages discovered while crawling; totals are approximate."
    else:
        target_pages = len(page_seeds)
        target_assets = 0 if profile in {"core", "morphology"} else 0
        remaining_assets = 0
        note = "deterministic profile: shared assets are fetched as referenced (small)."

    effective_rate = rate if not (delay and delay > 0) else min(rate, workers / delay)
    # assume ~0.6s server latency per request; effective throughput is min(rate, workers/latency)
    throughput = min(effective_rate, workers / 0.6)
    total_remaining = remaining_pages + remaining_assets
    eta = total_remaining / throughput if throughput > 0 else 0
    disk = remaining_pages * AVG_PAGE_BYTES + remaining_assets * AVG_ASSET_BYTES

    print(f"Selected: {label}   (crawl={crawl})")
    if profile in {"core", "morphology", "full"} and not db_present:
        print("  ! Local DB not found - counts for dictionary/morphology use approximate totals.")
        if not crawl:
            target_pages = {"core": EXPECTED['verses'] * 2 + EXPECTED['roots'],
                            "morphology": EXPECTED['morphology']}.get(profile, target_pages)
            remaining_pages = target_pages - cached
            total_remaining = remaining_pages
            eta = total_remaining / throughput if throughput > 0 else 0
            disk = remaining_pages * AVG_PAGE_BYTES
    print(f"  Target pages:        ~{target_pages:,}")
    print(f"  Already cached:       {cached:,}")
    print(f"  Remaining pages:     ~{max(0, remaining_pages):,}")
    if crawl:
        print(f"  Target assets (approx):   ~{target_assets:,}")
    print(f"  Workers={workers}  global rate cap={effective_rate:.1f} req/s  assumed throughput ~= {throughput:.1f} req/s")
    print(f"  Estimated time:      ~{fmt_hms(eta)}  (assumes ~0.6s/request latency)")
    print(f"  Estimated new disk:  ~{disk / (1024*1024):.0f} MiB")
    print(f"  Note: {note}")
    print("  Will download: corpus.quran.com study pages + referenced assets for this profile.")
    print("  Will NOT download: login/messageboard/feedback, external domains, pdf/zip/jar.")


# --------------------------------------------------------------------------- #
# Build report
# --------------------------------------------------------------------------- #
def write_report(profile: str | None, mode: str | None, settings: dict, stats: BuildStats) -> Path:
    s = stats.snapshot()
    now = datetime.now()
    lines = []
    lines.append(f"# Offline cache build report\n")
    lines.append(f"- Date: {now.isoformat(timespec='seconds')}")
    lines.append(f"- Selection: profile={profile} mode={mode}")
    lines.append(f"- Settings: {json.dumps(settings)}")
    lines.append("")
    lines.append("## Results")
    lines.append(f"- Pages saved: {s['saved_pages']:,}")
    lines.append(f"- Assets saved: {s['saved_assets']:,}")
    lines.append(f"- Skipped (already cached): {s['skipped']:,}")
    lines.append(f"- Errors: {s['errors']:,}")
    lines.append(f"- Retries: {s['retries']:,}")
    lines.append(f"- Bytes downloaded: {s['bytes']:,} ({s['bytes']/(1024*1024):.1f} MiB)")
    lines.append(f"- Elapsed: {fmt_hms(s['elapsed'])}")
    lines.append(f"- Index entries now: {len(load_index(INDEX_PATH)):,}")
    lines.append(f"- Asset entries now: {len(load_index(ASSET_INDEX_PATH)):,}")
    if stats.failures:
        lines.append("")
        lines.append("## Failures (first 50)")
        for url, code in stats.failures[:50]:
            lines.append(f"- HTTP {code}: {url}")
    lines.append("")
    lines.append("Resume any time by re-running the same command; cached pages are skipped.")
    text = "\n".join(lines) + "\n"

    if CACHE_ROOT.exists():
        out = CACHE_ROOT / f"build-report-{now.strftime('%Y%m%d-%H%M%S')}.md"
    else:
        out = ROOT / "BUILD_REPORT.md"
    out.write_text(text, "utf-8")
    return out


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_db_only() -> int:
    if DB_PATH.exists():
        print(f"Database already present: {DB_PATH}")
        return 0
    print("Profile db-only: building SQLite morphology database (no page cache).")
    try:
        from . import import_morphology
        return import_morphology.main([])
    except Exception as exc:
        print(f"Could not build DB automatically: {exc}")
        print("Run manually: python -m quran_offline.import_morphology --input data/quranic-corpus-morphology-0.4.txt")
        return 1


def build(profile: str | None, mode: str | None, *, workers: int, rate: float, delay: float,
          timeout: int, max_retries: int, assets: bool, crawl_override: bool | None,
          max_pages: int | None) -> int:
    if profile == "db-only":
        return run_db_only()

    if profile:
        seeds, crawl = seeds_for_profile(profile)
    else:
        seeds, crawl = page_list_for_mode(mode or "start"), (mode == "all")
    if crawl_override is not None:
        crawl = crawl_override

    if profile in {"core", "morphology", "full"} and not DB_PATH.exists():
        print("NOTE: local DB not found. Dictionary/morphology URL lists are generated from the DB.")
        print("      Build it first:  python -m quran_offline.import_morphology")
        if profile in {"core", "morphology"} and not seeds:
            print("      No seeds without a DB for this profile. Aborting.")
            return 2

    print(f"Generated {len(seeds):,} seed URLs (profile={profile} mode={mode} crawl={crawl} "
          f"workers={workers} rate<= {rate} req/s).")
    if not seeds:
        print("No seeds generated. Nothing to do.")
        return 0

    builder = Builder(workers=workers, rate=rate, delay=delay, timeout=timeout,
                      max_retries=max_retries, assets=assets, crawl=crawl, max_pages=max_pages)
    stats = builder.run(seeds)
    s = stats.snapshot()
    print()  # newline after progress line
    print(f"Done. pages={s['saved_pages']:,} assets={s['saved_assets']:,} "
          f"skipped={s['skipped']:,} errors={s['errors']:,} retries={s['retries']:,} "
          f"in {fmt_hms(s['elapsed'])}.")
    settings = {"workers": workers, "rate": rate, "delay": delay, "timeout": timeout,
                "max_retries": max_retries, "assets": assets, "crawl": crawl, "max_pages": max_pages}
    report = write_report(profile, mode, settings, stats)
    print(f"Build report: {report}")
    if s["errors"]:
        print(f"{s['errors']:,} URLs failed (see report). Re-run the same command to retry just those.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a respectful, resumable, parallel offline cache of Quranic Arabic Corpus pages.")
    parser.add_argument("--profile", choices=PROFILES,
                        help="db-only | core | morphology | full. Recommended over --mode.")
    parser.add_argument("--mode", choices=["start", "verse-pages", "dictionary", "all"],
                        help="Legacy selection (kept for compatibility). 'all' ~= profile full (crawl).")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Parallel download workers (default {DEFAULT_WORKERS}). Keep it modest.")
    parser.add_argument("--rate-limit", "--rate", dest="rate", type=float, default=DEFAULT_RATE,
                        help=f"Max global requests/second (default {DEFAULT_RATE}).")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="Optional per-request delay; folded into the global rate as an upper bound.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Per-request timeout seconds.")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES,
                        help="Max retries per URL (exponential backoff). No infinite retries.")
    parser.add_argument("--max-pages", type=int, help="Safety cap on pages saved (for testing).")
    parser.add_argument("--no-crawl", action="store_true", help="Do not follow discovered links.")
    parser.add_argument("--crawl", action="store_true", help="Force link-following on.")
    parser.add_argument("--no-assets", action="store_true", help="Do not download images/CSS/JS assets.")
    parser.add_argument("--estimate", "--dry-run", dest="estimate", action="store_true",
                        help="Show the plan, counts, time and disk estimate. Download nothing.")
    args = parser.parse_args(argv)

    if args.workers < 1:
        parser.error("--workers must be >= 1")
    if args.profile is None and args.mode is None:
        args.mode = "start"  # backward-compatible default

    if args.estimate:
        estimate(args.profile, args.mode, args.workers, args.rate, args.delay)
        return 0

    crawl_override = None
    if args.no_crawl:
        crawl_override = False
    elif args.crawl:
        crawl_override = True

    return build(args.profile, args.mode, workers=args.workers, rate=args.rate, delay=args.delay,
                 timeout=args.timeout, max_retries=args.max_retries, assets=not args.no_assets,
                 crawl_override=crawl_override, max_pages=args.max_pages)


# Backward-compatible helper used by older scripts/tests.
def cache_pages(mode: str, max_pages: int | None, delay: float, crawl: bool, assets: bool) -> None:
    build(None, mode, workers=DEFAULT_WORKERS, rate=DEFAULT_RATE, delay=delay,
          timeout=DEFAULT_TIMEOUT, max_retries=DEFAULT_MAX_RETRIES, assets=assets,
          crawl_override=crawl, max_pages=max_pages)


if __name__ == "__main__":
    raise SystemExit(main())

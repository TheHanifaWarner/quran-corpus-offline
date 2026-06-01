"""Phase 4: respectful, throttled comparison of a small deterministic sample
against the live corpus.quran.com site.

Hard safety limits:
  * default sample is ~30 URLs, capped at 200
  * fixed 1.5s delay between live requests (configurable, min 1.0s)
  * one polite User-Agent, sequential requests only
  * read-only GET; writes nothing to cache/data

Usage:
    python -m quran_offline.audit_tools.online_compare [PORT] [--delay 1.5]
"""
from __future__ import annotations

import argparse
import difflib
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_INDEX = ROOT / "cache" / "index.json"
UA = "QuranCorpusOfflineArchiveAudit/1.0 (personal offline-mirror verification; low-volume)"
ARABIC = re.compile(r"[؀-ۿ]")

FALLBACK_URLS = [
    "https://corpus.quran.com/wordmorphology.jsp?location=%286%3A119%3A4%29",
    "https://corpus.quran.com/wordmorphology.jsp?location=%286%3A122%3A7%29",
    "https://corpus.quran.com/wordmorphology.jsp?location=%286%3A125%3A15%29",
    "https://corpus.quran.com/wordmorphology.jsp?location=%286%3A126%3A7%29",
    "https://corpus.quran.com/wordmorphology.jsp?location=%287%3A157%3A25%29",
]

AYAH = {1: 7, 2: 286, 57: 29, 114: 6}  # plus random ones filled below


def build_sample() -> list[tuple[str, str]]:
    rng = random.Random(42)
    # full ayah counts for random verse picking
    from quran_offline.surah_data import AYAH_COUNTS
    urls: list[tuple[str, str]] = []
    # first / middle / last word-by-word
    for c, v in [(1, 1), (57, 1), (114, 6)]:
        urls.append(("wordbyword", f"https://corpus.quran.com/wordbyword.jsp?chapter={c}&verse={v}"))
    # fixed-seed random verses across all surahs
    for _ in range(8):
        c = rng.randint(1, 114)
        v = rng.randint(1, AYAH_COUNTS[c])
        urls.append(("wordbyword-rand", f"https://corpus.quran.com/wordbyword.jsp?chapter={c}&verse={v}"))
    # translation pages
    for c, v in [(1, 1), (18, 10), (36, 1)]:
        urls.append(("translation", f"https://corpus.quran.com/translation.jsp?chapter={c}&verse={v}"))
    # exact word morphology (cached)
    urls.append(("wordmorphology-exact", "https://corpus.quran.com/wordmorphology.jsp?location=%281%3A1%3A1%29"))
    urls.append(("wordmorphology-exact", "https://corpus.quran.com/wordmorphology.jsp?location=%282%3A255%3A1%29"))
    # the 5 SQLite fallback morphology URLs
    for u in FALLBACK_URLS:
        urls.append(("wordmorphology-fallback", u))
    # dictionary, concept, grammar, treebank, documentation
    urls.append(("qurandictionary", "https://corpus.quran.com/qurandictionary.jsp?q=rHm"))
    urls.append(("concept", "https://corpus.quran.com/concept.jsp?id=adam"))
    urls.append(("grammar", "https://corpus.quran.com/grammar.jsp?chapter=1&verse=1&token=1"))
    urls.append(("treebank", "https://corpus.quran.com/treebank.jsp?chapter=1&verse=1"))
    urls.append(("documentation", "https://corpus.quran.com/documentation/tagset.jsp"))
    urls.append(("lemmas", "https://corpus.quran.com/lemmas.jsp"))
    urls.append(("verbs", "https://corpus.quran.com/verbs.jsp"))
    return urls


def visible_text(html: str) -> str:
    html = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;|&middot;|&mdash;|&amp;", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def title_of(html: str) -> str:
    m = re.search(r"(?is)<title>(.*?)</title>", html)
    return m.group(1).strip() if m else ""


def fetch(url: str, timeout: float = 25) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def local_cached(base: str, url: str) -> tuple[int, str]:
    full = base + "/cached?url=" + urllib.parse.quote(url, safe="")
    try:
        with urllib.request.urlopen(full, timeout=25) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("port", nargs="?", default="8799")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--max", type=int, default=200)
    args = ap.parse_args(argv)
    delay = max(1.0, args.delay)
    base = f"http://127.0.0.1:{args.port}"

    sample = build_sample()[: args.max]
    results = []
    live_requests = 0
    for kind, url in sample:
        l_status, l_body = local_cached(base, url)
        time.sleep(delay)
        o_status, o_body = fetch(url)
        live_requests += 1

        l_text = visible_text(l_body)
        o_text = visible_text(o_body)
        # strip offline banner phrase from local before comparison
        l_text_core = l_text.replace("Offline cached page from corpus.quran.com. Back to offline app", "")
        ratio = round(difflib.SequenceMatcher(None, o_text, l_text_core).ratio(), 4)
        rec = {
            "kind": kind,
            "url": url,
            "local_status": l_status,
            "online_status": o_status,
            "local_title": title_of(l_body),
            "online_title": title_of(o_body),
            "title_match": title_of(l_body) == title_of(o_body),
            "local_arabic": bool(ARABIC.search(l_body)),
            "online_arabic": bool(ARABIC.search(o_body)),
            "local_text_len": len(l_text_core),
            "online_text_len": len(o_text),
            "text_similarity": ratio,
            "local_is_fallback": "generated from" in l_body and "no internet request" in l_body,
        }
        results.append(rec)
        print(f"[{live_requests:>2}/{len(sample)}] {kind:24s} sim={ratio:<6} "
              f"L={l_status} O={o_status} titleEq={rec['title_match']} "
              f"fb={rec['local_is_fallback']}  {url.split('corpus.quran.com')[-1][:50]}")

    out = ROOT / "quran_offline" / "audit_tools" / "online_compare_results.json"
    out.write_text(json.dumps({"live_requests": live_requests, "delay_s": delay, "results": results}, indent=2, ensure_ascii=False), "utf-8")
    print(f"\nLive requests made: {live_requests}; results -> {out}")
    return 0


if __name__ == "__main__":
    import urllib.error
    raise SystemExit(main())

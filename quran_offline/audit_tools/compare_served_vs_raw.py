"""Phase 3: compare raw cached HTML vs locally served HTML.

For a deterministic sample of cached Corpus URLs, load the raw cached file
(via cache/index.json) and the server-rendered output from /cached, then
characterise every category of intentional offline rewrite. Read-only.

Usage:
    python -m quran_offline.audit_tools.compare_served_vs_raw [PORT]
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_INDEX = ROOT / "cache" / "index.json"

SAMPLE_URLS = [
    "https://corpus.quran.com/wordbyword.jsp?chapter=1&verse=1",
    "https://corpus.quran.com/wordbyword.jsp?chapter=2&verse=255",
    "https://corpus.quran.com/wordbyword.jsp?chapter=114&verse=6",
    "https://corpus.quran.com/translation.jsp?chapter=1&verse=1",
    "https://corpus.quran.com/grammar.jsp?chapter=1&verse=1&token=1",
    "https://corpus.quran.com/treebank.jsp?chapter=1&verse=1",
    "https://corpus.quran.com/qurandictionary.jsp?q=rHm",
    "https://corpus.quran.com/concept.jsp?id=adam",
    "https://corpus.quran.com/documentation/tagset.jsp",
    "https://corpus.quran.com/wordmorphology.jsp?location=%281%3A1%3A1%29",
]


class RefParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        for a in ("href", "src", "action", "srcset"):
            if a in d and d[a] is not None:
                self.refs.append((a, d[a]))


def active_remote(body: str) -> list[str]:
    out = []
    p = RefParser()
    p.feed(body)
    for attr, val in p.refs:
        v = (val or "").strip().lower()
        if not v or v.startswith(("#", "mailto:", "javascript:", "data:", "about:", "tel:")):
            continue
        pu = urllib.parse.urlparse(val)
        if pu.scheme in ("http", "https") and pu.hostname not in ("127.0.0.1", "localhost", None):
            out.append(val)
    # css url()
    for m in re.finditer(r"url\(\s*['\"]?(https?:)?//([^'\")]+)", body, re.I):
        out.append(m.group(0))
    return out


def get(base: str, url: str) -> tuple[int, str]:
    full = base + "/cached?url=" + urllib.parse.quote(url, safe="")
    with urllib.request.urlopen(full, timeout=20) as r:
        return r.status, r.read().decode("utf-8", "replace")


def classify(url: str, raw: str, served: str) -> dict:
    info = {"url": url, "raw_bytes": len(raw.encode("utf-8")), "served_bytes": len(served.encode("utf-8"))}
    info["banner_inserted"] = "Offline cached page from corpus.quran.com" in served
    info["base_in_raw"] = bool(re.search(r"<base\b", raw, re.I))
    info["base_in_served"] = bool(re.search(r"<base\b", served, re.I))
    info["refresh_in_raw"] = bool(re.search(r"http-equiv=[\"']?refresh", raw, re.I))
    info["refresh_neutralised"] = "data-offline-removed='refresh'" in served
    info["links_to_cached"] = len(re.findall(r"/cached\?url=", served))
    info["links_to_asset"] = len(re.findall(r"/asset\?url=", served))
    info["neutralised_external"] = len(re.findall(r"data-offline-(href|src|action|srcset)=", served))
    info["raw_external_refs"] = len(set(active_remote(raw)))
    info["served_active_remote"] = active_remote(served)
    # crude visible-text comparison: strip tags
    def text(s):
        s = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", s)
        s = re.sub(r"(?s)<[^>]+>", " ", s)
        return re.sub(r"\s+", " ", s).strip()
    rt, st = text(raw), text(served)
    # served has banner text prepended; strip the known banner phrase region
    st_core = st.replace("Offline cached page from corpus.quran.com. Back to offline app", "")
    info["raw_text_len"] = len(rt)
    info["served_text_len"] = len(st_core)
    # how much of raw text survives in served
    info["text_ratio"] = round(len(st_core) / max(1, len(rt)), 4)
    return info


def main(argv):
    port = argv[0] if argv else "8799"
    base = f"http://127.0.0.1:{port}"
    index = json.loads(CACHE_INDEX.read_text("utf-8"))

    def norm(u):
        pu = urllib.parse.urlparse(u)
        q = urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(pu.query, keep_blank_values=True)))
        return urllib.parse.urlunparse((pu.scheme, pu.netloc, pu.path, "", q, ""))

    results = []
    for url in SAMPLE_URLS:
        key = norm(url)
        rel = index.get(key)
        is_fallback = rel is None
        raw = (ROOT / rel).read_text("utf-8", "replace") if rel else "(no raw cache file — SQLite fallback)"
        status, served = get(base, url)
        info = classify(url, raw, served)
        info["http_status"] = status
        info["is_sqlite_fallback"] = is_fallback
        results.append(info)

    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

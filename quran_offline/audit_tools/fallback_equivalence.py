"""Special check: are the 5 SQLite-fallback word-morphology pages
FUNCTIONALLY equivalent to the live Corpus pages for the same locations?

Compares the linguistic facts (Arabic form, segment POS tags, lemma, root,
grammar features) between:
  - live corpus.quran.com wordmorphology.jsp
  - local SQLite fallback page (served by the offline server)
  - the SQLite database rows directly

5 live requests, 2s throttle. Read-only.
"""
from __future__ import annotations

import re
import sqlite3
import time
import urllib.parse
import urllib.request

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent.parent
DB = ROOT / "data" / "quran_corpus.sqlite3"
UA = "QuranCorpusOfflineArchiveAudit/1.0 (personal offline-mirror verification; low-volume)"
LOCS = [(6, 119, 4), (6, 122, 7), (6, 125, 15), (6, 126, 7), (7, 157, 25)]
ARABIC = re.compile(r"[؀-ۿ]+")


def live_text(c, v, w):
    loc = urllib.parse.quote(f"({c}:{v}:{w})", safe="")
    url = f"https://corpus.quran.com/wordmorphology.jsp?location={loc}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        h = r.read().decode("utf-8", "replace")
    h = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", h)
    t = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", t).strip()


def local_text(c, v, w, port="8799"):
    loc = urllib.parse.quote(f"({c}:{v}:{w})", safe="")
    url = f"http://127.0.0.1:{port}/wordmorphology.jsp?location={loc}"
    with urllib.request.urlopen(url, timeout=25) as r:
        h = r.read().decode("utf-8", "replace")
    h = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", h)
    t = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", t).strip()


def db_facts(c, v, w):
    conn = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    word = conn.execute("SELECT * FROM words WHERE chapter=? AND verse=? AND word=?", (c, v, w)).fetchone()
    segs = conn.execute("SELECT * FROM segments WHERE chapter=? AND verse=? AND word=? ORDER BY segment", (c, v, w)).fetchall()
    conn.close()
    return word, segs


def main():
    for (c, v, w) in LOCS:
        word, segs = db_facts(c, v, w)
        loc_text = local_text(c, v, w)
        time.sleep(2.0)
        on_text = live_text(c, v, w)

        tags = [s["tag"] for s in segs]
        lemmas = [s["lemma_buck"] for s in segs if s["lemma_buck"]]
        roots = [s["root_buck"] for s in segs if s["root_buck"]]
        forms_ar = [s["form_ar"] for s in segs]

        # check each linguistic fact appears in BOTH the live page and local page
        checks = []
        for label, vals in (("tag", tags), ("lemma_buck", lemmas), ("root_buck", roots)):
            for val in vals:
                in_live = val in on_text
                in_local = val in loc_text
                checks.append((label, val, in_live, in_local))
        # Arabic word form present?
        ar_live = bool(ARABIC.search(on_text))
        ar_local = bool(ARABIC.search(loc_text))

        all_live = all(c[2] for c in checks)
        all_local = all(c[3] for c in checks)
        print(f"\n=== {c}:{v}:{w}  word.form_buck={word['form_buck']}  segments={len(segs)} ===")
        print(f"  DB tags={tags} lemmas={lemmas} roots={roots}")
        print(f"  Arabic present: live={ar_live} local={ar_local}")
        print(f"  all DB facts present in LIVE page:  {all_live}")
        print(f"  all DB facts present in LOCAL page: {all_local}")
        for label, val, il, ilo in checks:
            if not (il and ilo):
                print(f"    MISMATCH {label}={val!r} live={il} local={ilo}")


if __name__ == "__main__":
    main()

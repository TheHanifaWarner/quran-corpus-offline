from __future__ import annotations

import html
import json
import os
import re
import sqlite3
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .buckwalter import buck_to_ar, normalize_query_to_buck, strip_buck_diacritics, strip_ar_diacritics
from .surah_data import AYAH_COUNTS, SURAH_BY_ID, SURAHS, TREEBANK_CHAPTERS

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "quran_corpus.sqlite3"
CACHE_INDEX = ROOT / "cache" / "index.json"
ASSET_INDEX = ROOT / "cache" / "assets.json"
ASSET_EXTS = (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico")
DYNAMIC_ASSET_PATHS = {"/wordimage"}
CSP = (
    "default-src 'self' data: blob:; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline' data:; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'none'; "
    "frame-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
TRANSPARENT_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
    b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01"
    b"\x00\x00\x02\x02D\x01\x00;"
)

POS_LABELS = {
    "N": "Noun", "PN": "Proper noun", "ADJ": "Adjective", "V": "Verb", "P": "Preposition",
    "DET": "Determiner", "PRON": "Personal pronoun", "DEM": "Demonstrative pronoun", "REL": "Relative pronoun",
    "T": "Time adverb", "LOC": "Location adverb", "CONJ": "Coordinating conjunction", "SUB": "Subordinating conjunction",
    "ACC": "Accusative particle", "AMD": "Amendment particle", "ANS": "Answer particle", "AVR": "Aversion particle",
    "CERT": "Particle of certainty", "COND": "Conditional particle", "EXP": "Exceptive particle", "EXH": "Exhortation particle",
    "EXL": "Explanation particle", "FUT": "Future particle", "INC": "Inceptive particle", "INT": "Particle of interpretation",
    "INTG": "Interrogative particle", "NEG": "Negative particle", "PRO": "Prohibition particle", "REM": "Resumption particle",
    "RES": "Restriction particle", "RET": "Retraction particle", "SUP": "Supplemental particle", "SUR": "Surprise particle",
    "VOC": "Vocative particle", "INL": "Quranic initials",
}

CSS = """
:root{--bg:#f8f5ef;--card:#fffdf8;--ink:#1d1b18;--muted:#6b6258;--line:#ded5c8;--accent:#73512e;--accent2:#9b7446}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,Arial,sans-serif}
a{color:#604016;text-decoration:none} a:hover{text-decoration:underline}.wrap{max-width:1200px;margin:0 auto;padding:20px}
header{border-bottom:1px solid var(--line);background:#fffaf0;position:sticky;top:0;z-index:4}nav{display:flex;gap:14px;align-items:center;flex-wrap:wrap}.brand{font-weight:800;font-size:18px;margin-right:8px}.pill{padding:6px 10px;border:1px solid var(--line);border-radius:999px;background:#fff}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin:14px 0;box-shadow:0 1px 2px #0000000d}.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}.forms{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;align-items:end}
label{display:block;font-size:13px;color:var(--muted);margin-bottom:4px}input,select,button{width:100%;padding:10px;border:1px solid var(--line);border-radius:10px;background:#fff;color:var(--ink)}button{background:var(--accent);color:#fff;font-weight:700;cursor:pointer}.small{font-size:13px}.arabic{font-family:"Traditional Arabic","Amiri","Scheherazade New",serif;direction:rtl;font-size:34px;line-height:1.9}.arabic-sm{font-family:"Traditional Arabic","Amiri","Scheherazade New",serif;direction:rtl;font-size:24px}.wordrow{display:grid;grid-template-columns:120px 1fr;gap:14px;border-top:1px solid var(--line);padding:14px 0}.badge{display:inline-block;padding:2px 7px;border:1px solid var(--line);border-radius:999px;background:#fff7e9;margin:2px;font-size:12px}.seg{padding:8px;border:1px solid var(--line);border-radius:10px;margin:6px 0;background:#fff}.table{width:100%;border-collapse:collapse;background:#fff}.table th,.table td{border-bottom:1px solid var(--line);padding:8px;vertical-align:top;text-align:left}.table th{background:#f2eadf}.rtl{text-align:right;direction:rtl}.code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:13px}.notice{border-left:5px solid var(--accent2);padding:12px;background:#fff8ea;border-radius:10px}.cacheframe{width:100%;min-height:75vh;border:1px solid var(--line);border-radius:12px;background:white}.topline{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
"""


def esc(x: Any) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def page(title: str, body: str) -> bytes:
    nav = """
<header><div class="wrap"><nav>
  <span class="brand">Quran Corpus Offline</span>
  <a class="pill" href="/">Reader</a>
  <a class="pill" href="/search">Morphological Search</a>
  <a class="pill" href="/dictionary">Dictionary</a>
  <a class="pill" href="/lemmas">Lemma Frequency</a>
  <a class="pill" href="/mirror">Exact Cached Corpus Pages</a>
  <a class="pill" href="/status">Status</a>
</nav></div></header>
"""
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(title)}</title><style>{CSS}</style></head><body>{nav}<main class='wrap'>{body}</main></body></html>".encode("utf-8")


def no_db_page() -> bytes:
    return page("Setup needed", f"""
    <h1>Setup needed</h1>
    <div class="notice">
      <p>The SQLite database is not built yet.</p>
      <p>Run one of these from this folder:</p>
      <pre class="code">python -m quran_offline.import_morphology</pre>
      <p>Or download the official <code>quranic-corpus-morphology-0.4.txt</code> from corpus.quran.com/download, then run:</p>
      <pre class="code">python -m quran_offline.import_morphology --input data/quranic-corpus-morphology-0.4.txt</pre>
    </div>
    """)


def get_query(path: str) -> tuple[str, dict[str, list[str]]]:
    parsed = urllib.parse.urlparse(path)
    return parsed.path, urllib.parse.parse_qs(parsed.query)


def selected_attr(a: Any, b: Any) -> str:
    return " selected" if str(a) == str(b) else ""


def verse_selector(c: int, v: int, endpoint: str = "/") -> str:
    surah_opts = "".join(f"<option value='{sid}'{selected_attr(sid,c)}>{sid}. {esc(tr)} — {esc(en)}</option>" for sid, tr, en, count in SURAHS)
    maxv = AYAH_COUNTS.get(c, 7)
    verse_opts = "".join(f"<option value='{i}'{selected_attr(i,v)}>{i}</option>" for i in range(1, maxv + 1))
    return f"""
    <form class="card forms" action="{endpoint}" method="get">
      <div><label>Surah</label><select name="c">{surah_opts}</select></div>
      <div><label>Ayah</label><select name="v">{verse_opts}</select></div>
      <div><button>Go</button></div>
    </form>"""


def render_reader(q: dict[str, list[str]]) -> bytes:
    if not DB_PATH.exists(): return no_db_page()
    c = int(q.get("c", [1])[0])
    v = int(q.get("v", [1])[0])
    with db() as conn:
        words = conn.execute("SELECT * FROM words WHERE chapter=? AND verse=? ORDER BY word", (c, v)).fetchall()
        segs = conn.execute("SELECT * FROM segments WHERE chapter=? AND verse=? ORDER BY word, segment", (c, v)).fetchall()
    by_word: dict[int, list[sqlite3.Row]] = {}
    for s in segs:
        by_word.setdefault(int(s["word"]), []).append(s)
    surah = SURAH_BY_ID.get(c, (c, "", "", 0))
    arabic_line = " ".join(w["form_ar"] for w in words)
    rows = []
    for w in words:
        wno = int(w["word"])
        seg_html = []
        for s in by_word.get(wno, []):
            label = POS_LABELS.get(s["tag"], s["tag"])
            root = f"<a href='/dictionary?root={urllib.parse.quote(s['root_buck'] or '')}'>{esc(s['root_ar'])}</a> <span class='code'>{esc(s['root_buck'])}</span>" if s["root_buck"] else "—"
            lemma = f"{esc(s['lemma_ar'])} <span class='code'>{esc(s['lemma_buck'])}</span>" if s["lemma_buck"] else "—"
            seg_html.append(f"""
              <div class="seg">
                <div><span class="arabic-sm">{esc(s['form_ar'])}</span> <span class="code">{esc(s['form_buck'])}</span></div>
                <div><span class="badge">{esc(s['tag'])} — {esc(label)}</span> <span class="badge">{esc(s['segment_type'])}</span></div>
                <div class="small"><b>Lemma:</b> {lemma} &nbsp; <b>Root:</b> {root}</div>
                <div class="small code muted">{esc(s['features'])}</div>
              </div>""")
        cached_links = f"""
        <p class="small muted">Exact Corpus cache links, if you ran the cache builder:
          <a href="/cached?url={urllib.parse.quote(f'https://corpus.quran.com/wordbyword.jsp?chapter={c}&verse={v}', safe='')}">Word by Word</a> ·
          <a href="/cached?url={urllib.parse.quote(f'https://corpus.quran.com/translation.jsp?chapter={c}&verse={v}', safe='')}">Translation</a> ·
          <a href="/cached?url={urllib.parse.quote(f'https://corpus.quran.com/grammar.jsp?chapter={c}&verse={v}&token={wno}', safe='')}">Grammar for this word</a>
        </p>"""
        rows.append(f"""
          <div class="wordrow">
            <div><div class="muted">({c}:{v}:{wno})</div><div class="arabic-sm">{esc(w['form_ar'])}</div><div class="code">{esc(w['form_buck'])}</div></div>
            <div><div><span class="badge">{esc(w['tag_chain'])}</span> <span class="badge">root {esc(w['root_ar'] or '—')}</span> <span class="badge">lemma {esc(w['lemma_ar'] or '—')}</span></div>{''.join(seg_html)}{cached_links}</div>
          </div>
        """)
    body = f"""
      <div class="topline"><h1>Verse ({c}:{v}) — {esc(surah[1])} / {esc(surah[2])}</h1><p class="muted">Offline DB reader generated from morphology data</p></div>
      {verse_selector(c, v)}
      <div class="card"><div class="arabic rtl">{esc(arabic_line)}</div></div>
      <div class="card"><h2>Word by word morphology</h2>{''.join(rows) if rows else '<p>No rows found. Check import.</p>'}</div>
    """
    return page(f"Verse {c}:{v}", body)


def render_search(q: dict[str, list[str]]) -> bytes:
    if not DB_PATH.exists(): return no_db_page()
    tag = q.get("tag", [""])[0].strip()
    root_raw = q.get("root", [""])[0].strip()
    lemma_raw = q.get("lemma", [""])[0].strip()
    form_raw = q.get("form", [""])[0].strip()
    feature = q.get("feature", [""])[0].strip().upper()
    params: list[Any] = []
    where = []
    if tag:
        where.append("tag = ?")
        params.append(tag)
    if root_raw:
        rb = strip_buck_diacritics(normalize_query_to_buck(root_raw))
        ra = strip_ar_diacritics(buck_to_ar(rb))
        where.append("(root_buck_plain = ? OR root_ar_plain = ?)")
        params.extend([rb, ra])
    if lemma_raw:
        lb = strip_buck_diacritics(normalize_query_to_buck(lemma_raw))
        la = strip_ar_diacritics(buck_to_ar(lb))
        where.append("(lemma_buck_plain = ? OR lemma_ar_plain = ?)")
        params.extend([lb, la])
    if form_raw:
        fb = strip_buck_diacritics(normalize_query_to_buck(form_raw))
        fa = strip_ar_diacritics(buck_to_ar(fb))
        where.append("(form_buck_plain LIKE ? OR form_ar_plain LIKE ?)")
        params.extend([f"%{fb}%", f"%{fa}%"])
    if feature:
        where.append("(features LIKE ? OR feature_flags LIKE ?)")
        params.extend([f"%{feature}%", f"%{feature}%"])
    sql = "SELECT * FROM segments"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY chapter, verse, word, segment LIMIT 500"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
        tags = [r[0] for r in conn.execute("SELECT DISTINCT tag FROM segments ORDER BY tag").fetchall()]
    tag_opts = "<option value=''>Any</option>" + "".join(f"<option value='{esc(t)}'{selected_attr(t,tag)}>{esc(t)} — {esc(POS_LABELS.get(t,''))}</option>" for t in tags)
    result_rows = []
    for r in rows:
        result_rows.append(f"""
        <tr><td><a href='/?c={r['chapter']}&v={r['verse']}'>({r['chapter']}:{r['verse']}:{r['word']}:{r['segment']})</a></td>
        <td class='rtl arabic-sm'>{esc(r['form_ar'])}</td><td class='code'>{esc(r['form_buck'])}</td><td>{esc(r['tag'])}</td>
        <td>{esc(r['lemma_ar'])}<br><span class='code muted'>{esc(r['lemma_buck'])}</span></td>
        <td><a href='/dictionary?root={urllib.parse.quote(r['root_buck'] or '')}'>{esc(r['root_ar'])}</a><br><span class='code muted'>{esc(r['root_buck'])}</span></td>
        <td class='code small'>{esc(r['features'])}</td></tr>""")
    body = f"""
    <h1>Morphological Search</h1>
    <p class="muted">Search by POS tag, root, lemma, stem/form, or raw morphology feature. Arabic or Buckwalter input both work for root/lemma/form.</p>
    <form class="card forms" method="get" action="/search">
      <div><label>Part of speech</label><select name="tag">{tag_opts}</select></div>
      <div><label>Root e.g. رحم or rHm</label><input name="root" value="{esc(root_raw)}"></div>
      <div><label>Lemma e.g. ٱللَّه or {{ll~ah</label><input name="lemma" value="{esc(lemma_raw)}"></div>
      <div><label>Stem/form contains</label><input name="form" value="{esc(form_raw)}"></div>
      <div><label>Feature contains e.g. FORM:II, GEN, M, PERF</label><input name="feature" value="{esc(feature)}"></div>
      <div><button>Search</button></div>
    </form>
    <div class="card"><h2>Results <span class="muted small">showing max 500</span></h2><table class="table"><tr><th>Location</th><th>Arabic</th><th>Buck</th><th>Tag</th><th>Lemma</th><th>Root</th><th>Features</th></tr>{''.join(result_rows) or '<tr><td colspan=7>No results</td></tr>'}</table></div>
    """
    return page("Morphological Search", body)


def render_dictionary(q: dict[str, list[str]]) -> bytes:
    if not DB_PATH.exists(): return no_db_page()
    root_raw = q.get("root", [""])[0].strip()
    with db() as conn:
        if not root_raw:
            roots = conn.execute("""
                SELECT root_buck, root_ar, COUNT(*) as n FROM segments
                WHERE root_buck IS NOT NULL AND root_buck != ''
                GROUP BY root_buck, root_ar ORDER BY root_buck_plain LIMIT 2000
            """).fetchall()
            root_links = " ".join(f"<a class='badge arabic-sm' href='/dictionary?root={urllib.parse.quote(r['root_buck'])}'>{esc(r['root_ar'])}</a>" for r in roots)
            body = f"<h1>Quran Dictionary</h1><div class='card'><form class='forms'><div><label>Root Arabic/Buckwalter</label><input name='root'></div><div><button>Open root</button></div></form></div><div class='card'><h2>Roots</h2>{root_links}</div>"
            return page("Dictionary", body)
        rb = strip_buck_diacritics(normalize_query_to_buck(root_raw))
        ra = strip_ar_diacritics(buck_to_ar(rb))
        rows = conn.execute("""
            SELECT w.chapter, w.verse, w.word, w.form_ar, w.form_buck, w.lemma_ar, w.lemma_buck, w.root_ar, w.root_buck, w.tag_chain
            FROM words w
            WHERE w.root_buck = ? OR w.root_ar = ? OR REPLACE(w.root_buck, '~', '') = ?
            ORDER BY w.chapter, w.verse, w.word
        """, (root_raw, root_raw, rb)).fetchall()
        if not rows:
            rows = conn.execute("""
                SELECT chapter, verse, word, form_ar, form_buck, lemma_ar, lemma_buck, root_ar, root_buck, tag_chain
                FROM words WHERE root_buck = ? OR root_ar = ? ORDER BY chapter, verse, word
            """, (normalize_query_to_buck(root_raw), buck_to_ar(normalize_query_to_buck(root_raw)))).fetchall()
    lemmas: dict[str, int] = {}
    for r in rows:
        key = f"{r['lemma_ar'] or ''} <span class='code'>{esc(r['lemma_buck'] or '')}</span>"
        lemmas[key] = lemmas.get(key, 0) + 1
    lemma_bits = " ".join(f"<span class='badge'>{k}: {n}</span>" for k, n in lemmas.items())
    result_rows = "".join(f"<tr><td><a href='/?c={r['chapter']}&v={r['verse']}'>({r['chapter']}:{r['verse']}:{r['word']})</a></td><td class='rtl arabic-sm'>{esc(r['form_ar'])}</td><td class='code'>{esc(r['form_buck'])}</td><td>{esc(r['tag_chain'])}</td><td>{esc(r['lemma_ar'])}<br><span class='code muted'>{esc(r['lemma_buck'])}</span></td></tr>" for r in rows)
    title_root = rows[0]["root_ar"] if rows else buck_to_ar(normalize_query_to_buck(root_raw))
    body = f"""
    <h1>Dictionary root <span class='arabic-sm'>{esc(title_root)}</span></h1>
    <div class="card"><form class="forms"><div><label>Root Arabic/Buckwalter</label><input name="root" value="{esc(root_raw)}"></div><div><button>Open root</button></div></form></div>
    <div class="card"><p><b>{len(rows)}</b> word occurrences.</p><p>{lemma_bits}</p></div>
    <div class="card"><table class="table"><tr><th>Location</th><th>Arabic</th><th>Buck</th><th>Tags</th><th>Lemma</th></tr>{result_rows or '<tr><td colspan=5>No root rows found</td></tr>'}</table></div>
    """
    return page("Dictionary", body)


def render_lemmas(q: dict[str, list[str]]) -> bytes:
    if not DB_PATH.exists(): return no_db_page()
    pos = q.get("pos", [""])[0].strip()
    with db() as conn:
        params=[]; where="WHERE lemma_buck IS NOT NULL AND lemma_buck != ''"
        if pos:
            where += " AND tag = ?"; params.append(pos)
        rows = conn.execute(f"""
            SELECT lemma_buck, lemma_ar, tag, COUNT(*) n FROM segments {where}
            GROUP BY lemma_buck, lemma_ar, tag ORDER BY n DESC, lemma_buck LIMIT 1000
        """, params).fetchall()
        tags = [r[0] for r in conn.execute("SELECT DISTINCT tag FROM segments ORDER BY tag").fetchall()]
    tag_opts = "<option value=''>Any</option>" + "".join(f"<option value='{esc(t)}'{selected_attr(t,pos)}>{esc(t)} — {esc(POS_LABELS.get(t,''))}</option>" for t in tags)
    trs="".join(f"<tr><td class='rtl arabic-sm'>{esc(r['lemma_ar'])}</td><td class='code'>{esc(r['lemma_buck'])}</td><td>{esc(r['tag'])}</td><td>{r['n']}</td><td><a href='/search?lemma={urllib.parse.quote(r['lemma_buck'])}'>search</a></td></tr>" for r in rows)
    body=f"""
    <h1>Lemma Frequency</h1><form class="card forms"><div><label>Part of speech</label><select name="pos">{tag_opts}</select></div><div><button>Filter</button></div></form>
    <div class="card"><table class="table"><tr><th>Lemma</th><th>Buckwalter</th><th>Tag</th><th>Frequency</th><th></th></tr>{trs}</table></div>
    """
    return page("Lemma Frequency", body)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists(): return {}
    return json.loads(path.read_text("utf-8"))


def normalise_corpus_url(url: str) -> str:
    """Canonicalise a Corpus URL for cache lookup.

    v3 was too literal: an empty URL became just '/', and relative
    Corpus links/forms could lose their page path. This version always
    resolves relative URLs against corpus.quran.com and sorts query params
    exactly like the cache builder did.
    """
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
    # Treat missing Corpus host as the Corpus host, because cached pages sometimes
    # submit relative forms back to /cached without a full url= parameter.
    netloc = parsed.netloc or "corpus.quran.com"
    scheme = parsed.scheme or "https"
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = urllib.parse.urlencode(sorted(query))
    return urllib.parse.urlunparse((scheme, netloc, parsed.path or "/", "", query, ""))


def merge_extra_query_into_url(base_url: str, q: dict[str, list[str]]) -> str:
    """If a cached Corpus form submits /cached?url=...&chapter=2&verse=1,
    merge those extra form fields back into the Corpus URL.
    """
    url = normalise_corpus_url(base_url)
    extras = {k: v[-1] for k, v in q.items() if k != "url" and v}
    if not extras:
        return url
    p = urllib.parse.urlparse(url)
    params = dict(urllib.parse.parse_qsl(p.query, keep_blank_values=True))
    for k, v in extras.items():
        if k not in {"_", "cache", "submit"}:
            params[k] = v
    query = urllib.parse.urlencode(sorted(params.items()))
    return urllib.parse.urlunparse((p.scheme, p.netloc, p.path or "/", "", query, ""))


def infer_corpus_page_from_referer(referer: str | None) -> str:
    """Work out which Corpus page type the user was on before a relative form submit.

    Example: if the user is on a cached translation page and a Corpus form submits
    only chapter/verse fields, keep them on translation.jsp instead of defaulting
    to the homepage.
    """
    if not referer:
        return "https://corpus.quran.com/wordbyword.jsp"
    try:
        rp = urllib.parse.urlparse(referer)
        rq = urllib.parse.parse_qs(rp.query)
        old_url = rq.get("url", [""])[0]
        old = urllib.parse.urlparse(normalise_corpus_url(old_url))
        if old.path and old.path != "/":
            return urllib.parse.urlunparse(("https", "corpus.quran.com", old.path, "", "", ""))
    except Exception:
        pass
    return "https://corpus.quran.com/wordbyword.jsp"


def rewrite_cached_html(raw: str, current_url: str) -> str:
    # Rewrite Corpus links/images/forms into local cache routes.
    # The key fix is resolving relative links against current_url, not only the
    # Corpus homepage. On the live site, ?chapter=2&verse=1 from translation.jsp
    # means translation.jsp?chapter=2&verse=1, not /?chapter=2&verse=1.
    def route_for(full: str) -> str:
        parsed = urllib.parse.urlparse(full)
        ext = Path(parsed.path).suffix.lower()
        route = "/asset" if ext in ASSET_EXTS or parsed.path in DYNAMIC_ASSET_PATHS else "/cached"
        return f'{route}?url={urllib.parse.quote(normalise_corpus_url(full), safe="")}'

    def repl_link_attr(m):
        attr, quote, val = m.group(1), m.group(2), html.unescape(m.group(3))
        if val.startswith("#") or val.startswith("mailto:") or val.startswith("javascript:"):
            return m.group(0)
        full = urllib.parse.urljoin(current_url, val)
        if urllib.parse.urlparse(full).netloc.endswith("corpus.quran.com"):
            return f'{attr}={quote}{route_for(full)}{quote}'
        if urllib.parse.urlparse(full).scheme in {"http", "https"}:
            safe_val = html.escape(val, quote=True)
            blocked = "#offline-external-reference" if attr != "action" else "/"
            return f'data-offline-{attr}={quote}{safe_val}{quote} {attr}={quote}{blocked}{quote}'
        return m.group(0)

    def repl_src(m):
        quote, src = m.group(1), html.unescape(m.group(2))
        full = urllib.parse.urljoin(current_url, src)
        if urllib.parse.urlparse(full).netloc.endswith("corpus.quran.com"):
            return f'src={quote}{route_for(full)}{quote}'
        if urllib.parse.urlparse(full).scheme in {"http", "https"}:
            safe_src = html.escape(src, quote=True)
            return f'data-offline-src={quote}{safe_src}{quote}'
        return m.group(0)

    def repl_srcset(m):
        quote, srcset = m.group(1), html.unescape(m.group(2))
        rewritten = []
        blocked = False
        for item in srcset.split(","):
            bits = item.strip().split()
            if not bits:
                continue
            full = urllib.parse.urljoin(current_url, bits[0])
            parsed = urllib.parse.urlparse(full)
            if parsed.netloc.endswith("corpus.quran.com"):
                bits[0] = route_for(full)
                rewritten.append(" ".join(bits))
            elif parsed.scheme in {"http", "https"}:
                blocked = True
            else:
                rewritten.append(" ".join(bits))
        if rewritten and not blocked:
            return f'srcset={quote}{html.escape(", ".join(rewritten), quote=True)}{quote}'
        return f'data-offline-srcset={quote}{html.escape(srcset, quote=True)}{quote}'

    raw = re.sub(r"\b(href|action)=([\"'])(.*?)[\"']", repl_link_attr, raw, flags=re.I)
    raw = re.sub(r"src=([\"'])(.*?)[\"']", repl_src, raw, flags=re.I)
    raw = re.sub(r"srcset=([\"'])(.*?)[\"']", repl_srcset, raw, flags=re.I)
    raw = re.sub(r"<base\b[^>]*>", "", raw, flags=re.I)
    raw = re.sub(r"<meta\b(?=[^>]*http-equiv=[\"']?refresh)[^>]*>", "<meta data-offline-removed='refresh'>", raw, flags=re.I)
    raw = re.sub(r"url\(\s*(['\"]?)(?:https?:)?//.*?\1\s*\)", "url('data:,')", raw, flags=re.I)
    return raw


def parse_word_location(url: str) -> tuple[int, int, int] | None:
    parsed = urllib.parse.urlparse(normalise_corpus_url(url))
    if not parsed.path.endswith("/wordmorphology.jsp"):
        return None
    loc = urllib.parse.parse_qs(parsed.query).get("location", [""])[0]
    loc = urllib.parse.unquote(loc).strip()
    m = re.fullmatch(r"\(?(\d+):(\d+):(\d+)\)?", loc)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def render_word_morphology_fallback(url: str) -> bytes | None:
    location = parse_word_location(url)
    if not location or not DB_PATH.exists():
        return None
    c, v, wno = location
    with db() as conn:
        word = conn.execute(
            "SELECT * FROM words WHERE chapter=? AND verse=? AND word=?",
            (c, v, wno),
        ).fetchone()
        segs = conn.execute(
            "SELECT * FROM segments WHERE chapter=? AND verse=? AND word=? ORDER BY segment",
            (c, v, wno),
        ).fetchall()
    if not word:
        return None

    seg_rows = []
    for s in segs:
        label = POS_LABELS.get(s["tag"], s["tag"])
        lemma = f"{esc(s['lemma_ar'])}<br><span class='code muted'>{esc(s['lemma_buck'])}</span>" if s["lemma_buck"] else "&mdash;"
        root = f"<a href='/dictionary?root={urllib.parse.quote(s['root_buck'] or '')}'>{esc(s['root_ar'])}</a><br><span class='code muted'>{esc(s['root_buck'])}</span>" if s["root_buck"] else "&mdash;"
        seg_rows.append(f"""
        <tr>
          <td>{esc(s['segment'])}</td>
          <td class="rtl arabic-sm">{esc(s['form_ar'])}</td>
          <td class="code">{esc(s['form_buck'])}</td>
          <td>{esc(s['tag'])}<br><span class="small muted">{esc(label)}</span></td>
          <td>{lemma}</td>
          <td>{root}</td>
          <td class="code small">{esc(s['features'])}</td>
        </tr>""")

    exact_url = normalise_corpus_url(url)
    grammar_url = f"https://corpus.quran.com/grammar.jsp?chapter={c}&verse={v}&token={wno}"
    wordbyword_url = f"https://corpus.quran.com/wordbyword.jsp?chapter={c}&verse={v}"
    body = f"""
    <h1>Word morphology ({c}:{v}:{wno})</h1>
    <div class="notice">
      <p>The exact cached Corpus HTML page for this word was not found locally.</p>
      <p>This fallback is generated from <code>data/quran_corpus.sqlite3</code>; no internet request was made.</p>
      <p class="code">{esc(exact_url)}</p>
    </div>
    <div class="card">
      <div class="arabic">{esc(word['form_ar'])}</div>
      <p><span class="badge">{esc(word['tag_chain'])}</span>
      <span class="badge">lemma {esc(word['lemma_ar'] or '-')}</span>
      <span class="badge">root {esc(word['root_ar'] or '-')}</span></p>
      <p class="small muted">
        <a href="/?c={c}&v={v}">Open local verse</a> &middot;
        <a href="/cached?url={urllib.parse.quote(wordbyword_url, safe='')}">Open cached Word by Word page</a> &middot;
        <a href="/cached?url={urllib.parse.quote(grammar_url, safe='')}">Open cached grammar page</a>
      </p>
    </div>
    <div class="card">
      <h2>Segments</h2>
      <table class="table">
        <tr><th>Segment</th><th>Arabic</th><th>Buckwalter</th><th>Tag</th><th>Lemma</th><th>Root</th><th>Features</th></tr>
        {''.join(seg_rows)}
      </table>
    </div>
    """
    return page(f"Word morphology {c}:{v}:{wno}", body)


def render_mirror(q: dict[str, list[str]]) -> bytes:
    index = load_json(CACHE_INDEX)
    n = len(index)
    sample = "https://corpus.quran.com/wordbyword.jsp?chapter=1&verse=1"
    body = f"""
    <h1>Exact cached Corpus pages</h1>
    <div class="notice"><p>This mode serves the real HTML pages downloaded from corpus.quran.com, rewritten for offline links. Build it once while online, then it works offline.</p>
    <pre class="code">python -m quran_offline.cache_corpus_pages --profile full</pre></div>
    <div class="card"><p>Cached pages found: <b>{n}</b></p>
    <p><a class="pill" href="/cached?url={urllib.parse.quote(sample, safe='')}">Open cached Word by Word 1:1</a></p>
    <p class="small muted">If a page says "not cached", verify the selected cache profile or build a broader cache with <code>--profile full</code>.</p></div>
    """
    return page("Cached Corpus", body)


def corpus_url_aliases(url: str) -> list[str]:
    """Return cache-key aliases for Corpus URLs that mean the same study page.

    The live site often links to the home path like
    https://corpus.quran.com/?chapter=3&verse=37. The cache builder stores the
    actual study pages, e.g. wordbyword.jsp?chapter=3&verse=37, so the offline
    server should resolve that homepage-style link instead of saying Not cached.
    """
    out = [normalise_corpus_url(url)]
    p = urllib.parse.urlparse(out[0])
    params = dict(urllib.parse.parse_qsl(p.query, keep_blank_values=True))
    chapter = params.get("chapter")
    verse = params.get("verse")
    token = params.get("token") or params.get("t") or "1"
    search_q = (params.get("q") or "").strip()
    verse_search = re.fullmatch(r"\s*(\d{1,3})\s*:\s*(\d{1,3})(?:\s*:\s*(\d{1,3}))?\s*", search_q)
    if verse_search:
        chapter = verse_search.group(1)
        verse = verse_search.group(2)
        token = verse_search.group(3) or token

    def add(u: str) -> None:
        nu = normalise_corpus_url(u)
        if nu not in out:
            out.append(nu)

    # Common Corpus homepage/search verse links. Prefer Word by Word because
    # that is closest to the normal Quran browsing page.
    if p.path in ("", "/") and chapter and verse:
        add(f"https://corpus.quran.com/wordbyword.jsp?chapter={chapter}&verse={verse}")
        add(f"https://corpus.quran.com/translation.jsp?chapter={chapter}&verse={verse}")
        add(f"https://corpus.quran.com/grammar.jsp?chapter={chapter}&verse={verse}&token={token}")
        add(f"https://corpus.quran.com/treebank.jsp?chapter={chapter}&verse={verse}")

    if p.path.endswith("/search.jsp") and verse_search and chapter and verse:
        add(f"https://corpus.quran.com/wordbyword.jsp?chapter={chapter}&verse={verse}")
        add(f"https://corpus.quran.com/translation.jsp?chapter={chapter}&verse={verse}")
        add(f"https://corpus.quran.com/grammar.jsp?chapter={chapter}&verse={verse}&token={token}")
        add(f"https://corpus.quran.com/treebank.jsp?chapter={chapter}&verse={verse}")

    # Some links use t= for token while generated/cached grammar pages may use token=.
    if p.path.endswith("/grammar.jsp") and chapter and verse:
        add(f"https://corpus.quran.com/grammar.jsp?chapter={chapter}&verse={verse}&token={token}")
        add(f"https://corpus.quran.com/grammar.jsp?chapter={chapter}&verse={verse}&t={token}")

    return out


def render_cached(q: dict[str, list[str]], referer: str | None = None) -> bytes:
    index = load_json(CACHE_INDEX)
    requested_url = q.get("url", [""])[0]

    # If a Corpus form/link submitted chapter/verse without url=, infer the page
    # type from the previous cached page. This fixes navigation inside cached
    # Translation/Word-by-Word pages.
    if not requested_url and any(k in q for k in ("chapter", "verse", "token", "t")):
        requested_url = infer_corpus_page_from_referer(referer)

    requested_url = merge_extra_query_into_url(requested_url, q)
    tried = corpus_url_aliases(requested_url)
    rel = None
    url = tried[0] if tried else normalise_corpus_url(requested_url)
    for candidate in tried:
        rel = index.get(candidate)
        if rel:
            url = candidate
            break
    if not rel:
        fallback = render_word_morphology_fallback(url)
        if fallback is not None:
            return fallback
        tried_html = "".join(f"<li class='code'>{esc(u)}</li>" for u in tried)
        return page("Not cached", f"<h1>Not cached</h1><p>This exact Corpus URL was not found in the local cache.</p><p><b>Requested:</b></p><p class='code'>{esc(normalise_corpus_url(requested_url))}</p><p><b>Also tried aliases:</b></p><ul>{tried_html}</ul><p>If the page should be available, verify the selected cache profile or run the relevant cache build command.</p>")
    p = ROOT / rel
    if not p.exists():
        return page("Missing cache file", f"<h1>Missing file</h1><p>{esc(str(p))}</p>")
    raw = p.read_text("utf-8", errors="replace")
    raw = rewrite_cached_html(raw, url)
    banner = f"<div style='background:#fff8da;border:1px solid #d2be88;padding:8px;font:14px system-ui'>Offline cached page from corpus.quran.com. <a href='/mirror'>Back to offline app</a> <span style='color:#666'>serving: {esc(url)}</span></div>"
    if "<body" in raw.lower():
        raw = re.sub(r"(<body[^>]*>)", r"\1" + banner, raw, count=1, flags=re.I)
    else:
        raw = banner + raw
    return raw.encode("utf-8")


def render_asset(q: dict[str, list[str]]) -> bytes | tuple[bytes, str]:
    assets = load_json(ASSET_INDEX)
    url = merge_extra_query_into_url(q.get("url", [""])[0], q)
    rel = assets.get(url)
    if not rel:
        return (b"", "image/gif")
    p = ROOT / rel
    ext = p.suffix.lower()
    if not p.exists():
        return b"", "application/octet-stream"
    if ext == ".css":
        text = p.read_text("utf-8", errors="replace")
        text = re.sub(r"url\(\s*(['\"]?)(?:https?:)?//.*?\1\s*\)", "url('data:,')", text, flags=re.I)
        return text.encode("utf-8"), "text/css; charset=utf-8"
    data = p.read_bytes()
    ctype = sniff_content_type(data, ext, urllib.parse.urlparse(url).path)
    return data, ctype


def sniff_content_type(data: bytes, ext: str, source_path: str = "") -> str:
    if ext == ".png" or data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if ext in (".jpg", ".jpeg") or data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if ext == ".gif" or data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if ext == ".svg" or data.lstrip().startswith(b"<svg"):
        return "image/svg+xml"
    if ext == ".js":
        return "application/javascript; charset=utf-8"
    if ext == ".html":
        return "text/html; charset=utf-8"
    if source_path in DYNAMIC_ASSET_PATHS:
        return "image/png"
    return "application/octet-stream"


def looks_like_corpus_cache_path(path: str) -> bool:
    if not path or path in {"/", "/cached", "/asset", "/status", "/mirror", "/search", "/dictionary", "/lemmas"}:
        return False
    ext = Path(path).suffix.lower()
    return (
        ext in ASSET_EXTS
        or path in DYNAMIC_ASSET_PATHS
        or ext in {".jsp", ".html", ".htm"}
        or path.startswith(("/documentation", "/java/", "/images/", "/css/", "/flash/"))
    )


def render_status() -> bytes:
    db_stats = "<p>Database: <b>missing</b></p>"
    if DB_PATH.exists():
        with db() as conn:
            meta = dict(conn.execute("SELECT key,value FROM meta").fetchall())
            db_stats = f"<p>Database: <b>present</b> - {esc(DB_PATH)}</p><p>Segments: {esc(meta.get('segment_count'))}; Words: {esc(meta.get('word_count'))}; Source: <span class='code'>{esc(meta.get('source_file'))}</span></p>"
    index = load_json(CACHE_INDEX)
    assets = load_json(ASSET_INDEX)
    body = f"""
    <h1>Status</h1><div class="card">{db_stats}<p>Cached Corpus HTML pages: <b>{len(index)}</b></p><p>Cached image assets: <b>{len(assets)}</b></p></div>
    <div class="card"><h2>Build commands</h2><pre class="code">python -m quran_offline.import_morphology
python -m quran_offline.cache_corpus_pages --profile full</pre></div>
    <div class="card"><h2>Coverage target</h2><ul><li>DB mode: all morphology-derived features from v0.4.</li><li>Exact page cache mode: Corpus Word by Word, Translation, Grammar, Treebank where present, Dictionary, Lemmas, Verb Concordance, Ontology/docs pages downloaded while online.</li></ul></div>
    """
    return page("Status", body)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path, q = get_query(self.path)
        try:
            if path == "/" and any(k in q for k in ("chapter", "verse", "token", "t")):
                data, ctype = render_cached(q, self.headers.get("Referer")), "text/html; charset=utf-8"
            elif path == "/": data, ctype = render_reader(q), "text/html; charset=utf-8"
            elif path == "/search": data, ctype = render_search(q), "text/html; charset=utf-8"
            elif path == "/dictionary": data, ctype = render_dictionary(q), "text/html; charset=utf-8"
            elif path == "/lemmas": data, ctype = render_lemmas(q), "text/html; charset=utf-8"
            elif path == "/mirror": data, ctype = render_mirror(q), "text/html; charset=utf-8"
            elif path == "/cached": data, ctype = render_cached(q, self.headers.get("Referer")), "text/html; charset=utf-8"
            elif path in ("/wordbyword.jsp", "/translation.jsp", "/grammar.jsp", "/treebank.jsp", "/qurandictionary.jsp", "/lemmas.jsp", "/verbs.jsp", "/morphologicalsearch.jsp", "/ontology.jsp", "/ontologyconcept.jsp"):
                # If a cached Corpus page submits/links directly to a Corpus JSP path, serve it from cache.
                corpus_url = "https://corpus.quran.com" + path
                q2 = dict(q); q2["url"] = [corpus_url]
                data, ctype = render_cached(q2, self.headers.get("Referer")), "text/html; charset=utf-8"
            elif path == "/asset":
                out = render_asset(q)
                data, ctype = out if isinstance(out, tuple) else (out, "application/octet-stream")
            elif path == "/status": data, ctype = render_status(), "text/html; charset=utf-8"
            elif path == "/graphimage":
                data, ctype = TRANSPARENT_GIF, "image/gif"
            elif looks_like_corpus_cache_path(path):
                corpus_url = "https://corpus.quran.com" + path
                q2 = dict(q); q2["url"] = [corpus_url]
                if Path(path).suffix.lower() in ASSET_EXTS or path in DYNAMIC_ASSET_PATHS:
                    out = render_asset(q2)
                    data, ctype = out if isinstance(out, tuple) else (out, "application/octet-stream")
                else:
                    data, ctype = render_cached(q2, self.headers.get("Referer")), "text/html; charset=utf-8"
            else:
                self.send_response(404); self.end_headers(); self.wfile.write(b"Not found"); return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            data = page("Error", f"<h1>Error</h1><pre class='code'>{esc(type(exc).__name__ + ': ' + str(exc))}</pre>")
            self.send_response(500); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(data)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Run the offline Quran Corpus local web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--open-path", default="/", help="Local path to open in the browser after startup.")
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    root_url = f"http://{args.host}:{args.port}/"
    open_path = args.open_path or "/"
    if not open_path.startswith("/"):
        open_path = "/" + open_path
    open_url = f"http://{args.host}:{args.port}{open_path}"
    print(f"Quran Corpus Offline running at {root_url}")
    if not args.no_browser:
        try: webbrowser.open(open_url)
        except Exception: pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

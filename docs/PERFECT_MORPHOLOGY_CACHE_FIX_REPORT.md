<!-- Scrubbed for public release: local machine paths replaced with <project-root>/<local-path>. -->

# Perfect Morphology Cache Fix Report

**Date:** 2026-06-01
**Project:** `<project-root>`
**Goal:** Cache the 5 missing **original** `wordmorphology.jsp` HTML pages and integrate them into the existing content-addressed cache, removing the last dependence on SQLite-generated fallback for morphology coverage.

**Outcome:** ✅ Success. Exact cached word-morphology pages went **77,424 → 77,429 / 77,429**. The SQLite fallback is no longer required for any morphology page. No unrelated cache/asset/database files were changed.

---

## 1. The 5 URLs fetched

All fetched once each, HTTP 200, validated as authentic Corpus morphology pages, with a respectful 2.0 s throttle between requests:

| # | Location | URL | Live status | Fetched bytes |
| --- | --- | --- | --- | --- |
| 1 | 6:119:4 | `https://corpus.quran.com/wordmorphology.jsp?location=%286%3A119%3A4%29` | 200 | 11,072 |
| 2 | 6:122:7 | `https://corpus.quran.com/wordmorphology.jsp?location=%286%3A122%3A7%29` | 200 | 10,578 |
| 3 | 6:125:15 | `https://corpus.quran.com/wordmorphology.jsp?location=%286%3A125%3A15%29` | 200 | 10,661 |
| 4 | 6:126:7 | `https://corpus.quran.com/wordmorphology.jsp?location=%286%3A126%3A7%29` | 200 | 10,369 |
| 5 | 7:157:25 | `https://corpus.quran.com/wordmorphology.jsp?location=%287%3A157%3A25%29` | 200 | 10,851 |

Every page returned the canonical title *"The Quranic Arabic Corpus - Word by Word Grammar, Syntax and Morphology of the Holy Quran"* and passed all validation checks (title marker, `<title>` present, location/morphology markers present, plausible size). Sizes are consistent with the neighbouring cached morphology pages (e.g. 1:1:1 = 10,640 bytes). **No fetch failed and no page had changed unexpectedly**, so the integration proceeded.

---

## 2. Content-addressing convention (verified before any change)

From `quran_offline/cache_corpus_pages.py`:
- **Index key** = `normalise_url(url)` → `urljoin` to `https://corpus.quran.com/`, force https, drop fragment, `parse_qsl(keep_blank_values=True)` → `urlencode(sorted(...))`.
- **File name** = `sha256(key.encode("utf-8")).hexdigest() + ".html"`, stored under `cache/pages/`.
- **File content** = `response.decode("utf-8", errors="replace")` written as UTF-8 (raw HTML; offline rewriting happens only at serve time).
- **index.json format** = `json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True)`, atomic `.tmp` → replace, no trailing newline.

This was confirmed empirically against existing entries (1:1:1, and the immediate neighbours 6:119:3 and 6:119:5) — `sha256(key)+".html"` matched the stored filename exactly in every case. The new pages were written with the **identical** decode/re-encode method, so they are byte-identical to what the original builder would have produced.

For the normalised key `…location=%286%3A119%3A4%29`, the builder's `normalise_url`, the server's lookup key, and the audit's `word_morphology_url(c,v,w)` all produce the **same** string, so the new entries are found by all three code paths.

---

## 3. Where each page was saved + index.json keys added

5 keys added, 0 removed, 0 existing mappings modified (verified by diff against the pre-edit backup):

| Index key (added) | Saved file |
| --- | --- |
| `https://corpus.quran.com/wordmorphology.jsp?location=%286%3A119%3A4%29` | `cache/pages/8d4289a0b7f25ad390cdd289723f8b51e7d5a748d0c67b5fcecb39d58869dbcd.html` |
| `https://corpus.quran.com/wordmorphology.jsp?location=%286%3A122%3A7%29` | `cache/pages/74201b33c41ccd0e9a156f3dd545857779f6793900398d466a263cb35bbf3d80.html` |
| `https://corpus.quran.com/wordmorphology.jsp?location=%286%3A125%3A15%29` | `cache/pages/7e712836591bdb4ee52a04c04b33c98e794b5871b80178b25f9aa4fb9f288f09.html` |
| `https://corpus.quran.com/wordmorphology.jsp?location=%286%3A126%3A7%29` | `cache/pages/2f9cc13faeb2ba9fd7eb7ee6061a8df0066d9448fd6450f4ea2217fbcf47972d.html` |
| `https://corpus.quran.com/wordmorphology.jsp?location=%287%3A157%3A25%29` | `cache/pages/bd3f83883e083e621776d4d175a68aad6b98c53689c4624de530dbf516082210.html` |

**Assets:** Each fetched page was scanned for referenced assets (`href`/`src` with asset extensions, plus all `src`). **0 referenced assets were missing** from `cache/assets.json` — every CSS/JS/image they use is already cached. Therefore `cache/assets/` and `cache/assets.json` were **not touched** (rule 5 satisfied: assets reused, not re-fetched).

---

## 4. Before / after exact morphology count

| Metric | Before | After |
| --- | --- | --- |
| Exact cached word morphology pages | **77,424 / 77,429** | **77,429 / 77,429** ✅ |
| Word morphology pages requiring SQLite fallback | 5 | **0** ✅ |
| `cache/index.json` mapped entries | 149,900 | 149,905 |
| `cache/pages` files on disk | 149,922 | 149,927 |
| `cache/assets.json` entries / files | 78,119 / 78,119 | 78,119 / 78,119 (unchanged) |
| SQLite counts (surahs/verses/words/segments/roots/lemmas) | 114 / 6,236 / 77,429 / 128,219 / 1,642 / 4,832 | identical (unchanged) |
| Orphan HTML files | 22 | 22 (unchanged, untouched) |

---

## 5. Commands run

```powershell
# Verify convention + confirm the 5 are absent (read-only)
python -m quran_offline.audit_tools.analyze_cache        # (context from prior audit)

# Back up the index before editing (REQUIRED)
copy cache\index.json cache\index.json.bak-before-morph-fix

# Pre-fix integrity snapshot
python -m quran_offline.audit_tools.snapshot_manifest before_fix

# Dry run: fetch + validate all 5, check assets, write NOTHING
python -m quran_offline.audit_tools.fetch_missing_morphology --delay 2.0

# Commit: fetch + validate + write 5 files + atomically update index.json
python -m quran_offline.audit_tools.fetch_missing_morphology --commit --delay 2.0

# Start server, confirm the 5 serve ORIGINAL cached HTML (not fallback)
python -m quran_offline.server --host 127.0.0.1 --port 8801 --no-browser

# Official audit
python -m quran_offline.audit_offline_archive

# Post-fix integrity snapshot + comparison
python -m quran_offline.audit_tools.snapshot_manifest after_fix
```

The integration tool fetches and validates all 5 pages **in memory first** and writes nothing unless every page passes — so a single failure aborts cleanly with no partial state. The full crawl / cache builder was **not** run.

**Total live requests to corpus.quran.com in this task:** 15 (5 dry-run + 5 commit + 5 served-vs-live verification), all sequential, 2.0 s apart, polite User-Agent. Far below any mass-crawl.

---

## 6. Audit output (after fix)

```
Offline Quran Corpus archive audit
=========================================

Facts:
  - cache/index.json: 149,905 mapped entries
  - cache/index.json: 149,927 files on disk, 22 orphan files
  - cache/assets.json: 78,119 mapped entries
  - cache/assets.json: 78,119 files on disk, 0 orphan files
  - SQLite counts: 114 surahs, 6,236 verses, 77,429 words, 128,219 segments, 1,642 roots, 4,832 lemmas
  - Word-by-word cached verse pages: 6,236/6,236
  - Translation cached verse pages: 6,236/6,236
  - Treebank cached pages for configured chapters: 2,345/2,345
  - Exact cached word morphology pages: 77,429/77,429      <-- was 77,424/77,429
  - Root dictionary cached pages: 1,642/1,642
  - Server smoke pages: 21; local linked resources checked: 982; Arabic word images checked: 21; deliberate not-cached diagnostics: 19

Warnings:
  - cache/index.json: 22 orphan files exist ...; leaving them untouched

Failures:
  - none
```

The previous warning *"5 word morphology pages require SQLite fallback"* is **gone**. The only remaining warning is the pre-existing, unrelated 22-orphan note.

---

## 7. Verification that the 5 now serve ORIGINAL cached HTML (not fallback)

Served locally via `http://127.0.0.1:8801/wordmorphology.jsp?location=...`:

| Location | HTTP | Served title | Fallback banner present? | Offline-cache banner present? |
| --- | --- | --- | --- | --- |
| 6:119:4 | 200 | *…Word by Word Grammar, Syntax and Morphology…* | **No** | Yes (served from `/cached`) |
| 6:122:7 | 200 | *…Word by Word Grammar, Syntax and Morphology…* | **No** | Yes |
| 6:125:15 | 200 | *…Word by Word Grammar, Syntax and Morphology…* | **No** | Yes |
| 6:126:7 | 200 | *…Word by Word Grammar, Syntax and Morphology…* | **No** | Yes |
| 7:157:25 | 200 | *…Word by Word Grammar, Syntax and Morphology…* | **No** | Yes |

The SQLite fallback page has the distinctive title *"Word morphology C:V:W"* and the text *"This fallback is generated from data/quran_corpus.sqlite3"* — **neither appears** for any of the 5 now. They serve the original Corpus HTML (rewritten for offline use, like every other cached page).

**Served-vs-live similarity (5 live comparison requests):**

| Location | Visible-text similarity vs live | Arabic present | Active external refs |
| --- | --- | --- | --- |
| 6:119:4 | 0.9799 | ✓ | 0 |
| 6:122:7 | 0.9754 | ✓ | 0 |
| 6:125:15 | 0.9758 | ✓ | 0 |
| 6:126:7 | 0.9730 | ✓ | 0 |
| 7:157:25 | 0.9795 | ✓ | 0 |

These now match the live site at ~0.97–0.98 (the same band as all other exact morphology pages), versus ~0.02–0.05 when they were fallback-rendered. **No broken local resources** (171 local refs resolved 200, 0 broken across the 5 pages) and **0 active external network references**.

---

## 8. Is the SQLite fallback now unused for these 5?

**Yes — for these 5 locations the SQLite fallback is now dormant.** The server's `render_cached` path finds each URL in `index.json` and serves the cached original HTML; `render_word_morphology_fallback` is only reached when a URL is **not** in the index, which is no longer the case for any of the 77,429 morphology locations.

**The fallback code was deliberately left in place** (per the task rule). Although the audit now proves all 77,429 exact pages exist, the fallback is a harmless safety net and removing it was explicitly out of scope. It is now exercised by zero morphology URLs.

---

## 9. Confirmation: no unrelated cache/database files changed

Before/after integrity snapshot comparison (`snapshot_manifest`):

| Target | Before → After | Verdict |
| --- | --- | --- |
| `cache/index.json` | 23,782,100 → 23,782,912 bytes | **CHANGED — expected** (+5 entries, +812 bytes) |
| `cache/pages` | 149,922 → 149,927 files; +54,678 bytes | **CHANGED — expected** (+5 new pages only) |
| `cache/assets.json` | 10,540,434 → 10,540,434 bytes | **UNCHANGED** |
| `cache/assets` | 78,119 → 78,119 files; same bytes | **UNCHANGED** |
| `data/quran_corpus.sqlite3` | 42,991,616 bytes, same mtime | **UNCHANGED** |
| `data/quranic-corpus-morphology-0.4.txt` | 6,309,503 bytes, same mtime | **UNCHANGED** |

- Index diff: **exactly +5 keys, 0 removed, 0 existing mappings modified**, file still fully sorted and in the same JSON format.
- The 22 orphan HTML files were **not** deleted or altered.
- Database content **not** modified.
- No existing cached page or asset was overwritten (the 5 target hashes did not previously exist on disk).
- Backup retained at `cache/index.json.bak-before-morph-fix` (pre-edit copy, as required).

---

## 10. Files added by this task

| Path | Purpose |
| --- | --- |
| `cache/pages/8d4289…dbcd.html` … `bd3f83…2210.html` (5 files) | The 5 newly cached original morphology pages |
| `cache/index.json.bak-before-morph-fix` | Required pre-edit backup of the index |
| `quran_offline/audit_tools/fetch_missing_morphology.py` | The transactional fetch+validate+integrate tool (dry-run by default) |
| `quran_offline/audit_tools/snapshots/before_fix.json`, `after_fix.json` | Integrity snapshots used for the proof in §9 |
| `PERFECT_MORPHOLOGY_CACHE_FIX_REPORT.md` | This report |

No production code (`server.py`, launchers, importer, builder) was modified.

---

## Bottom line

The offline archive now contains **all 77,429 original `wordmorphology.jsp` pages** as genuine cached Corpus HTML. The last five SQLite-fallback morphology pages have been replaced by their authentic originals, verified to serve correctly offline (no fallback layout, ~0.97–0.98 fidelity to live, no broken resources, no external references). Every unrelated cached page, asset, the 22 orphans, and the SQLite database remain byte-for-byte untouched. This closes the only non-original-HTML gap identified in `FINAL_1TO1_QURAN_CORPUS_AUDIT.md`.


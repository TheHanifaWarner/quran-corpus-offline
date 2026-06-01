<!-- Scrubbed for public release: local machine paths replaced with <project-root>/<local-path>. -->

# Offline Quran Corpus Audit

Date: 2026-05-31

This report summarizes the read-only offline archive audit after server hardening. No cache files were deleted, renamed, regenerated, or recrawled.

## Result

Pass. The archive is usable offline through the local server, with expected warnings only.

Run:

```powershell
python -m quran_offline.audit_offline_archive
```

## Final Audit Facts

- `cache/index.json`: 149,900 mapped entries.
- `cache/pages`: 149,922 HTML files on disk.
- `cache/assets.json`: 78,119 mapped entries.
- `cache/assets`: 78,119 files on disk.
- SQLite counts: 114 surahs, 6,236 verses, 77,429 words, 128,219 segments, 1,642 roots, 4,832 lemmas.
- Word-by-word cached verse pages: 6,236/6,236.
- Translation cached verse pages: 6,236/6,236.
- Treebank cached pages for configured chapters: 2,345/2,345.
- Exact cached word morphology pages: 77,424/77,429.
- Root dictionary cached pages: 1,642/1,642.
- `Run Offline Corpus.bat` opens the offline cached Corpus homepage at `http://127.0.0.1:8765/cached?url=https%3A%2F%2Fcorpus.quran.com%2F`.
- Windows launcher will not trigger morphology import/download because `data\quran_corpus.sqlite3` exists.
- Windows batch scripts checked: 3.
- Server smoke pages checked: 21.
- Local linked resources checked: 915.
- Arabic word images checked on `wordbyword.jsp?chapter=55&verse=5`: 21/21.
- Deliberate not-cached diagnostics observed: 12.
- Corpus search-box verse queries such as `3:6` and `56:4` resolve to cached word-by-word pages.

## Expected Warnings

- `cache/pages` contains 22 orphan HTML files. They were reported only and left untouched.
- Five exact `wordmorphology.jsp` cache pages are missing. They are now covered by SQLite fallback pages generated from `data\quran_corpus.sqlite3`.

## SQLite Fallback Word Morphology Locations

| Location | Corpus URL |
| --- | --- |
| `6:119:4` | `https://corpus.quran.com/wordmorphology.jsp?location=%286%3A119%3A4%29` |
| `6:122:7` | `https://corpus.quran.com/wordmorphology.jsp?location=%286%3A122%3A7%29` |
| `6:125:15` | `https://corpus.quran.com/wordmorphology.jsp?location=%286%3A125%3A15%29` |
| `6:126:7` | `https://corpus.quran.com/wordmorphology.jsp?location=%286%3A126%3A7%29` |
| `7:157:25` | `https://corpus.quran.com/wordmorphology.jsp?location=%287%3A157%3A25%29` |

## Hardening Implemented

- Direct Corpus-style local paths are routed through the local cache handler.
- Corpus search-box verse queries like `search.jsp?q=3:6` route to the cached verse page instead of a missing cached search URL.
- Dynamic Arabic word image URLs like `/wordimage?id=...` are routed through the local asset cache and served as PNG images.
- Missing word morphology pages fall back to SQLite without making network requests.
- Active external resource references are neutralized in served responses while raw cache files remain unchanged.
- A local Content Security Policy blocks network fetches from served pages.
- `/graphimage` is served locally as a placeholder so treebank pages do not produce broken local requests.

## Final Audit Output

```text
Offline Quran Corpus archive audit
=========================================

Facts:
  - cache/index.json: 149,900 mapped entries
  - cache/index.json: 149,922 files on disk, 22 orphan files
  - cache/assets.json: 78,119 mapped entries
  - cache/assets.json: 78,119 files on disk, 0 orphan files
  - SQLite counts: 114 surahs, 6,236 verses, 77,429 words, 128,219 segments, 1,642 roots, 4,832 lemmas
  - Word-by-word cached verse pages: 6,236/6,236
  - Translation cached verse pages: 6,236/6,236
  - Treebank cached pages for configured chapters: 2,345/2,345
  - Exact cached word morphology pages: 77,424/77,429
  - Root dictionary cached pages: 1,642/1,642
  - Windows launcher will not trigger morphology import/download because data\quran_corpus.sqlite3 exists
  - Windows batch scripts checked: 3
  - Server smoke pages: 21; local linked resources checked: 915; Arabic word images checked: 21; deliberate not-cached diagnostics: 12

Warnings:
  - cache/index.json: 22 orphan files exist in <project-root>\cache\pages; leaving them untouched
  - 5 word morphology pages require SQLite fallback; first missing: [(6, 119, 4), (6, 122, 7), (6, 125, 15), (6, 126, 7), (7, 157, 25)]

Failures:
  - none
```


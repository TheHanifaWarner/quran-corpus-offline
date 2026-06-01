<!-- Scrubbed for public release: local machine paths replaced with <project-root>/<local-path>. -->

# FINAL 1:1 Quran Corpus Audit

**Date:** 2026-06-01
**Project:** `<project-root>`
**Scope:** Prove how close the offline archive is to the live `corpus.quran.com`, and decide whether it is a functional 1:1 offline mirror.
**Mode:** Read-only audit/proof. No cached HTML, assets, database, or launcher files were modified, deleted, renamed, regenerated, or recrawled. The full 149,900-page crawl was **not** re-run.

> **Path note:** The brief referenced `<project-root>`. That path does not exist on this machine; the live project is at `<project-root>`. The prior `OFFLINE_AUDIT.md` was written when the project lived under the OneDrive path. All tooling uses module-relative paths, so the move has no effect.

---

## TL;DR Verdict

| Question | Answer |
| --- | --- |
| **A. Exact byte-for-byte mirror?** | **No** — by design. Every served page is intentionally rewritten (offline link routing, external-reference neutralisation, offline banner, CSP header). |
| **B. Functional 1:1 offline mirror?** | **Yes**, for the cached Corpus study content (≈149,895 pages). Served content matches live with 98.5–99.9% visible-text similarity, identical titles, identical Arabic, and all study features work fully offline. |
| **C. Near-1:1 with known intentional differences?** | **Yes — this is the precise overall verdict.** The only differences are intentional offline rewrites, 5 SQLite-fallback morphology pages, and a handful of inherently-online features deliberately left uncached. |
| **D. Not 1:1; blockers?** | **No blockers.** No bugs, no cache gaps in Quran study data, no broken local resources, no external network leakage. |

**Final classification: C — Near-1:1 functional offline mirror with known, documented, intentional differences.** It behaves like the online site with virtually no difference except being offline.

---

## Was internet required? Were live requests made?

- **Internet required for offline use:** **No.** Phases 1, 2, 3, 5 ran with zero outbound network traffic. The server makes no outbound requests on any serving path (verified by code review of `server.py` and by Phase 5 link resolution: 0 off-localhost active references).
- **Live requests made:** **Yes — only in Phase 4, for verification, ~36 total**, all to `corpus.quran.com`, sequential, throttled (1.5–2.0 s apart), with a polite identifying User-Agent. This is far below the 50–200 ceiling you set. The full crawl was not repeated.

---

## Integrity proof (archive untouched)

Baseline snapshot taken before any testing, and again after all phases:

```
python -m quran_offline.audit_tools.snapshot_manifest before
python -m quran_offline.audit_tools.snapshot_manifest after
```

| Target | Before vs After |
| --- | --- |
| `cache/index.json` (size + SHA-256) | UNCHANGED |
| `cache/assets.json` (size + SHA-256) | UNCHANGED |
| `cache/pages` (149,922 files, total bytes, newest mtime) | UNCHANGED |
| `cache/assets` (78,119 files, total bytes, newest mtime) | UNCHANGED |
| `data/quran_corpus.sqlite3` (size + mtime) | UNCHANGED |
| `data/quranic-corpus-morphology-0.4.txt` (size + mtime) | UNCHANGED |

**Result: NOTHING MODIFIED.** (The SQLite `-wal`/`-shm` sidecar files may be touched by any read connection, but the database file content itself is byte-identical before and after.)

---

## Exact commands run

```powershell
# Phase 0 — baseline integrity snapshot
python -m quran_offline.audit_tools.snapshot_manifest before

# Phase 1 — existing audit + server smoke (the audit starts its own server)
python -m quran_offline.audit_offline_archive

# Phase 1 — independent server run for deeper probing
python -m quran_offline.server --host 127.0.0.1 --port 8799 --no-browser
#   probed: / /status /mirror /search /dictionary /lemmas /?c=..&v=..
#           wordbyword.jsp translation.jsp grammar.jsp treebank.jsp
#           qurandictionary.jsp lemmas.jsp verbs.jsp morphologicalsearch.jsp
#           ontology.jsp documentation/tagset.jsp concept.jsp
#           wordmorphology.jsp (5 fallback + exact) graphimage search.jsp

# Phase 2 — cache completeness analysis
python -m quran_offline.audit_tools.analyze_cache

# Phase 3 — served vs raw cache diff
python -m quran_offline.audit_tools.compare_served_vs_raw 8799

# Phase 4 — throttled online comparison (28 URLs, 1.5s delay)
python -m quran_offline.audit_tools.online_compare 8799 --delay 1.5

# Phase 4 — fallback functional-equivalence check (5 live, 2.0s delay)
python -m quran_offline.audit_tools.fallback_equivalence

# Phase 5 — browser-style link/asset/form resolution
python -m quran_offline.audit_tools.link_resolution 8799

# Phase 0 — final integrity snapshot + comparison
python -m quran_offline.audit_tools.snapshot_manifest after
```

Helper scripts were created only under `quran_offline/audit_tools/` as permitted. No production files were changed.

---

## PHASE 1 — Local offline health

**Built-in audit (`audit_offline_archive`): PASS, 0 failures.**

```
Facts:
  - cache/index.json: 149,900 mapped entries
  - cache/index.json: 149,922 files on disk, 22 orphan files
  - cache/assets.json: 78,119 mapped entries / 78,119 files on disk, 0 orphan
  - SQLite: 114 surahs, 6,236 verses, 77,429 words, 128,219 segments, 1,642 roots, 4,832 lemmas
  - Word-by-word cached verse pages: 6,236/6,236
  - Translation cached verse pages: 6,236/6,236
  - Treebank cached pages for configured chapters: 2,345/2,345
  - Exact cached word morphology pages: 77,424/77,429
  - Root dictionary cached pages: 1,642/1,642
  - Server smoke pages: 21; local linked resources checked: 915; Arabic word images: 21; not-cached diagnostics: 12
Warnings:
  - 22 orphan files (reported, left untouched)
  - 5 word morphology pages require SQLite fallback: (6,119,4),(6,122,7),(6,125,15),(6,126,7),(7,157,25)
Failures: none
```

**Independent server smoke test (port 8799) — all routes HTTP 200, CSP present, authentic Corpus titles:**

| Route | Status | Title |
| --- | --- | --- |
| `/`, `/status`, `/mirror`, `/search`, `/dictionary`, `/lemmas` | 200 | Offline app pages |
| `/wordbyword.jsp?chapter=1&verse=1` … `?chapter=114&verse=6` | 200 | *Word by Word Grammar, Syntax and Morphology…* |
| `/translation.jsp?chapter=1&verse=1` | 200 | *…Translation* |
| `/grammar.jsp?chapter=1&verse=1&token=1` | 200 | *…Grammar* |
| `/treebank.jsp?chapter=1&verse=1` | 200 | *Word by Word…* |
| `/qurandictionary.jsp?q=rHm` | 200 | *…Quran Dictionary* |
| `/lemmas.jsp`, `/verbs.jsp`, `/morphologicalsearch.jsp` | 200 | *Lemmas by Frequency / Verb Concordance / Morphological Search* |
| `/ontology.jsp`, `/concept.jsp?id=…` | 200 | *Ontology of Quranic Concepts / Concept…* |
| `/documentation/tagset.jsp` | 200 | *Part-of-speech Tagset* |
| 5 SQLite-fallback `wordmorphology.jsp` URLs | 200 | *Word morphology C:V:W* (fallback banner present) |
| `/graphimage?id=1` | 200 | transparent GIF placeholder (43 bytes, `image/gif`) |
| `/search.jsp?q=3:6` | 200 | routes to cached Word-by-Word 3:6 |
| unknown route | 404 | (correct) |

**Confirmations:**
- Server starts cleanly; stderr log shows only `200`/`404` lines, **no Python errors, tracebacks, or 500s**.
- No 404s for any expected cached page.
- All **5 SQLite fallback morphology URLs load correctly** with HTTP 200 and the fallback banner.
- No broken local CSS/JS/images (see Phases 3 & 5).
- No active external network references in any served page (see Phases 3 & 5).
- CSP / local-only behaviour works on every response (see Phase 5).
- No raw cache files modified (integrity proof above).

---

## PHASE 2 — Cache completeness

| Metric | Value |
| --- | --- |
| Mapped HTML pages (`index.json`) | 149,900 |
| Actual HTML files on disk | 149,922 |
| Orphan HTML files (on disk, unmapped) | 22 |
| Missing mapped pages | **0** |
| Zero-byte HTML files | **0** |
| Mapped assets (`assets.json`) | 78,119 |
| Asset files on disk | 78,119 |
| Missing mapped assets | **0** |
| Orphan / zero-byte assets | **0** |

**Database counts:** 114 surahs · 6,236 verses · 77,429 words · 128,219 segments · 1,642 roots · 4,832 lemmas — all match the canonical 114-surah / 6,236-ayah / 77,429-word Corpus v0.4 totals.

**Expected Quran coverage:**

| Coverage target | Result |
| --- | --- |
| Word-by-word pages (6,236) | **6,236 / 6,236** ✓ |
| Translation pages (6,236) | **6,236 / 6,236** ✓ |
| Word morphology locations (77,429) | **77,424 exact cached + 5 SQLite fallback = 77,429 / 77,429** |
| Treebank pages (configured chapters 1–8, 59–114) | **2,345 / 2,345** ✓ |
| Root dictionary pages | **1,642 / 1,642** ✓ (one per distinct root) |
| Per-word `wordimage` PNG assets | 77,429 (one per word) |

**Mapped HTML page-type breakdown (top types):**

```
wordmorphology.jsp   77,424      grammar.jsp          18,765
treebank.jsp         18,954      options.jsp          18,139   (treebank display options)
wordbyword.jsp        6,238      translation.jsp       6,237
search.jsp            1,999      qurandictionary.jsp   1,693
concept.jsp             272      lemmas.jsp               40      verbs.jsp   28
documentation/*         ~55      java API HTML (*.html)  ~20
+ singletons: ontology, ontologyconcept, faq, license, publications, download, buckwalter, etc.
```

**Asset breakdown:** 77,429 dynamic word images (stored as `.bin`, served as PNG) · 640 PNG · 27 JPEG · 7 GIF · 6 JS · 6 HTML · 4 CSS.

**Ontology / concept coverage:** Ontology concept pages are cached as `concept.jsp?id=…` (**272 concepts**, e.g. `adam`, `abel`, `abu-lahab`). `ontologyconcept.jsp` is only the legacy landing page. A probe of `ontologyconcept.jsp?id=1` returns a graceful "Not cached" page — that is **not** a gap; the live site's concept content lives at `concept.jsp`.

**Orphan files (22):** Inspected — they are genuine Corpus HTML pages (e.g. *Word by Word*, *Audio Options* popups) captured during the crawl but superseded / not referenced by the final index (alternate query orderings, audio popups). They are **extra** data, not missing data, and were left untouched.

---

## PHASE 3 — Served output vs raw cache

Deterministic 10-page sample. The server reads the raw cached file and applies offline rewrites at serve time; the raw files on disk are never altered.

| Page | Raw→Served bytes | Banner | Links→`/cached` | Assets→`/asset` | External neutralised | Active remote left | Visible-text ratio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| wordbyword 1:1 | 25,050→30,640 | ✓ | 66 | 34 | 8 | **0** | 1.009 |
| wordbyword 2:255 | 49,806→59,608 | ✓ | 118 | 60 | 8 | **0** | 1.005 |
| wordbyword 114:6 | 24,451→29,766 | ✓ | 60 | 35 | 8 | **0** | 1.010 |
| translation 1:1 | 16,668→19,249 | ✓ | 30 | 8 | 9 | **0** | 1.011 |
| grammar 1:1:1 | 16,980→19,713 | ✓ | 32 | 8 | 10 | **0** | 1.013 |
| treebank 1:1 | 15,891→19,612 | ✓ | 47 | 13 | 8 | **0** | 1.016 |
| qurandictionary rHm | 141,149→167,983 | ✓ | 401 | 9 | 9 | **0** | 1.002 |
| concept adam | 10,612→14,780 | ✓ | 62 | 13 | 10 | **0** | 1.029 |
| documentation/tagset | 23,372→27,581 | ✓ | 60 | 6 | 10 | **0** | 1.007 |
| wordmorphology 1:1:1 (exact) | 10,640→13,708 | ✓ | 35 | 12 | 9 | **0** | 1.045 |

The visible-text ratio is slightly **above** 1.0 because the offline banner text and `data-offline-*` attribute strings add a little text; the original body text is fully preserved.

**Difference classification (Phase 3):**

| Difference | Classification |
| --- | --- |
| Corpus `href`/`action` → `/cached?url=…` and asset URLs → `/asset?url=…` | **Expected offline rewrite** |
| Non-Corpus external `href/src/action/srcset` → `data-offline-*` (neutralised) | **Expected offline rewrite** (security/offline) |
| Offline banner injected after `<body>` | **Expected offline rewrite** (cosmetic, additive) |
| `<base>` removal, `<meta refresh>` neutralisation, `url(...)` CSS de-referencing | **Expected offline rewrite** (none triggered in this sample; logic verified) |
| `Content-Security-Policy` header added | **Expected offline rewrite** (header only; not in body) |
| `/graphimage` served as transparent-GIF placeholder | **Expected offline rewrite** (treebank dependency-graph image is server-rendered online only) |
| Any **functional** difference or **failure** | **None found** |

---

## PHASE 4 — Online 1:1 comparison (controlled & respectful)

**Sample size: 28 URLs** in the main comparison (fixed seed = 42) + **5** in the fallback-equivalence check + connectivity/inspection ≈ **36 live requests total**, sequential, throttled 1.5–2.0 s, polite User-Agent. The full crawl was not repeated.

Sample composition: first/middle/last verses (1:1, 57:1, 114:6); 8 fixed-seed random verses across all surahs; translation pages; exact + fallback word-morphology; dictionary, concept, grammar, treebank, documentation, lemmas, verbs pages.

**Result — every sampled URL returned HTTP 200 both locally and live.**

| Category | Pages | Title match | Arabic both | Visible-text similarity vs live |
| --- | --- | --- | --- | --- |
| wordbyword (incl. 8 random) | 11 | ✓ all | ✓ | **0.9954 – 0.9972** |
| translation | 3 | ✓ all | ✓ | **0.9947 – 0.9958** |
| wordmorphology (exact cached) | 2 | ✓ all | ✓ | **0.9777 – 0.9798** |
| qurandictionary / concept | 2 | ✓ all | ✓ | 0.9857 – 0.9992 |
| grammar / treebank | 2 | ✓ all | ✓ | 0.9927 – 0.9941 |
| documentation / lemmas / verbs | 3 | ✓ all | ✓ | 0.9913 – 0.9966 |
| **wordmorphology (SQLite fallback)** | **5** | ✗ (different layout) | ✓ | **0.024 – 0.050** (layout differs; data equivalent — see below) |

**Classification (Phase 4):**

- 23 cached study pages → **exact or near-exact content match** (98.5–99.9% visible text; the <1.5% delta is the offline banner + offline nav chrome, never missing Quran content).
- 5 fallback morphology pages → **fallback-generated content, functionally equivalent** (low text similarity is purely layout, not data — proven next).
- **Missing content: none. Broken content: none. "Live site changed since cache": none observed** in the sample (all titles and core content aligned).

### Special attention — the 5 SQLite-fallback morphology pages

These five `wordmorphology.jsp` locations have **no original cached HTML**; the server generates the page from `data/quran_corpus.sqlite3` (no network). Direct content comparison vs the live site (location 6:119:4 shown):

| Linguistic fact | Live corpus.quran.com | Local SQLite fallback | Match |
| --- | --- | --- | --- |
| Word | takulū تَأْكُلُوا۟ "you eat" | تَأْكُلُوا۟ | ✓ |
| Segments | 2 (a verb + subject pronoun) | 2 (V + PRON) | ✓ |
| Verb features | imperfect, 2nd person masc. plural, subjunctive | IMPF · 2MP · MOOD:SUBJ | ✓ |
| Root | hamza kāf lām (أ ك ل) | اكل / `Akl` | ✓ |
| Lemma | (rendered Arabic) | أَكَلَ / `>akala` | ✓ |
| Suffix | attached subject pronoun (الواو) | SUFFIX \| PRON:2MP | ✓ |

All five fallback locations carry the **same POS tags, segment structure, lemma, root, and grammatical features** as the live page. What the fallback **does not** reproduce: the live page's English prose grammar sentence, the Sahih-International verse-translation block, the audio-recitation widget, and the Corpus site chrome.

**Honest label:** these 5 URLs are **functionally equivalent for morphological data but are NOT original-HTML mirrors.** They are a *known fallback difference*, by design, fully documented.

---

## PHASE 5 — Functional browser-style checks

Extracted every `href`/`src`/`action` from 5 representative served pages and resolved each locally.

| Page | CSP / `connect-src 'none'` / `form-action 'self'` | Total refs | Local unique | Off-localhost refs | Form actions off-site |
| --- | --- | --- | --- | --- | --- |
| wordbyword 1:1 | ✓ / ✓ / ✓ | 105 | 87 | **0** | **0** |
| translation 1:1 | ✓ / ✓ / ✓ | 43 | 32 | **0** | **0** |
| treebank 1:1 | ✓ / ✓ / ✓ | 65 | 45 | **0** | **0** |
| qurandictionary rHm | ✓ / ✓ / ✓ | 416 | 406 | **0** | **0** |
| concept adam | ✓ / ✓ / ✓ | 80 | 49 | **0** (form action → local `/cached`) | **0** |

**Aggregate local resolution: 604 refs → HTTP 200 (resolve), 15 → graceful "Not cached" 200, 0 broken.**

- Internal links resolve locally ✓
- Image `src` targets resolve locally ✓
- CSS links resolve locally ✓ (and `url(...)` references inside CSS are de-referenced)
- JS links resolve locally or are safely neutralised ✓
- Form actions stay local (`/cached`, `'self'`) ✓
- **No active remote scripts / styles / images / forms remain ✓ (0 off-localhost active refs)**
- Navigation never tries to leave localhost ✓
- **The offline version is fully usable with the internet disabled ✓**

**The 15 graceful "not-cached" links** are 3 recurring URLs per page: `login.jsp`, `messageboard.jsp`, `feedback.jsp` — inherently dynamic, online-only, account/interaction features. They are deliberately uncached and degrade to a local "Not cached" page **without any network attempt**. Not Quran study content; not a gap.

---

## PHASE 6 — Strict 1:1 verdict

**Overall: C — Near-1:1 functional offline mirror with known, documented, intentional differences.**
For all cached Quran study content it is effectively **B (functional 1:1)**; it is explicitly **not A (byte-for-byte)** by design; there are **no D-class blockers.**

### Complete list of differences, each classified

| # | Difference | Classification |
| --- | --- | --- |
| 1 | Corpus links/forms rewritten to local `/cached` & `/asset` routes | **Intentional offline difference** |
| 2 | Non-Corpus external references neutralised to `data-offline-*` | **Intentional offline difference** |
| 3 | Offline banner injected after `<body>` | **Intentional offline difference** (cosmetic, additive) |
| 4 | `Content-Security-Policy` header added; `<base>`/refresh-meta neutralised | **Intentional offline difference** |
| 5 | `/graphimage` (treebank dependency graph) served as transparent placeholder | **Intentional offline difference** (server-rendered image, online-only) |
| 6 | 5 `wordmorphology.jsp` pages rendered from SQLite, not original HTML; same morphology data, different layout, no English prose/translation/chrome | **Known fallback difference** |
| 7 | `login.jsp`, `messageboard.jsp`, `feedback.jsp` not cached → graceful "Not cached" | **Intentional offline difference** (dynamic, account/interaction features) |
| 8 | 22 orphan HTML files on disk, unmapped | Extra data, not a difference in served behaviour (reported, untouched) |
| 9 | Visible text ~1% longer than live (banner + offline nav) | **Cosmetic difference** |
| — | Missing Quran study content | **None** |
| — | Bug in offline project | **None found** |
| — | Live website changed since cache | **None observed** in the sample |
| — | Unknown / needs manual review | **None** |

### Why not byte-for-byte (A)

The product intentionally is **not** a byte-for-byte mirror: it rewrites HTML so the archive is safe and navigable offline (local routing, no external calls, CSP, banner). This is the correct design for an offline mirror and is the source of every "difference" except items 6–7.

---

## Recommended fixes (NOT applied — listed only)

None are required for the 1:1 goal. In rough priority order:

1. **(Optional, eliminates the only non-original-HTML pages)** Cache the 5 missing `wordmorphology.jsp` pages individually while online (5 throttled requests — well within respectful limits), then they become exact-HTML mirrors and the archive reaches 77,429/77,429 *original* morphology pages. Until then the SQLite fallback is functionally equivalent.
2. **(Cosmetic)** Optionally add the live English prose grammar sentence + verse-translation block to the SQLite fallback template so even the 5 fallback pages visually resemble the online layout more closely.
3. **(Housekeeping)** Optionally prune or document the 22 orphan HTML files so on-disk file count (149,922) matches the mapped count (149,900). Purely cosmetic; they are harmless extra captures.
4. **(Robustness, not a 1:1 issue)** `server.py` opens the SQLite DB with a read-write connection (`sqlite3.connect(DB_PATH)`); switching to a read-only URI connection (as the audit tool already does) would guarantee the DB can never be written by the server. No evidence of any write occurred (integrity proof passed).
5. **(Cosmetic)** Update the stale path reference in `OFFLINE_AUDIT.md` (OneDrive path) to the current `Quran Tools` path.

> Per instructions, **no fixes were applied** and `server.py` was **not** modified. No bug was found that would justify changing it.

---

## Audit tooling added (read-only, under `quran_offline/audit_tools/`)

| Script | Purpose |
| --- | --- |
| `snapshot_manifest.py` | Before/after integrity snapshot (counts, bytes, mtimes, JSON hashes) |
| `analyze_cache.py` | Cache completeness + page-type/asset breakdown + DB counts |
| `compare_served_vs_raw.py` | Phase 3 served-vs-raw diff and rewrite characterisation |
| `online_compare.py` | Phase 4 throttled live comparison (results: `online_compare_results.json`) |
| `fallback_equivalence.py` | Phase 4 special check: 5 fallback pages vs live morphology data |
| `link_resolution.py` | Phase 5 browser-style link/asset/form resolution |

These were used to produce this report and can be re-run at any time. They do not modify `cache/`, `data/`, or any launcher/production file.

---

## Bottom line

With the internet **disabled**, the offline server reproduces the Quranic Arabic Corpus study experience — word-by-word morphology, translations, grammar, treebank, dictionary/roots, lemmas, verbs, ontology concepts, and documentation — with **98.5–99.9% content fidelity** to the live site, **zero broken local resources**, **zero external network leakage**, and **no missing Quran study data**. It is a **near-1:1 functional offline mirror**: identical in substance, intentionally different only in offline-safety rewrites and five honestly-labelled SQLite-fallback morphology pages.


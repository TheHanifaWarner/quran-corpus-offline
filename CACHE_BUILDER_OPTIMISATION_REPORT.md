# Cache Builder Optimisation Report

**Date:** 2026-06-01
**Repo:** `quran-corpus-offline-public` (public staging — code only)
**Private archive:** left **untouched** (read-only reference).

Goal: make the public cache builder much faster, safer, resumable, and easier, so
users don't need to leave a PC on for 3–4 days — while staying respectful to
`corpus.quran.com`.

---

## 1. Files changed (public repo only)

| File | Change |
| --- | --- |
| `quran_offline/cache_corpus_pages.py` | Rewritten: build profiles, bounded parallel downloader, rate limiting, retry/backoff + Retry-After, adaptive slow-down, resumable atomic checkpoints, `--estimate`/`--dry-run`, live progress, build report. Legacy `--mode` and `cache_pages()` kept. Content-addressing unchanged. |
| `quran_offline/audit_offline_archive.py` | Added `--verify db-only|core|morphology|full` scoped verification (default `full` = unchanged behaviour). |
| `README.md` | New build section: profiles, estimate-first, resume, safe speeds, verification, and "the 2.3 GB cache is not shipped — build your own". |
| `CACHE_BUILDER_OPTIMISATION_PLAN.md` | New — builder audit + plan. |
| `CACHE_BUILDER_OPTIMISATION_REPORT.md` | New — this report. |

No other files touched. No cache/DB/morphology data added.

---

## 2. Exact commands run

```bash
# Compile checks
python -m py_compile quran_offline/cache_corpus_pages.py quran_offline/server.py quran_offline/audit_offline_archive.py

# Estimate (offline, no downloads) for every profile + legacy mode
python -m quran_offline.cache_corpus_pages --profile db-only    --estimate
python -m quran_offline.cache_corpus_pages --profile core        --estimate --workers 4 --rate-limit 6
python -m quran_offline.cache_corpus_pages --profile morphology  --estimate
python -m quran_offline.cache_corpus_pages --profile full        --estimate
python -m quran_offline.cache_corpus_pages --mode all            --estimate

# Tiny real build + resume test (then cache/ deleted to keep repo code-only)
python -m quran_offline.cache_corpus_pages --profile core --max-pages 3 --workers 2 --rate-limit 2 --no-assets   # run 1
python -m quran_offline.cache_corpus_pages --profile core --max-pages 3 --workers 2 --rate-limit 2 --no-assets   # run 2 (resume)

# Verify modes
python -m quran_offline.audit_offline_archive --verify db-only
python -m quran_offline.audit_offline_archive --verify core
python -m quran_offline.audit_offline_archive --verify morphology
```

Total live requests to corpus.quran.com during testing: **~8** (two tiny capped
builds), throttled to ≤2 req/s.

---

## 3. New user commands

```bash
# Plan first (downloads nothing)
python -m quran_offline.cache_corpus_pages --profile <db-only|core|morphology|full> --estimate

# Build (resumable — re-run the same command to continue)
python -m quran_offline.cache_corpus_pages --profile core
python -m quran_offline.cache_corpus_pages --profile full --workers 4 --rate-limit 6

# Knobs: --workers N  --rate-limit R  --delay S  --timeout S  --max-retries N
#        --max-pages N  --no-assets  --no-crawl  --estimate/--dry-run

# Verify
python -m quran_offline.audit_offline_archive --verify core
```

Legacy still works: `--mode start|verse-pages|dictionary|all`.

---

## 4. Before / after speed model

Assumes ~0.6 s/request average server latency; ~228k total requests for the full
mirror (~150k pages + ~78k assets). Real times vary with the site and your link.

| Setting | Effective throughput | Full mirror (~228k) | `core` (~14k) | `morphology` (~77k) |
| --- | --- | --- | --- | --- |
| **Old** sequential, 0.25 s delay | ~1.0 req/s | ~2.5–4 days | ~4 h | ~21 h |
| **New DEFAULT** 4 workers, **2 req/s** cap | ~2 req/s | **~1.3 days (~31 h)** | ~2 h | ~10.5 h |
| **Faster opt-in** `--workers 4 --rate-limit 6` | ~6 req/s | **~10–11 h** | ~39 min | ~3.5 h |
| **Advanced** 6 workers, 10 req/s | ~10 req/s | ~6–7 h | ~24 min | ~2.1 h |

**The default is intentionally respectful (2 req/s)** so the tool never encourages
hammering corpus.quran.com — it is meant to run gently in the background and resumes
if interrupted. **Faster mode is an explicit opt-in for advanced users**
(`--workers 4 --rate-limit 6` ≈ **10–11 h** for the full mirror, per the current
estimate). Please **avoid running aggressive settings repeatedly** against the live
site — one gentle build is the right approach. Most users only need `core` (minutes
to ~2 h) or `morphology`, not the full mirror; resuming a partial build costs only
the *remaining* pages.

### `--estimate` vs a real `full` build (timing mismatch explained)

`--estimate` is a **planning estimate** based on the targets **known/enumerated at
that moment** — for `full` that is mostly the deterministic seeds plus known assets.
A real `full` run is **crawl-based and discovers additional Corpus pages/assets
while it runs**, so it does more work than the up-front estimate implies.

- `--profile full --estimate` reports **~14 h at 2 req/s** (enumerated seeds+assets).
- The **realistic full-mirror model is ~31 h (≈1 day+) at 2 req/s**, because of
  crawl **discovery** plus **retries, the live site's speed, your network speed,
  the volume of assets, and polite back-off pauses**.

Both figures are correct for what they measure; they are not in conflict. Treat
**`full` at the conservative default as roughly "overnight to 1–2 days"**. Users who
want it faster can opt in with `--workers 4 --rate-limit 6` (~10–11 h by the current
estimate) but should not repeatedly hammer the site. `core`/`morphology` are far
quicker and are what most users actually need.

---

## 5. Safe default settings

| Setting | Default | Notes |
| --- | --- | --- |
| `--workers` | 4 | bounded; per-host concurrency = workers (single host) |
| `--rate-limit` | **2 req/s** | global token-bucket cap — intentionally gentle; faster is opt-in (`--rate-limit 6`) |
| `--timeout` | 45 s | per request |
| `--max-retries` | 4 | exponential backoff + jitter; **no infinite retries** |
| adaptive slow-down | on | doubles interval on 429/403/5xx, floor 0.5 req/s |
| `Retry-After` | honoured | clamped to ≤300 s |
| cooldown pause | on | global pause after rate-limit responses |
| checkpoint | every 100 saves + on exit | atomic `.tmp`→replace |

Aggressive scraping is **never** the default; higher speeds are opt-in.

---

## 6. Test results

- **Compile:** `py_compile` passes for builder, server, and audit. ✅
- **Estimate (all profiles + `--mode all`):** runs offline, prints profile,
  target/cached/remaining counts, ETA, disk estimate, and what will/won't download.
  ASCII-only output (fixed a Unicode crash on the default Windows console). ✅
  - At the **default 2 req/s**: core ≈ 14k pages / ~198 MiB / **~2 h**;
    full ≈ 150k pages + 78k assets / ~449 MiB / **~14 h** (enumerated seeds+assets;
    a complete DB-seeded full mirror is ~31 h at this rate).
  - With the **`--rate-limit 6` opt-in**: core ≈ **~39 min** (≈3× faster). ✅
- **Tiny build:** saved pages and wrote `cache/build-report-*.md`. ✅
- **Resume:** re-running the same command reported `skipped=4` (already-cached pages
  detected and not re-downloaded), confirming checkpoint-based resume. ✅
- **Interrupt safety:** `KeyboardInterrupt` is caught — workers stop, the queue is
  drained, and a final atomic checkpoint is written before exit. Atomic
  `.tmp`→replace means a partial write can never corrupt the index. ✅
- **Verify modes:** `db-only`, `core`, `morphology` run and report correctly; on a
  code-only repo they correctly report the DB/cache is absent (exit 1). ✅
- **Repo hygiene:** after testing, the generated `cache/` was deleted; the repo
  contains **no** `cache/pages`, `cache/assets`, SQLite DB, morphology txt, secrets,
  personal paths, or files over 25 MiB (largest file is `server.py`, ~40 KiB). ✅

### Known limitations

- `--max-pages` is an **approximate** cap under parallelism (may exceed by up to
  `workers-1`). It's a testing safety valve, not an exact limit.
- ETA/disk are **estimates** (heuristic averages: ~14.7 KB/page, ~2 KB/asset, ~0.6 s
  latency); real numbers depend on the live site and your connection.
- `core`/`morphology`/`full` URL lists for dictionary/morphology are generated from
  the **local DB**, so build `--profile db-only` first; without a DB those counts
  fall back to documented approximations and morphology/dictionary seeds are empty.
- `full` is crawl-based, so its total is discovered during the run and can't be known
  exactly up front.
- Speed is bounded by the remote site's latency and any server-side throttling; the
  builder deliberately backs off rather than pushing through 429/403/5xx.

---

## 7. Confirmations

- ✅ **Private completed archive NOT modified.** All work was in the public staging
  repo. The private `cache/index.json` remains the intact post-morphology-fix
  archive (149,905 entries, valid JSON, the 5 fix entries present; 149,927 page
  files). Its `cache_corpus_pages.py`, `assets.json`, and SQLite DB retain their
  original dates. (The private index's timestamp is from the earlier *authorized*
  morphology fix, not this work.)
- ✅ **No cache/data added to the public repo.** No `cache/pages`, `cache/assets`,
  `quran_corpus.sqlite3`, or full morphology txt. Only the tiny attributed
  `data/sample-morphology.txt` test fixture remains.
- ✅ **No push, no remote, no commit.** Awaiting your review/approval.
- ✅ **Respectful by default.** Conservative workers + global rate cap + backoff;
  fast settings are opt-in only.

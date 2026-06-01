# Cache Builder Optimisation Plan

**Scope:** public staging repo only (`quran-corpus-offline-public`). The completed
private archive was treated as read-only reference and was **not** modified.

This documents the audit of the original builder and the plan that was implemented.

---

## 1. Audit of the original builder

Files inspected: `quran_offline/cache_corpus_pages.py`, `quran_offline/server.py`,
`README.md`, and the three `.bat` launchers.

| Aspect | Original behaviour | Verdict |
| --- | --- | --- |
| **Crawl/download flow** | Single BFS queue (`deque`); `START_PAGES`/deterministic seeds, optional link-following | Works, but… |
| **Concurrency** | **Sequential** — one request at a time | ⛔ main bottleneck |
| **Throttle/delay** | Fixed `time.sleep(delay)` after each request; default `0.25s` | Crude; no global rate control |
| **Retry/backoff** | **None.** Any exception → counted as error, moves on | ⛔ transient errors lose pages |
| **Retry-After / 429 handling** | None | ⛔ not adaptive to server pushback |
| **Resume / skip-existing** | Yes: `if url in index and path.exists(): skip` | ✅ already present |
| **Asset dedup** | Yes: `if aurl not in asset_index or not apath.exists()` | ✅ already present |
| **Atomic index writes** | Yes: `save_index` writes `.tmp` then `replace`; every 25 pages | ✅ good |
| **Interrupted build safety** | Partial: checkpoints every 25 pages; Ctrl-C not handled gracefully | 🟡 improvable |
| **Progress / ETA** | Prints `[n] url` per page; no totals/ETA/rate | 🟡 weak UX |
| **Profiles / presets** | `--mode start|verse-pages|dictionary|all` only | 🟡 not user-friendly |
| **Dry-run / estimate** | None | ⛔ users can't plan |
| **Content addressing** | `sha256(normalised_url)` → `pages/<hash>.html`, `assets/<hash><ext>` | ✅ preserved exactly |

### Where time is spent

For a near-1:1 mirror the builder issues on the order of **~150k page requests +
~78k asset requests ≈ 228k HTTP round-trips**. At a sequential ~0.25s delay plus
real server latency (~0.5–1s/request observed), wall-clock is dominated by
**round-trip latency × request count**, i.e. effectively serialised network waits.
That is the 3–4 day experience. CPU/disk are negligible by comparison.

### What can be optimised safely

1. **Parallelism** — the single biggest win. Multiple in-flight requests hide
   latency. Must be **bounded** and **rate-limited** to stay respectful.
2. **Retry with backoff** — recover transient 5xx/timeouts instead of losing pages,
   so a build completes in one pass and needs fewer re-runs.
3. **Adaptive politeness** — honour `Retry-After`; slow down / pause on repeated
   429/403/5xx so we never hammer the site.
4. **Profiles** — let users cache just what they need (`core` first) rather than
   committing to the full mirror.
5. **Estimate mode** — show counts, time, and disk before committing.
6. **Better progress + build report** — visibility and easy retry of failures.
7. **Graceful interrupt + frequent atomic checkpoints** — safe resume.

### What must NOT change

- The content-addressing convention (hash of the normalised URL) — required so the
  server and audit tools keep finding pages. **Preserved byte-for-byte.**
- Default behaviour must remain **polite** — speed is opt-in, not aggressive.
- `--mode all` and the existing CLI must keep working.

---

## 2. Plan (implemented)

1. **Profiles** `--profile db-only|core|morphology|full`, alongside legacy `--mode`.
2. **Parallel engine**: bounded worker threads + a global token-bucket
   `Pacer` (max requests/second), per-host concurrency = workers (single host).
3. **Retry**: exponential backoff + jitter, capped retries (no infinite loops),
   `Retry-After` support, adaptive global slow-down + cooldown on 429/403/5xx.
4. **Resumability**: skip cached pages/assets (counted + reported), atomic
   `index.json`/`assets.json` checkpoints every 100 saves and at exit, graceful
   `KeyboardInterrupt` handling.
5. **`--estimate` / `--dry-run`**: profile, target/cached/remaining counts, ETA at
   chosen workers/rate, approximate disk, and what will/won't be downloaded.
6. **Progress + report**: live `done/total, rate, ETA, failures, retries`; a
   `cache/build-report-*.md` (or `BUILD_REPORT.md`) afterwards.
7. **Verification**: `audit_offline_archive --verify db-only|core|morphology|full`.
8. **README**: profiles, resume, safe speeds, verification, and the "build your own
   cache; the 2.3 GB cache is not shipped" guidance.

### Safe defaults chosen

- `--workers 4`, `--rate-limit 6` req/s, `--timeout 45s`, `--max-retries 4`,
  checkpoint every 100 saves, adaptive floor `0.5` req/s during cooldowns.
- These are conservative on purpose. Speed is available via flags but the default
  must never hammer `corpus.quran.com`.

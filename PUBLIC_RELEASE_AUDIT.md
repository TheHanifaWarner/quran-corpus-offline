# Public Release Audit

**Date:** 2026-06-01
**Purpose:** Decide exactly what may be safely published to a public GitHub repository
for this unofficial offline Quranic Arabic Corpus tool, and what must be excluded or
held pending permission. This audit is read-only with respect to the original project;
nothing was uploaded.

**Source project (private, local):** `<project-root>`
**Clean staging repo:** `<staging-root>` (`quran-corpus-offline-public`)

---

## 1. Verdicts at a glance

- ✅ **Code-only GitHub repo: SAFE to publish now.** Contains only original MIT code
  + public docs + attribution + a 7-line test sample. No third-party content, no
  secrets, no personal paths.
- ⛔ **Full offline cache ZIP (cache/ + database): DO NOT publish now.** It contains
  third-party translations and the Corpus project's own copyrighted pages/assets.
  Hold pending explicit permission. See `ATTRIBUTION_AND_LICENSE_NOTES.md`.

---

## 2. File / folder classification

Legend: 🟢 safe for repo · 🟡 Release asset only (with permission) · 🔴 exclude / never publish · ⚖️ licensing review

| Path | Size | Class | Reason |
| --- | --- | --- | --- |
| `quran_offline/*.py` (server, importer, cache builder, audit, buckwalter, surah_data) | ~0.09 MiB | 🟢 repo | Original code, MIT, no secrets |
| `quran_offline/audit_tools/*.py` | ~0.03 MiB | 🟢 repo | Original read-only audit code |
| `*.bat` launchers | ~1.8 KiB | 🟢 repo | Use relative `%~dp0`; no personal paths |
| `data/sample-morphology.txt` | 429 B | 🟢 repo ⚖️ | 7-line attributed Corpus sample (GPL data); fine for testing |
| `README.md`, `LICENSE`, `NOTICE`, attribution & audit docs | small | 🟢 repo | Public docs (scrubbed) |
| `quran_offline/__pycache__/`, `audit_tools/__pycache__/` | ~0.25 MiB | 🔴 exclude | Compiled bytecode; regenerated locally |
| `quran_offline/audit_tools/snapshots/*.json` | ~4 KiB | 🔴 exclude | Contain local absolute machine paths (`root: <local-path>`) |
| `quran_offline/audit_tools/online_compare_results.json` | 16 KiB | 🔴 exclude | Generated run artifact |
| `cache/pages/` (149,927 HTML files) | **2,108.4 MiB** | 🔴 / 🟡 ⚖️ | Corpus page HTML **+ third-party translations**; redistribution needs permission |
| `cache/assets/` (78,119 files) | **153.7 MiB** | 🔴 / 🟡 ⚖️ | Corpus images/CSS/JS; redistribution needs permission |
| `cache/index.json` | 22.7 MiB | 🔴 / 🟡 | Cache manifest; only meaningful with the cache it maps |
| `cache/assets.json` | 10.1 MiB | 🔴 / 🟡 | Asset manifest; same |
| `cache/index.json.bak-before-morph-fix` | 22.7 MiB | 🔴 never | Backup file — never publish |
| `data/quran_corpus.sqlite3` (+`-shm`,`-wal`) | 41 MiB | 🔴 / 🟡 ⚖️ | Generated DB from GPL data; users build it themselves |
| `data/quranic-corpus-morphology-0.4.txt` | 6 MiB | 🔴 repo / ⚖️ | Official GPL data — users download from official site for clean provenance |

### Specifically requested items

| Item | Decision |
| --- | --- |
| `cache/`, `cache/pages/`, `cache/assets/` | **Exclude from repo.** Optional Release asset only **with permission** (⚖️ third-party content). |
| `cache/index.json`, `cache/assets.json` | Exclude from repo (only useful bundled with the cache). |
| `data/`, `quran_corpus.sqlite3` | Exclude from repo (generated; potential Release asset only, with permission). |
| `quranic-corpus-morphology-0.4.txt` | Exclude from repo; user downloads from official site. |
| `audit_tools/snapshots/` | **Exclude** (local machine paths inside). |
| `*.bak` files | **Exclude / never publish.** |
| `*.log` files | None present; excluded by `.gitignore` regardless. |
| Generated reports (`FINAL_…`, `PERFECT_…`, `OFFLINE_AUDIT`) | Included **scrubbed** under `docs/`. |
| Local Windows paths containing the username | **Scrubbed** → `<project-root>` / `<local-path>`; verified none remain in staged files. |
| Email / token / credential / cookie / session data | **None found** anywhere in code or docs. |

---

## 3. Sensitive-data scan results

- **Credentials/tokens/cookies/sessions:** none. The only `token` strings in code are
  the Corpus URL query parameter `token=1` (verse grammar), not secrets.
- **Emails:** none (the `@` characters flagged were Buckwalter morphology notation in
  the data file, which is excluded anyway).
- **Personal/local paths:** present only in the generated audit reports and the
  snapshot JSONs. Reports were **scrubbed** before staging; snapshot JSONs are
  **excluded**. The staged tree was re-scanned: no `AmirT`, `OneDrive`-path, or
  `C:\Users` strings remain in staged files (the word "OneDrive" survives only in
  harmless narrative prose).
- **Launchers:** anchored with `cd /d "%~dp0"` (relative); safe.

---

## 4. Size check

| Scope | Bytes | Size |
| --- | --- | --- |
| **Original full project** | 2,479,818,482 | **2,364.9 MiB (~2.31 GiB)** |
| `cache/` total | 2,430,034,639 | 2,317.5 MiB |
| &nbsp;&nbsp;`cache/pages/` | 2,210,802,378 | 2,108.4 MiB |
| &nbsp;&nbsp;`cache/assets/` | 161,126,815 | 153.7 MiB |
| `data/` total | 49,334,316 | 47.0 MiB |
| `quran_offline/` (incl. artifacts) | 447,700 | 0.4 MiB |
| **Staging repo** (code + docs only) | see git step | **< 0.3 MiB** |

**Files crossing size thresholds:**

| Threshold | Files |
| --- | --- |
| > 25 MiB | `data/quran_corpus.sqlite3` (41 MiB) only |
| > 50 MiB | none |
| > 100 MiB | none (note: `cache/pages` is a *folder* of 2.1 GiB, not one file) |
| > 2 GiB (single file) | none |

GitHub limits to keep in mind: **per-file warning at 50 MiB**, hard **100 MiB** push
limit for normal git (so the DB and cache must never be committed); **GitHub Release
assets allow up to 2 GiB per file**.

**Would a full-cache Release ZIP need splitting?** Uncompressed `cache/` + `data/`
≈ **2.31 GiB**. HTML/JSON compress strongly (often 80–90%), so a ZIP would likely land
in the ~0.4–0.8 GiB range and fit **under the 2 GiB single-asset limit**. However, the
exact compressed size is unverified, so the release plan below includes a split
procedure as a contingency. (This is moot unless/until permission to publish a cache
is obtained.)

---

## 5. Exactly what is staged vs excluded

**Staged for GitHub (repo-safe):**
```
README.md
LICENSE
NOTICE
ATTRIBUTION_AND_LICENSE_NOTES.md
PUBLIC_RELEASE_AUDIT.md
requirements.txt
.gitignore
data/sample-morphology.txt
quran_offline/__init__.py
quran_offline/audit_offline_archive.py
quran_offline/buckwalter.py
quran_offline/cache_corpus_pages.py
quran_offline/import_morphology.py
quran_offline/server.py
quran_offline/surah_data.py
quran_offline/audit_tools/__init__.py
quran_offline/audit_tools/analyze_cache.py
quran_offline/audit_tools/compare_served_vs_raw.py
quran_offline/audit_tools/fallback_equivalence.py
quran_offline/audit_tools/fetch_missing_morphology.py
quran_offline/audit_tools/link_resolution.py
quran_offline/audit_tools/online_compare.py
quran_offline/audit_tools/snapshot_manifest.py
Run Offline Corpus.bat
BUILD-FULL-OFFLINE-CACHE.bat
IMPORT-OFFICIAL-DATA.bat
docs/OFFLINE_AUDIT.md                      (scrubbed)
docs/FINAL_1TO1_QURAN_CORPUS_AUDIT.md      (scrubbed)
docs/PERFECT_MORPHOLOGY_CACHE_FIX_REPORT.md (scrubbed)
```

**Excluded (not copied into staging at all):**
```
cache/                                  (entire offline cache, 2.3 GiB)
data/quran_corpus.sqlite3 (+ -shm/-wal) (generated DB)
data/quranic-corpus-morphology-0.4.txt  (official GPL data; user downloads)
cache/index.json.bak-before-morph-fix   (backup)
quran_offline/**/__pycache__/           (bytecode)
quran_offline/audit_tools/snapshots/    (local-path JSONs)
quran_offline/audit_tools/online_compare_results.json (run artifact)
```

---

## 6. Optional release-package plan (NOT executed)

### A. Code-only GitHub repository (recommended, do now after approval)
- Push the staging repo as-is. No large files, no third-party content.
- Tag e.g. `v3.0.0`. Enable Issues for takedown requests.

### B. Optional full-cache Release ZIP (hold pending permission)
- **Do not build or upload until licensing permission is secured** (translations,
  Corpus content, Tanzil). See `ATTRIBUTION_AND_LICENSE_NOTES.md` §8.
- If/when permitted:
  1. Zip `cache/` + `data/quran_corpus.sqlite3` (exclude `*.bak`, snapshots, logs).
  2. Publish as a **GitHub Release asset** (not a git commit).
  3. Provide a SHA-256 checksum in the release notes.

### C. Splitting a ZIP over 2 GiB (contingency)
- Split into < 2 GiB parts, e.g. 1500 MiB each:
  - 7-Zip: `7z a -v1500m cache.zip cache/ data/quran_corpus.sqlite3`
  - or `split -b 1500m cache.zip cache.zip.` (rejoin with `cat`/`copy /b`).
- Upload each part as a separate Release asset; document the rejoin command and
  checksum in the release notes (see README "future full-cache release ZIP").

### D. Release notes wording (suggested)
> Unofficial offline Quranic Arabic Corpus tool — code only. This release is **not
> affiliated with or endorsed by** the Quranic Arabic Corpus project. All credit to
> Kais Dukes, the University of Leeds Language Research Group, the quran.com
> maintainers, Tanzil, and contributors. No Corpus content or third-party
> translations are included. Build your own local cache from the official source.

### E. Takedown / transfer notice
- Include the takedown/transfer paragraph (already in `ATTRIBUTION_AND_LICENSE_NOTES.md`
  §9 and README) in the repo and every release.

---

## 7. Git preparation (staging folder only)

Performed inside the staging folder only — **no remote, no push**:
```
git init
git symbolic-ref HEAD refs/heads/main   (branch = main)
git add -A        (staging folder only — NOT the original project)
git status        (review)
```
See the session summary for the exact `git status` output and the next command to
approve.

---

## 8. Final recommendation

1. **Publish the code-only repo now** (after your approval) — it is clean and safe.
2. **Do not publish any cache/database/ZIP** until per-source permission is obtained;
   prefer letting each user build their own cache locally.
3. Keep the original private project (cache, DB, backups) **out** of git permanently
   via `.gitignore`.

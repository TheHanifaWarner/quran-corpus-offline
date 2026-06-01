# Unofficial Offline Quranic Arabic Corpus Tool

> **Unofficial & not endorsed.** This is a community-built, offline study tool that
> mirrors the *Quranic Arabic Corpus* experience locally. It is **not** produced,
> endorsed, reviewed, or approved by the original Quranic Arabic Corpus project,
> Kais Dukes, the University of Leeds Language Research Group, or the quran.com
> maintainers — unless they explicitly say otherwise. All scholarly credit and
> authority belong to the original project (see [Attribution](#attribution--provenance)).

A local Python web app that lets you study the Holy Quran word-by-word — morphology,
roots, lemmas, grammar, treebank, dictionary, and ontology concepts — **completely
offline**, after a one-time local setup. It reproduces the original Corpus study
pages either from morphology data (database mode) or from pages you cache yourself
(exact-cache mode).

---

## What this is

- An **offline reader** for Quranic Arabic morphology built on the official
  Quranic Arabic Corpus v0.4 morphology data (which **you** download from the
  official site).
- A **local web server** (`python -m quran_offline.server`) that serves a
  word-by-word reader, morphological search, root dictionary, and lemma frequency
  generated from that data — no internet required once set up.
- An optional **personal offline cache builder** that, while you are online once,
  saves real Corpus study pages to your own machine so you can browse them later
  offline. The cache is rewritten at serve time so it never calls the internet.
- A set of **read-only audit tools** that verify the offline archive's health and
  fidelity.

## What this is **not**

- ❌ Not the official Quranic Arabic Corpus, and not affiliated with it.
- ❌ Not a redistribution of the Corpus website, its translations, or its content.
  This repository ships **only original code** — no cached pages, no database,
  no third-party translations.
- ❌ Not a claim of ownership or authority over any Quranic text, translation,
  morphology data, or Corpus content. Those belong to their original authors.
- ❌ Not a hosted service — it runs only on your own computer at `127.0.0.1`.

---

## Attribution & provenance

This tool exists only because of the original work of others. Full credit to:

- **Quranic Arabic Corpus** — <https://corpus.quran.com>
- **Kais Dukes** — original author/creator
- **Language Research Group, University of Leeds** — where the Corpus was created
- **quran.com maintainers/community** — associated with current hosting
- **Tanzil Project** (<https://tanzil.net>) — source of the Quranic Arabic text
- **Translators & contributors** — for the English translations and annotations
  shown on the Corpus site (each under their own copyright)

The Quranic linguistic data and all Corpus content belong to the original project
and contributors. See [`NOTICE`](NOTICE) and
[`ATTRIBUTION_AND_LICENSE_NOTES.md`](ATTRIBUTION_AND_LICENSE_NOTES.md) for details.

---

## Requirements

- Python **3.11+** (standard library only — **no third-party packages**, see
  [`requirements.txt`](requirements.txt)).
- Windows, macOS, or Linux.

---

## How to run locally

1. **Get the official morphology data** (one-time):
   Download `quranic-corpus-morphology-0.4.txt` from the official download page:
   <https://corpus.quran.com/download/> and place it in `data/`.
   *(Please read and follow the licensing terms on that page.)*

2. **Build the local database:**
   ```bash
   python -m quran_offline.import_morphology --input data/quranic-corpus-morphology-0.4.txt
   ```

3. **Start the offline app:**
   ```bash
   python -m quran_offline.server
   ```
   Then open <http://127.0.0.1:8765/> in your browser.

**Windows users** can instead double-click `Run Offline Corpus.bat`.

Even with only the steps above (no page cache), you get a full offline word-by-word
reader, morphological search, root dictionary, and lemma frequency — all generated
from the morphology data.

---

## How to build/cache pages locally (optional, advanced)

> **This repository does not include the ~2.3 GB cache.** You build your own,
> locally, from the official source. The builder is **resumable, parallel, and
> respectful** so you don't need to leave your PC on for days.

### Build profiles (recommended)

Pick how much to cache with `--profile`:

| Profile | What it caches | Approx pages |
| --- | --- | --- |
| `db-only` | Just the SQLite morphology DB (no page cache) | 0 |
| `core` | Word-by-word + translation for all 6,236 verses + root dictionary | ~14k |
| `morphology` | All word-morphology pages | ~77k |
| `full` | Near-1:1 mirror (everything + crawl) | ~150k pages + ~78k assets |

**Always estimate first** (downloads nothing):

```bash
python -m quran_offline.cache_corpus_pages --profile core --estimate
```

Then build. **Start small** (`db-only` → `core`) before attempting `full`:

```bash
# 1) Build the database first (needed for core/morphology/full URL lists)
python -m quran_offline.cache_corpus_pages --profile db-only

# 2) Cache the most useful pages
python -m quran_offline.cache_corpus_pages --profile core

# 3) (optional) all morphology pages, or the full mirror
python -m quran_offline.cache_corpus_pages --profile morphology
python -m quran_offline.cache_corpus_pages --profile full
```

The legacy commands still work: `--mode start|verse-pages|dictionary|all`
(`--mode all` ≈ `--profile full`). On Windows you can double-click
`BUILD-FULL-OFFLINE-CACHE.bat`. Browse results at <http://127.0.0.1:8765/mirror>.

### Resume instead of restarting

The builder is **checkpointed**. If it stops (Ctrl-C, network drop, reboot),
just **re-run the exact same command** — already-cached pages are skipped and it
continues where it left off. Nothing is re-downloaded and the index is written
atomically, so an interrupted build never corrupts your cache.

### Safe speed settings (be kind to corpus.quran.com)

**The default is intentionally conservative: 4 workers but a global cap of just
2 requests/second**, with automatic retry/backoff and an adaptive slow-down if the
site returns 429/403/5xx. This default is chosen so the tool never encourages
hammering a third-party site — please leave it as-is unless you have a good reason.

```bash
# default (respectful: ~2 req/s) — recommended
python -m quran_offline.cache_corpus_pages --profile full

# faster, advanced opt-in (only if you know the site tolerates it)
python -m quran_offline.cache_corpus_pages --profile full --workers 4 --rate-limit 6
```

Options: `--workers N`, `--rate-limit R` (req/s), `--delay S`, `--timeout S`,
`--max-retries N`, `--max-pages N` (approximate cap for testing),
`--no-assets`, `--no-crawl`, `--estimate`/`--dry-run`.

> ⚠️ **Be respectful and lawful.** This downloads many pages from a third-party
> site. Build once, keep your cache, and use it **for personal use only**. **Do not
> run aggressive settings repeatedly** against corpus.quran.com — a single gentle
> build is the right approach. Caching is not redistribution: the cached content
> (including third-party translations and Corpus page markup) belongs to its owners.
> Do **not** re-publish your cache without permission from the rights holders.
>
> **Timing — and why `--estimate` and real builds differ.** `--estimate` is a
> *planning* figure computed from the targets known **at that moment** (for `full`,
> mostly the deterministic seeds + known assets). A real `full` build also **crawls
> and discovers additional Corpus pages/assets as it goes**, so the live run does
> more work than the up-front estimate suggests. For example, `--profile full
> --estimate` may report ~14 hours at the default 2 req/s, while a real full build is
> better modelled at **~31 hours**. Real-world time also varies with **link discovery,
> retries, the site's speed, your network, the number of assets, and polite pauses**.
>
> Treat **`full` at the conservative default as roughly "overnight to 1–2 days"** —
> it is meant to run gently in the background and resumes if interrupted. Advanced
> users who want it faster can explicitly opt in with **`--workers 4 --rate-limit 6`**
> (~10–11 hours by the current estimate), but should **avoid repeatedly hammering the
> site**. Most users only need `core` (minutes to ~2 h) or `morphology`, not `full`.

### Verify completion

```bash
python -m quran_offline.audit_offline_archive --verify db-only     # DB only
python -m quran_offline.audit_offline_archive --verify core        # core pages
python -m quran_offline.audit_offline_archive --verify morphology  # morphology pages
python -m quran_offline.audit_offline_archive                      # full audit (default)
```

Each build also writes a `cache/build-report-YYYYMMDD-HHMMSS.md` summarising what
was saved, skipped, retried, and any failures (re-run to retry just the failures).

---

## How to use a future full-cache release ZIP (if one is ever provided)

A pre-built cache is **not** distributed in this repository, and may never be,
because it contains third-party content (see licensing notes). *If* an official or
permission-cleared cache archive is ever published as a GitHub Release asset:

1. Download the release ZIP (or the split parts `*.zip.001`, `*.zip.002`, …).
2. If split, rejoin them, e.g.:
   - Windows (PowerShell): `cmd /c copy /b cache.zip.001+cache.zip.002+... cache.zip`
   - macOS/Linux: `cat cache.zip.* > cache.zip`
3. Verify the checksum published in the release notes.
4. Extract so that `cache/pages/`, `cache/assets/`, `cache/index.json`, and
   `cache/assets.json` sit next to `quran_offline/`.
5. Start the server normally; cached pages will be served offline.

---

## Licensing / provenance (summary)

- **This repository's source code:** MIT (see [`LICENSE`](LICENSE)).
- **Quranic Arabic Corpus morphology/annotation data:** © the Corpus project;
  distributed by the project under the **GNU GPL** — obtain it yourself from the
  official site.
- **Quranic Arabic text:** Tanzil Project (CC BY-ND / Tanzil terms).
- **English translations & Corpus page content:** © their respective owners;
  **not** included or redistributed here.

Full detail and open questions are in
[`ATTRIBUTION_AND_LICENSE_NOTES.md`](ATTRIBUTION_AND_LICENSE_NOTES.md).

---

## Known limitations

- The morphology file does not contain every visible gloss/translation/treebank
  text shown on the website; those require the optional local page cache.
- A small number of pages on the live site are dynamic/account-only
  (sign-in, message board, feedback) and are intentionally not cached.
- The bundled `data/sample-morphology.txt` is a tiny 7-line excerpt for testing
  only; it is not the full dataset.
- This is a personal/educational tool, provided "as is" with no warranty.

---

## Audit status summary

The offline archive used to develop this tool was independently audited
(read-only) and classified as a **near-1:1 functional offline mirror** of the live
site, with all **77,429** word-morphology locations available as original cached
HTML. Audit reports are in [`docs/`](docs/):

- `docs/OFFLINE_AUDIT.md` — baseline archive audit
- `docs/FINAL_1TO1_QURAN_CORPUS_AUDIT.md` — full 1:1 comparison vs the live site
- `docs/PERFECT_MORPHOLOGY_CACHE_FIX_REPORT.md` — completing the last 5 pages

> Note: those audits describe a *local* archive on the author's machine. The
> archive itself (cache + database) is **not** part of this repository.

---

## Contact / takedown

If you are a rights holder for any content referenced by this tool and have a
concern, please open an issue. See the takedown/transfer note in
[`ATTRIBUTION_AND_LICENSE_NOTES.md`](ATTRIBUTION_AND_LICENSE_NOTES.md). The intent
of this project is to defer entirely to the original Quranic Arabic Corpus project.

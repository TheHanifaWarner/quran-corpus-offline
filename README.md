# Unofficial Offline Quranic Arabic Corpus Tool

This is an unofficial Python tool for studying Quranic Arabic Corpus material on a local computer. It can build a local SQLite morphology database and, optionally, a personal offline cache of selected pages from the Quranic Arabic Corpus website.

This project is not produced, endorsed, reviewed, or approved by the Quranic Arabic Corpus project, Kais Dukes, the University of Leeds, quran.com, or any associated maintainers.

## What It Does

- Imports the Quranic Arabic Corpus morphology file into SQLite.
- Runs a local web app at `http://127.0.0.1:8765/`.
- Provides an offline morphology reader, root dictionary, lemma frequency view, and morphology search from the local database.
- Optionally builds a local cache of Corpus pages for personal offline study.
- Includes audit commands to estimate, resume, and verify a local cache.

## What It Does Not Include

- No prebuilt page cache.
- No cached Corpus website pages.
- No SQLite database.
- No full morphology file.
- No third-party translations, images, or website content.

Prebuilt cache archives are not included in this repository. This project provides tooling for users to build a local cache from the official Quranic Arabic Corpus website for personal offline study. Redistribution of cached website pages, translations, images, or other third-party content may require additional permission from the relevant rights holders. This repository does not grant rights to redistribute third-party content.

## Download and run

1. Get the code:

   - Click **Code** -> **Download ZIP** on GitHub, then extract the folder.
   - Or clone the repository:

     ```bash
     git clone https://github.com/TheHanifaWarner/quran-corpus-offline.git
     cd quran-corpus-offline
     ```

2. Install Python requirements:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Download `quranic-corpus-morphology-0.4.txt` from the official Corpus download page:
   <https://corpus.quran.com/download/>

4. Place the morphology file at:

   ```text
   data/quranic-corpus-morphology-0.4.txt
   ```

5. Estimate before building. These commands do not download pages:

   ```bash
   python -m quran_offline.cache_corpus_pages --profile core --estimate
   python -m quran_offline.cache_corpus_pages --profile full --estimate
   ```

6. Build the local data/cache you want:

   ```bash
   python -m quran_offline.cache_corpus_pages --profile db-only
   python -m quran_offline.cache_corpus_pages --profile core
   python -m quran_offline.cache_corpus_pages --profile morphology
   python -m quran_offline.cache_corpus_pages --profile full
   ```

   Start with `db-only` or `core` unless you specifically want a broader cache. The builder is resumable: if a build is interrupted, re-run the same command and existing files will be skipped.

7. Verify the local build:

   ```bash
   python -m quran_offline.audit_offline_archive --verify core
   ```

8. Start the local server:

   ```bash
   python -m quran_offline.server
   ```

9. Open:

   ```text
   http://127.0.0.1:8765/
   ```

On Windows, `Run Offline Corpus.bat` starts the local server after Python is installed. The prebuilt full cache is not included; each user builds local cache output on their own machine.

## Attribution

Credit for the Quranic Arabic Corpus belongs to the original project and contributors:

- Quranic Arabic Corpus: <https://corpus.quran.com>
- Kais Dukes and Corpus contributors
- Language Research Group, University of Leeds
- Tanzil Project for Quranic text provenance
- Translation and annotation rights holders shown by the Corpus website
- quran.com maintainers where relevant to current hosting

See [`NOTICE`](NOTICE) and [`docs/LEGAL_NOTES.md`](docs/LEGAL_NOTES.md).

## Requirements

- Python 3.11 or newer.
- No third-party Python packages are required.

## Build Profiles

Use `--profile` for cache builds:

| Profile | Purpose | Network use |
| --- | --- | --- |
| `db-only` | Build only the SQLite morphology database. | None after the morphology file is available locally. |
| `core` | Cache verse word-by-word pages, translations, and root dictionary pages. | Moderate. |
| `morphology` | Cache word morphology pages. | Larger. |
| `full` | Build the broadest local cache using deterministic URLs and crawling. | Largest. |

Estimate first. These commands do not download pages:

```bash
python -m quran_offline.cache_corpus_pages --profile core --estimate
python -m quran_offline.cache_corpus_pages --profile full --estimate
```

Then run a build:

```bash
python -m quran_offline.cache_corpus_pages --profile db-only
python -m quran_offline.cache_corpus_pages --profile core
python -m quran_offline.cache_corpus_pages --profile morphology
python -m quran_offline.cache_corpus_pages --profile full
```

The builder is resumable. Re-run the same command after interruption; existing files are skipped.

## Download Behaviour

The default cache builder settings are conservative:

- `--workers 4`
- `--rate-limit 2`
- retry and backoff for transient failures
- resumable indexes

Faster settings are opt-in:

```bash
python -m quran_offline.cache_corpus_pages --profile full --workers 4 --rate-limit 6
```

Use faster settings responsibly. The source website is a third-party service.

## Verify A Local Cache

```bash
python -m quran_offline.audit_offline_archive --verify db-only
python -m quran_offline.audit_offline_archive --verify core
python -m quran_offline.audit_offline_archive --verify morphology
python -m quran_offline.audit_offline_archive --verify full
```

See [`docs/VERIFYING_A_CACHE.md`](docs/VERIFYING_A_CACHE.md).

## Limitations

- Database mode depends only on morphology data and does not reproduce every website page.
- Exact cached-page mode requires each user to build a local cache.
- Some website features are dynamic, account-based, or intentionally excluded.
- Cache completeness depends on the selected profile and successful access to the source website.

## License And Provenance

- This repository's original source code is licensed under MIT. See [`LICENSE`](LICENSE).
- Quranic Arabic Corpus data and website content belong to their original rights holders.
- The full morphology file and cached pages are not distributed here.
- This repository does not grant rights to redistribute third-party content.

More detail:

- [`docs/QUICKSTART.md`](docs/QUICKSTART.md)
- [`docs/BUILD_PROFILES.md`](docs/BUILD_PROFILES.md)
- [`docs/VERIFYING_A_CACHE.md`](docs/VERIFYING_A_CACHE.md)
- [`docs/LEGAL_NOTES.md`](docs/LEGAL_NOTES.md)
- [`docs/TECHNICAL_AUDIT_SUMMARY.md`](docs/TECHNICAL_AUDIT_SUMMARY.md)

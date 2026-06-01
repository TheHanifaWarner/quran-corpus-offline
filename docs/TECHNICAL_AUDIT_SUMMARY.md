# Technical Audit Summary

The tooling has been tested against a completed local cache during development.
The completed cache is not included in this repository.

## Public Repository Scope

This repository is code-only:

- Python source code.
- Windows launcher scripts.
- Documentation.
- A small sample morphology file for tests and examples.

It excludes:

- `cache/`
- generated SQLite databases
- the full morphology text file
- release archives
- local snapshots and logs

## Verified Behaviors

- Database-only mode can run without a page cache.
- Cached Corpus pages are served through localhost routes.
- Dynamic local routes such as word morphology pages and word images resolve locally when their cache entries exist.
- Audit commands can verify expected cache coverage for supported build profiles.

## Reproducible Checks

```bash
python -m py_compile quran_offline/cache_corpus_pages.py quran_offline/server.py quran_offline/audit_offline_archive.py
python -m quran_offline.cache_corpus_pages --profile core --estimate
python -m quran_offline.cache_corpus_pages --profile full --estimate
```

These commands do not require committing generated cache output.

# Build Profiles

The cache builder supports profiles so users can choose the amount of content
to cache locally.

## Profiles

| Profile | Description |
| --- | --- |
| `db-only` | Build the SQLite morphology database only. |
| `core` | Cache high-use pages such as word-by-word verse pages, translations, and root dictionary pages. |
| `morphology` | Cache word morphology pages. |
| `full` | Build the broadest local cache using deterministic URL lists and link discovery. |

## Estimate Without Downloading

```bash
python -m quran_offline.cache_corpus_pages --profile core --estimate
python -m quran_offline.cache_corpus_pages --profile full --estimate
```

## Build

```bash
python -m quran_offline.cache_corpus_pages --profile db-only
python -m quran_offline.cache_corpus_pages --profile core
python -m quran_offline.cache_corpus_pages --profile morphology
python -m quran_offline.cache_corpus_pages --profile full
```

## Resume

The builder skips already-cached pages and assets. If a build stops, run the
same command again.

## Conservative Defaults

Defaults are intentionally gentle:

- modest worker count
- global rate limit
- retries with backoff
- no infinite retry loop
- atomic index writes

Faster builds require explicit options:

```bash
python -m quran_offline.cache_corpus_pages --profile full --workers 4 --rate-limit 6
```

Use faster settings responsibly. The source website is operated by a third party.

# Quickstart

This guide builds the local database and starts the offline web app.

## Requirements

- Python 3.11 or newer.
- The official `quranic-corpus-morphology-0.4.txt` file from:
  <https://corpus.quran.com/download/>

## Build The Database

Place the morphology file at:

```text
data/quranic-corpus-morphology-0.4.txt
```

Run:

```bash
python -m quran_offline.import_morphology --input data/quranic-corpus-morphology-0.4.txt
```

This creates:

```text
data/quran_corpus.sqlite3
```

The generated SQLite database is local build output and is not included in this
repository.

## Start The App

```bash
python -m quran_offline.server
```

Open:

```text
http://127.0.0.1:8765/
```

Windows users can run:

```text
Run Offline Corpus.bat
```

## Optional Page Cache

The app works in database mode without a page cache. To build a personal local
cache, estimate first:

```bash
python -m quran_offline.cache_corpus_pages --profile core --estimate
```

Then build:

```bash
python -m quran_offline.cache_corpus_pages --profile core
```

The cache is local build output and is not included in this repository.

# Verifying A Local Cache

Use the audit command to verify local build output. The audit reads local files
and can start a temporary local server for smoke checks.

## Verification Scopes

```bash
python -m quran_offline.audit_offline_archive --verify db-only
python -m quran_offline.audit_offline_archive --verify core
python -m quran_offline.audit_offline_archive --verify morphology
python -m quran_offline.audit_offline_archive --verify full
```

`full` is the default when no `--verify` value is supplied.

## Skip Server Smoke Checks

```bash
python -m quran_offline.audit_offline_archive --verify core --skip-server
```

## What The Audit Checks

- SQLite database availability and expected table counts.
- Cache indexes point to existing local files.
- Required page sets are present for the selected profile.
- Local server routes do not depend on active external network references.
- Known dynamic assets, including Arabic word images, resolve locally when present in the asset index.

The audit does not download missing pages.

@echo off
setlocal
cd /d "%~dp0"
echo Quran Corpus Offline
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.11+ from https://python.org and tick "Add Python to PATH".
  pause
  exit /b 1
)
if not exist data\quran_corpus.sqlite3 (
  echo Database not found. Building it now from the public morphology mirror...
  python -m quran_offline.import_morphology
  if errorlevel 1 (
    echo.
    echo Automatic download failed. Download quranic-corpus-morphology-0.4.txt from https://corpus.quran.com/download/
    echo Save it into the data folder, then run:
    echo python -m quran_offline.import_morphology --input data\quranic-corpus-morphology-0.4.txt
    pause
    exit /b 1
  )
)
python -m quran_offline.server --open-path "/cached?url=https%%3A%%2F%%2Fcorpus.quran.com%%2F"
pause

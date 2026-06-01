@echo off
setlocal
cd /d "%~dp0"
echo This will download thousands of Quranic Arabic Corpus pages into the cache folder.
echo Use this when online. When complete, the cached pages work offline through the local app.
echo.
echo Recommended first step:
echo   python -m quran_offline.cache_corpus_pages --profile full --estimate
echo.
echo The full build may take many hours. It is resumable: if it stops, run this
echo file again and already-cached pages will be skipped.
echo.
pause
if not exist data\quran_corpus.sqlite3 (
  echo Database not found. Building it first so root dictionary pages can be generated...
  python -m quran_offline.import_morphology
  if errorlevel 1 (
    echo Database import failed. Put quranic-corpus-morphology-0.4.txt in the data folder and run IMPORT-OFFICIAL-DATA.bat first.
    pause
    exit /b 1
  )
)
echo.
echo Starting full cache now. You should see lines beginning with [1], [2], [3] etc.
echo.
python -m quran_offline.cache_corpus_pages --profile full
pause

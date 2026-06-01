@echo off
setlocal
cd /d "%~dp0"
echo Put quranic-corpus-morphology-0.4.txt into the data folder first.
python -m quran_offline.import_morphology --input data\quranic-corpus-morphology-0.4.txt
pause

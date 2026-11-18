@echo off
echo ========================================================
echo Starting AutoClipper with Python 3.13 (Faster-Whisper)
echo ========================================================
"%LOCALAPPDATA%\Programs\Python\Python313\python.exe" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
pause

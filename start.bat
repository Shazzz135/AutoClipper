@echo off
echo ========================================================
echo Starting AutoClipper with Python 3.13 (Faster-Whisper)
echo ========================================================
"%LOCALAPPDATA%\Programs\Python\Python313\python.exe" -m uvicorn backend.main:app --host localhost --port 8000 --reload --reload-dir backend
pause

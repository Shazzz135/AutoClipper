@echo off
title AutoClipper - Connect YouTube Account
echo ========================================================
echo Connecting YouTube Account (OAuth 2.0 Authorization)
echo ========================================================
echo.
"%LOCALAPPDATA%\Programs\Python\Python313\python.exe" scripts\auth_youtube.py
echo.
echo Press any key to exit...
pause >nul

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Connecting YouTube Account (OAuth 2.0 Authorization)" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$pythonPath = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
if (Test-Path $pythonPath) {
    & $pythonPath scripts\auth_youtube.py
} else {
    python scripts\auth_youtube.py
}

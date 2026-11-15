# TARS Care AI — One-Command Local Startup Script (PowerShell)
Write-Host "Starting TARS Care AI Backend (FastAPI on http://127.0.0.1:8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot\backend'; python -m uvicorn main:app --host 127.0.0.1 --port 8000"

Write-Host "Starting TARS Care AI Frontend (Vite on http://127.0.0.1:5173)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot\frontend'; npm run dev -- --host 127.0.0.1 --port 5173"

Write-Host "TARS Care AI is launching at http://127.0.0.1:5173" -ForegroundColor Green


# Agent Mind Bridge — Start all services (Windows PowerShell)
# Usage: .\start.ps1

$ErrorActionPreference = "Stop"

Write-Host "==============================" -ForegroundColor Cyan
Write-Host "  Agent Mind Bridge v4.0.0" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan

# 1. Environment Check
if (-not (Test-Path ".env")) {
    Write-Host "[!] Warning: .env file not found. Copying from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
}

# 2. Dependency Check (Dashboard)
if (-not (Test-Path "dashboard\node_modules")) {
    Write-Host "[*] Installing dashboard dependencies (npm install)..." -ForegroundColor Yellow
    Set-Location "dashboard"
    npm.cmd install
    Set-Location ".."
}

# 3. Start Services
Write-Host "[*] Starting services..." -ForegroundColor Green

# Start MCP Server
Write-Host "  -> Starting MCP Server on port 3333..." -ForegroundColor Gray
$mcpProc = Start-Process python -ArgumentList "server.py" -NoNewWindow -PassThru

# Start REST API
Write-Host "  -> Starting REST API on port 8000..." -ForegroundColor Gray
$apiProc = Start-Process uvicorn -ArgumentList "api:app --host 127.0.0.1 --port 8000" -NoNewWindow -PassThru

# Start Dashboard
Write-Host "  -> Starting Dashboard on port 3000..." -ForegroundColor Gray
$dashProc = Start-Process npm.cmd -ArgumentList "run dev" -WorkingDirectory "dashboard" -NoNewWindow -PassThru

Write-Host ""
Write-Host "Agent Mind Bridge is running!" -ForegroundColor Green
Write-Host "------------------------------"
Write-Host "  MCP Server:  http://127.0.0.1:3333/mcp"
Write-Host "  REST API:    http://127.0.0.1:8000"
Write-Host "  Dashboard:   http://localhost:3000"
Write-Host "------------------------------"
Write-Host "Press Ctrl+C in this window to stop all services."

# Keep the script alive and wait for termination
try {
    while ($true) {
        Start-Sleep -Seconds 1
        if ($mcpProc.HasExited) { Write-Host "[!] MCP Server stopped." -ForegroundColor Red; break }
        if ($apiProc.HasExited) { Write-Host "[!] REST API stopped." -ForegroundColor Red; break }
    }
}
finally {
    Write-Host "`n[*] Shutting down services..." -ForegroundColor Yellow
    Stop-Process -Id $mcpProc.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $apiProc.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $dashProc.Id -ErrorAction SilentlyContinue
    Write-Host "[+] All services stopped. Goodbye!" -ForegroundColor Green
}

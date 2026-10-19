param(
    [switch]$NoWait,
    [switch]$NoBrowser
)

# Content Outlier - Unified One-Click Launcher
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "                       CONTENT OUTLIER" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

function Stop-AllServices {
    param([switch]$Silent)
    if (-not $Silent) {
        Write-Host "Cleaning up existing Content Outlier instances..." -ForegroundColor Yellow
    }

    # 1. Kill any process listening on ports 8000 or 3000
    foreach ($p in @(8000, 3000)) {
        try {
            $conns = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue
            if ($conns) {
                $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
                foreach ($procId in $pids) {
                    if ($procId -gt 4) {
                        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                    }
                }
            }
        } catch {}
    }

    # 2. Kill orphan worker, uvicorn, or standalone node processes
    try {
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.CommandLine -and (
                $_.CommandLine.Contains("app.worker.runner") -or
                $_.CommandLine.Contains("app.api.main:app") -or
                $_.CommandLine.Contains("frontend/.next/standalone/server.js")
            )
        } | ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    } catch {}

    # 3. Wait for ports to be fully released
    for ($i = 0; $i -lt 10; $i++) {
        $c8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
        $c3000 = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
        if ((-not $c8000) -and (-not $c3000)) { break }
        Start-Sleep -Milliseconds 300
    }
}

# Stop any lingering background instances first
Stop-AllServices -Silent

# 2. Check Python executable
$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

# 3. Start Backend API (FastAPI)
Write-Host "[1/3] Starting backend engine: FastAPI on port 8000..." -ForegroundColor Yellow
$backendProc = Start-Process -FilePath $PythonExe `
    -ArgumentList "-m uvicorn app.api.main:app --host 127.0.0.1 --port 8000" `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -PassThru

# 4. Start Background Worker (Scraper & Outlier Intelligence)
Write-Host "[2/3] Starting background worker: Residential Scraper..." -ForegroundColor Yellow
$workerProc = Start-Process -FilePath $PythonExe `
    -ArgumentList "-m app.worker.runner" `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -PassThru

# 5. Start Web Frontend
Write-Host "[3/3] Starting web frontend on port 3000..." -ForegroundColor Yellow
$frontendScript = Join-Path $Root "frontend\.next\standalone\server.js"
if (Test-Path $frontendScript) {
    # Ensure Next.js standalone has static assets & public assets synced
    $staticSrc = Join-Path $Root "frontend\.next\static"
    $staticDst = Join-Path $Root "frontend\.next\standalone\.next\static"
    if ((Test-Path $staticSrc) -and (-not (Test-Path $staticDst))) {
        Copy-Item -Path $staticSrc -Destination $staticDst -Recurse -Force -ErrorAction SilentlyContinue
    }
    $pubSrc = Join-Path $Root "frontend\public"
    $pubDst = Join-Path $Root "frontend\.next\standalone\public"
    if ((Test-Path $pubSrc) -and (-not (Test-Path $pubDst))) {
        Copy-Item -Path $pubSrc -Destination $pubDst -Recurse -Force -ErrorAction SilentlyContinue
    }

    $frontendProc = Start-Process -FilePath "node" `
        -ArgumentList "frontend/.next/standalone/server.js" `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -PassThru
} else {
    $frontendProc = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c npm --prefix frontend run dev" `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -PassThru
}

# Wait for backend (port 8000) and frontend (port 3000) to be ready
Write-Host "  Waiting for backend and web interface to bind..." -ForegroundColor Gray
$backendReady = $false
$frontendReady = $false

for ($i = 0; $i -lt 40; $i++) {
    if (-not $backendReady) {
        $c8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
        if ($c8000) { $backendReady = $true }
    }
    if (-not $frontendReady) {
        $c3000 = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
        if ($c3000) { $frontendReady = $true }
    }
    if ($backendReady -and $frontendReady) { break }
    if ($backendProc.HasExited) {
        Write-Host "[ERROR] Backend API process terminated unexpectedly." -ForegroundColor Red
        break
    }
    if ($frontendProc.HasExited) {
        Write-Host "[ERROR] Frontend process terminated unexpectedly." -ForegroundColor Red
        break
    }
    Start-Sleep -Milliseconds 500
}

if (-not $frontendReady) {
    Write-Host "[WARNING] Frontend port 3000 did not respond in time. Check if node or npm is working." -ForegroundColor Yellow
}

Start-Sleep -Seconds 1

# 6. Open Browser
if (-not $NoBrowser) {
    Write-Host ""
    Write-Host "[OK] All services are running!" -ForegroundColor Green
    Write-Host "  Opening http://localhost:3000 in your browser..." -ForegroundColor Green

    $targetUrl = "http://localhost:3000"
    $launched = $false

    $browserCandidates = @(
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    )

    foreach ($bPath in $browserCandidates) {
        if ($bPath -and (Test-Path $bPath)) {
            try {
                Start-Process -FilePath $bPath -ArgumentList $targetUrl -ErrorAction Stop
                $launched = $true
                break
            } catch {}
        }
    }

    if (-not $launched) {
        try {
            Start-Process $targetUrl -ErrorAction Stop
            $launched = $true
        } catch {}
    }

    if (-not $launched) {
        try {
            Start-Process "cmd.exe" -ArgumentList "/c", "start", '""', "`"$targetUrl`"" -ErrorAction SilentlyContinue
            $launched = $true
        } catch {}
    }
} else {
    Write-Host ""
    Write-Host "[OK] All services are running in background!" -ForegroundColor Green
}

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  Platform URL: http://localhost:3000" -ForegroundColor White
Write-Host "  Backend API:  http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  Scraping IP:  Residential - Your local network connection" -ForegroundColor White
Write-Host "========================================================================" -ForegroundColor Cyan

if (-not $NoWait) {
    Write-Host "  Keep this window open while using Content Outlier." -ForegroundColor Gray
    Write-Host "  Press Enter or close this window to stop all services." -ForegroundColor Gray
    Write-Host ""

    # Wait for user input to terminate
    $null = Read-Host "Press Enter to exit and stop all services"

    Write-Host ""
    Write-Host "Stopping Content Outlier services..." -ForegroundColor Yellow

    Stop-AllServices

    Write-Host "[OK] Content Outlier stopped cleanly." -ForegroundColor Green
    Start-Sleep -Seconds 1
} else {
    Write-Host "  Content Outlier background services active." -ForegroundColor Gray
    Write-Host "  Run 'Stop Content Outlier.bat' to stop all services." -ForegroundColor Gray
}

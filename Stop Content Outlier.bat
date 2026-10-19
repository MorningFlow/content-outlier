@echo off
title Stop Content Outlier
cd /d "%~dp0"
echo Stopping all Content Outlier services...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { foreach ($p in @(8000, 3000)) { $conns = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue; if ($conns) { foreach ($id in ($conns | Select-Object -ExpandProperty OwningProcess -Unique)) { if ($id -gt 4) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue } } } }; Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and ($_.CommandLine.Contains('app.worker.runner') -or $_.CommandLine.Contains('app.api.main:app') -or $_.CommandLine.Contains('frontend/.next/standalone/server.js')) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }"
echo.
echo [OK] All Content Outlier services have been stopped.
powershell -NoProfile -Command "Start-Sleep -Seconds 2"

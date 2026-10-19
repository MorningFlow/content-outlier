@echo off
title Content Outlier Launcher
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher.ps1"
if errorlevel 1 (
    echo [ERROR] Launcher exited with an error.
    pause
)

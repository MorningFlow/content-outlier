@echo off
title ContentOutlier Local Scraping Agent
cd /d "%~dp0"
echo ============================================================
echo Starting ContentOutlier Scraping Agent (Residential IP)
echo ============================================================
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" contentoutlier_agent.py
) else (
    python contentoutlier_agent.py
)
pause

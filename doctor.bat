@echo off
chcp 65001 >nul
title AI Usage Widget - Doctor
cd /d "%~dp0"
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (where python >nul 2>&1 && set "PY=python")
if not defined PY (
    echo Python not found. Run install.bat first.
    pause
    exit /b 1
)
%PY% "%~dp0doctor.py"

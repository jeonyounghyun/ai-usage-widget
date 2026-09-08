@echo off
rem Remove the widget (shortcut, autostart, files). Helper programs are NOT removed.
title AI Usage Widget - Uninstall
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Uninstall

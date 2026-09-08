@echo off
rem AI Usage Widget installer launcher. The actual steps (with Korean messages) are in install.ps1.
title AI Usage Widget - Install
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"

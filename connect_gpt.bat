@echo off
rem Connect GPT later (install Codex CLI if needed, log in, enable GPT in the widget)
title AI Usage Widget - GPT connect
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Gpt

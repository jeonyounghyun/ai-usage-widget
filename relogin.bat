@echo off
rem Re-login to Claude (opens the Korean guide in install.ps1 with -Relogin)
title AI Usage Widget - Claude login
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Relogin

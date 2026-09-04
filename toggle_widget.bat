@echo off
rem Toggle AI usage widget: stop if running, otherwise start.
rem   toggle_widget.bat          -> toggle
rem   toggle_widget.bat /start   -> start only (used by installer / autostart)
set "SCRIPT=%~dp0usage_widget.py"

rem --- find a windowless Python (pythonw): install-manager launcher > PATH > py launcher
set "PYW="
if exist "%LOCALAPPDATA%\Python\bin\pythonw.exe" set "PYW=%LOCALAPPDATA%\Python\bin\pythonw.exe"
if not defined PYW for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW for /f "delims=" %%i in ('where pyw 2^>nul') do if not defined PYW set "PYW=%%i" & set "PYARGS=-3"
if not defined PYW (
    echo Python not found. Run install.bat first.
    pause
    exit /b 1
)

if /i "%~1"=="/start" goto :start

powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'usage_widget' }; if ($p) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; exit 1 } else { exit 0 }"
if %errorlevel%==1 exit /b

:start
start "" "%PYW%" %PYARGS% "%SCRIPT%"

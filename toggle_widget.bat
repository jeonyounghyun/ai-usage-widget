@echo off
rem Toggle AI usage widget: stop if running, otherwise start
set "PYW=%LOCALAPPDATA%\Python\bin\pythonw.exe"
if not exist "%PYW%" for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined FOUND (set "PYW=%%i" & set FOUND=1)
set "SCRIPT=%~dp0usage_widget.py"
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'usage_widget' }; if ($p) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; exit 1 } else { exit 0 }"
if %errorlevel%==1 exit /b
start "" "%PYW%" "%SCRIPT%"

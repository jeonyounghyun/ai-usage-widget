@echo off
rem AI usage widget launcher.
rem   toggle_widget.bat          -> start the widget, or bring it back if already running (never stops it)
rem   toggle_widget.bat /start   -> same as above (used by installer)
rem   toggle_widget.bat /boot    -> start with --boot (used by Windows startup)
rem   toggle_widget.bat /stop    -> stop the widget (used by uninstall)
set "SCRIPT=%~dp0usage_widget.py"

if /i "%~1"=="/stop" (
    powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'usage_widget' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
    exit /b 0
)

rem --- already running? then ask it to show itself instead of starting a second copy
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'usage_widget' }; if ($p) { exit 1 } else { exit 0 }"
if %errorlevel%==1 (
    echo show > "%~dp0show.flag"
    exit /b 0
)

rem --- find a windowless Python (pythonw): recorded by installer > install-manager launcher > py launcher > PATH
rem     (pythonw.exe on PATH may be the Microsoft Store stub, which silently does nothing -> skip WindowsApps)
set "PYW="
if exist "%~dp0pythonw.txt" for /f "usebackq delims=" %%i in ("%~dp0pythonw.txt") do if exist "%%i" set "PYW=%%i"
if not defined PYW if exist "%LOCALAPPDATA%\Python\bin\pythonw.exe" set "PYW=%LOCALAPPDATA%\Python\bin\pythonw.exe"
if not defined PYW for /f "usebackq delims=" %%i in (`py -3 -c "import sys,os;p=os.path.join(os.path.dirname(sys.executable),'pythonw.exe');print(p if os.path.exists(p) else '')" 2^>nul`) do if not defined PYW set "PYW=%%i"
if not defined PYW for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW (echo %%i | find /i "WindowsApps" >nul || set "PYW=%%i")
if not defined PYW for /f "delims=" %%i in ('where pyw 2^>nul') do if not defined PYW set "PYW=%%i" & set "PYARGS=-3"
if not defined PYW (
    echo Python not found. Run install.bat first.
    pause
    exit /b 1
)
if /i "%~1"=="/boot" set "PYARGS2=--boot"
start "" "%PYW%" %PYARGS% "%SCRIPT%" %PYARGS2%

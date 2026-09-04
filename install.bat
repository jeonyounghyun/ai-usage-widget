@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title AI Usage Widget - Install
cd /d "%~dp0"

echo.
echo  ==============================================
echo    AI Usage Widget  one-click install
echo  ==============================================
echo.

rem ---------- 1. Python ----------
set "PY="
where py >nul 2>&1 && (py -3 -c "import sys" >nul 2>&1 && set "PY=py -3")
if not defined PY (where python >nul 2>&1 && (python -c "import sys" >nul 2>&1 && set "PY=python"))
if not defined PY (
    echo  [1/5] Python not found - installing via winget ...
    winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements --silent
    if errorlevel 1 (
        echo  ! Python install failed. Install it from https://python.org and run this again.
        pause & exit /b 1
    )
    set "PY=py -3"
) else (
    echo  [1/5] Python found: !PY!
)

rem ---------- 2. Pillow ----------
echo  [2/5] Installing Pillow ...
!PY! -m pip install --user --quiet --disable-pip-version-check pillow
if errorlevel 1 (
    echo  ! pip failed. Check your internet connection.
    pause & exit /b 1
)

rem ---------- 3. Win-CodexBar ----------
set "CLI=%LOCALAPPDATA%\Programs\CodexBar\codexbar-cli.exe"
if exist "%CLI%" (
    echo  [3/5] Win-CodexBar found.
) else (
    echo  [3/5] Installing Win-CodexBar via winget ...
    winget install -e --id Finesssee.Win-CodexBar --accept-package-agreements --accept-source-agreements --silent
    if not exist "%CLI%" (
        echo  ! Win-CodexBar not found after install. Get it from https://github.com/nesszer/Win-CodexBar/releases
        pause & exit /b 1
    )
)

rem ---------- 4. Desktop shortcut ----------
echo  [4/5] Creating desktop shortcut "AI Usage Widget" ...
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$sc = $ws.CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'AI Usage Widget.lnk'));" ^
  "$sc.TargetPath = '%~dp0toggle_widget.bat'; $sc.WorkingDirectory = '%~dp0';" ^
  "$sc.IconLocation = '%LOCALAPPDATA%\Programs\CodexBar\icon.ico'; $sc.WindowStyle = 7; $sc.Save()"

rem ---------- 5. Autostart (optional) ----------
set "ANS="
set /p ANS="  [5/5] Start automatically with Windows? (Y/N): "
if /i "!ANS!"=="Y" (
    set "SU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ai-usage-widget.bat"
    > "!SU!" echo @echo off
    >> "!SU!" echo call "%~dp0toggle_widget.bat" /start
    echo        Autostart enabled.
)

echo.
echo  ==============================================
echo    Almost done - 2 things only you can do:
echo.
echo    1) Claude Code must be logged in on this PC
echo       (open a terminal and run:  claude )
echo    2) In the Win-CodexBar window that opens now:
echo       Settings ^> Providers ^> Claude ^>
echo       check "Allow reading Claude Code's credentials"
echo       Then you may close Win-CodexBar.
echo  ==============================================
echo.
start "" "%LOCALAPPDATA%\Programs\CodexBar\codexbar.exe"
echo  Starting the widget ...
call "%~dp0toggle_widget.bat" /start
echo  Done. Use the desktop shortcut to toggle the widget on/off.
pause

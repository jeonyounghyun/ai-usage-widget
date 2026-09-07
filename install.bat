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
echo  This widget shows your Claude and GPT usage limits.
echo  - Claude: claude.ai chat and Claude Code share the same limit,
echo    so you only need to LOG IN to Claude Code once (no need to use it).
echo  - GPT: the "GPT" number is the ChatGPT agent limit (Work / Codex).
echo    To see it, log in to Codex CLI once (no need to use it).
echo.

rem ---------- 1. Python ----------
set "PY="
where py >nul 2>&1 && (py -3 -c "import sys" >nul 2>&1 && set "PY=py -3")
if not defined PY (where python >nul 2>&1 && (python -c "import sys" >nul 2>&1 && set "PY=python"))
if not defined PY (
    echo  [1/7] Python not found - installing via winget ...
    winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements --silent
    if errorlevel 1 (
        echo  ! Python install failed. Install it from https://python.org and run this again.
        pause & exit /b 1
    )
    set "PY=py -3"
) else (
    echo  [1/7] Python found: !PY!
)

rem ---------- 2. Pillow ----------
echo  [2/7] Installing Pillow ...
!PY! -m pip install --user --quiet --disable-pip-version-check pillow
if errorlevel 1 (
    echo  ! pip failed. Check your internet connection.
    pause & exit /b 1
)

rem ---------- 3. Win-CodexBar ----------
set "CLI=%LOCALAPPDATA%\Programs\CodexBar\codexbar-cli.exe"
set "APP=%LOCALAPPDATA%\Programs\CodexBar\codexbar.exe"
if exist "%CLI%" (
    echo  [3/7] Win-CodexBar found.
) else (
    echo  [3/7] Installing Win-CodexBar via winget ...
    winget install -e --id Finesssee.Win-CodexBar --accept-package-agreements --accept-source-agreements --silent
    if not exist "%CLI%" (
        echo  ! Win-CodexBar not found after install. Get it from https://github.com/nesszer/Win-CodexBar/releases
        pause & exit /b 1
    )
)

rem ---------- 4. Claude Code login ----------
echo  [4/7] Claude Code ...
set "CLAUDE_EXE="
where claude >nul 2>&1 && set "CLAUDE_EXE=claude"
if not defined CLAUDE_EXE if exist "%USERPROFILE%\.local\bin\claude.exe" set "CLAUDE_EXE=%USERPROFILE%\.local\bin\claude.exe"
if not defined CLAUDE_EXE (
    echo        Installing Claude Code ...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex" >nul
    if exist "%USERPROFILE%\.local\bin\claude.exe" (
        set "CLAUDE_EXE=%USERPROFILE%\.local\bin\claude.exe"
        powershell -NoProfile -Command "[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path','User') + ';' + $env:USERPROFILE + '\.local\bin', 'User')"
    ) else (
        echo  ! Claude Code install failed. Install it manually: https://claude.ai/code
    )
)
if exist "%USERPROFILE%\.claude\.credentials.json" (
    echo        Claude login found.
) else if defined CLAUDE_EXE (
    echo.
    echo   ---------------------------------------------------------------
    echo    Claude will open now. Please LOG IN:
    echo      1. choose "Claude account with subscription"
    echo      2. log in in the browser and click Authorize
    echo      3. back here, type  /exit  and press Enter to continue
    echo   ---------------------------------------------------------------
    echo.
    pause
    call "!CLAUDE_EXE!"
    if exist "%USERPROFILE%\.claude\.credentials.json" (echo        Claude login OK.) else (echo  ! Claude login not detected. You can run  claude  later.)
)

rem ---------- 5. GPT (Codex) login - optional ----------
set "PROVIDERS=claude"
set "ANS="
set /p ANS="  [5/7] Show GPT usage too? (needs one Codex CLI login) (Y/N): "
if /i "!ANS!"=="Y" (
    set "PROVIDERS=claude,codex"
    where codex >nul 2>&1
    if errorlevel 1 (
        where npm >nul 2>&1 && (echo        Installing Codex CLI ... & call npm install -g @openai/codex >nul)
    )
    where codex >nul 2>&1
    if errorlevel 1 (
        echo  ! Codex CLI not found. Install it later ^(npm install -g @openai/codex^) and run:  codex login
    ) else if exist "%USERPROFILE%\.codex\auth.json" (
        echo        Codex login found.
    ) else (
        echo        Codex login: a browser will open, log in with your ChatGPT account.
        call codex login
    )
) else (
    echo        GPT hidden. You can turn it on later: right-click the widget.
    if not exist "widget_state.json" (> "widget_state.json" echo {"show_gpt": false})
)

rem ---------- 6. Configure Win-CodexBar (allow Claude credentials, etc.) ----------
echo  [6/7] Configuring Win-CodexBar ...
if not exist "%APPDATA%\CodexBar\settings.json" (
    start "" "%APP%"
    for /l %%i in (1,1,20) do (
        if not exist "%APPDATA%\CodexBar\settings.json" ping -n 2 127.0.0.1 >nul
    )
    taskkill /im codexbar.exe /f >nul 2>&1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure_codexbar.ps1" -Providers "!PROVIDERS!"
if errorlevel 1 (
    echo  ! Could not write Win-CodexBar settings automatically.
    echo    Open CodexBar: tray icon ^> Settings ^> Providers ^> Claude ^> check "Allow reading Claude Code's credentials"
)
"%CLI%" autostart --disable >nul 2>&1

rem ---------- 7. Shortcut + autostart + start ----------
echo  [7/7] Creating desktop shortcut "AI Usage Widget" ...
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$sc = $ws.CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'AI Usage Widget.lnk'));" ^
  "$sc.TargetPath = '%~dp0toggle_widget.bat'; $sc.WorkingDirectory = '%~dp0';" ^
  "$sc.IconLocation = '%LOCALAPPDATA%\Programs\CodexBar\icon.ico'; $sc.WindowStyle = 7; $sc.Save()"
set "ANS="
set /p ANS="       Start automatically with Windows? (Y/N): "
if /i "!ANS!"=="Y" (
    set "SU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ai-usage-widget.bat"
    > "!SU!" echo @echo off
    >> "!SU!" echo call "%~dp0toggle_widget.bat" /boot
    echo        Autostart enabled.
)

echo.
echo  Starting the widget ...
call "%~dp0toggle_widget.bat" /start
echo.
echo  Done. Use the desktop shortcut to toggle the widget on/off.
echo  If numbers don't show up, run doctor.bat.
pause

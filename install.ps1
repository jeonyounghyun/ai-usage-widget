# AI Usage Widget 설치 스크립트 (install.bat이 호출). 한글 안내를 위해 PowerShell로 작성.
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Say($t) { Write-Host $t }
function Head($t) { Write-Host ""; Write-Host ("  " + $t) -ForegroundColor Cyan }
function Warn($t) { Write-Host ("  ! " + $t) -ForegroundColor Yellow }
function Ask($q) { return (Read-Host ("  " + $q)) }
function Pause-Enter($t = "계속하려면 Enter") { [void](Read-Host ("  " + $t)) }

Say ""
Say "  =============================================="
Say "    AI 사용량 위젯 설치"
Say "  =============================================="
Say ""
Say "  이 위젯은 Claude와 GPT의 사용량 한도를 화면에 항상 보여줍니다."
Say "   - Claude: claude.ai 채팅과 Claude Code가 같은 한도를 씁니다."
Say "     그래서 Claude Code를 쓰지 않아도, 한 번만 로그인해 두면 채팅 사용량이 보입니다."
Say "   - GPT: 표시되는 숫자는 ChatGPT의 에이전트 한도(Codex / ChatGPT Work)입니다."
Say "     ChatGPT 일반 채팅 한도는 볼 수 없습니다."
Say ""
Say "  설치 중 파란색 'Windows의 PC 보호' 경고가 뜨면 '추가 정보' → '실행'을 누르세요."
Say "  프로그램 설치 때 '이 앱이 디바이스를 변경하도록 허용' 창이 뜨면 '예'를 누르세요."
Say ""

# ---------- 0. 영구 폴더로 이동 (Downloads/임시 폴더에서 실행하면 나중에 지워져 깨짐)
$tempish = @($env:TEMP, (Join-Path $env:USERPROFILE "Downloads"), [Environment]::GetFolderPath("Desktop"))
$permanent = Join-Path $env:LOCALAPPDATA "Programs\ai-usage-widget"
if ($tempish | Where-Object { $Here.StartsWith($_, [System.StringComparison]::OrdinalIgnoreCase) }) {
    Head "[0/7] 설치 폴더"
    Say "  지금 폴더($Here)는 나중에 지워질 수 있는 위치입니다."
    Say "  위젯 파일을 $permanent 로 복사해서 거기서 설치합니다."
    New-Item -ItemType Directory -Force $permanent | Out-Null
    Get-ChildItem $Here -File | ForEach-Object { Copy-Item $_.FullName $permanent -Force }
    if (Test-Path (Join-Path $Here "docs")) { Copy-Item (Join-Path $Here "docs") $permanent -Recurse -Force }
    $Here = $permanent
}
Set-Location $Here

# ---------- 1. Python
Head "[1/7] Python"
function Find-Python {
    # 실제로 실행되는 Python만 인정 (py 런처만 있고 Python이 없는 경우 제외)
    foreach ($c in @(@("py", @("-3")), @("python", @()), @("python3", @()))) {
        if (Get-Command $c[0] -ErrorAction SilentlyContinue) {
            & $c[0] @($c[1]) -c "import sys" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $c }
        }
    }
    return $null
}
$found = Find-Python
if (-not $found) {
    Say "  Python이 없어서 설치합니다 (1~2분)..."
    winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements --silent | Out-Null
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    $found = Find-Python
}
$py = $null
if ($found) { $py = $found[0]; $pyArgs = $found[1] }
if (-not $py) {
    Warn "Python 설치에 실패했습니다. https://python.org 에서 설치(Add python.exe to PATH 체크)한 뒤 install.bat을 다시 실행하세요."
    Pause-Enter; exit 1
}
Say "  Python 확인됨."
Say "  그림 라이브러리(Pillow) 설치..."
& $py @pyArgs -m pip install --user --quiet --disable-pip-version-check pillow
if ($LASTEXITCODE -ne 0) { Warn "Pillow 설치 실패. 인터넷 연결을 확인하고 install.bat을 다시 실행하세요."; Pause-Enter; exit 1 }

# ---------- 2. Win-CodexBar
Head "[2/7] Win-CodexBar (사용량을 읽어 오는 도구)"
$cli = Join-Path $env:LOCALAPPDATA "Programs\CodexBar\codexbar-cli.exe"
$app = Join-Path $env:LOCALAPPDATA "Programs\CodexBar\codexbar.exe"
if (-not (Test-Path $cli)) {
    Say "  설치합니다..."
    winget install -e --id Finesssee.Win-CodexBar --accept-package-agreements --accept-source-agreements --silent | Out-Null
}
if (-not (Test-Path $cli)) { Warn "Win-CodexBar 설치 실패. https://github.com/nesszer/Win-CodexBar/releases 에서 설치 후 install.bat을 다시 실행하세요."; Pause-Enter; exit 1 }
Say "  확인됨."

# ---------- 3. Claude 로그인
Head "[3/7] Claude 로그인"
$claudeExe = $null
if (Get-Command claude -ErrorAction SilentlyContinue) { $claudeExe = "claude" }
elseif (Test-Path "$env:USERPROFILE\.local\bin\claude.exe") { $claudeExe = "$env:USERPROFILE\.local\bin\claude.exe" }
if (-not $claudeExe) {
    Say "  Claude Code(로그인 도구)를 설치합니다..."
    try { irm https://claude.ai/install.ps1 | iex | Out-Null } catch { Warn "설치 실패: $($_.Exception.Message)" }
    if (Test-Path "$env:USERPROFILE\.local\bin\claude.exe") {
        $claudeExe = "$env:USERPROFILE\.local\bin\claude.exe"
        [Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";$env:USERPROFILE\.local\bin", "User")
    }
}
$claudeCred = "$env:USERPROFILE\.claude\.credentials.json"
if (Test-Path $claudeCred) {
    Say "  이미 로그인되어 있습니다."
} elseif ($claudeExe) {
    Say ""
    Say "  잠시 후 검은 화면이 열립니다. 순서대로 하세요:"
    Say "    1) 방향키로 'Claude account with subscription' 을 고르고 Enter"
    Say "    2) 브라우저가 열리면 Claude 계정으로 로그인하고 'Authorize'(허용) 클릭"
    Say "    3) 화면에 코드가 보이면 복사해서 검은 화면에 붙여넣고 Enter (자동으로 넘어가기도 함)"
    Say "    4) 로그인이 끝나면 검은 화면에  /exit  (슬래시 포함) 를 입력하고 Enter → 설치가 이어집니다"
    Say "  창을 그냥 닫아도 되지만, 그러면 로그인이 안 된 채 넘어갈 수 있습니다."
    Pause-Enter "준비되면 Enter"
    & $claudeExe
    if (Test-Path $claudeCred) { Say "  Claude 로그인 완료." } else { Warn "로그인이 확인되지 않았습니다. 설치가 끝난 뒤 install.bat을 다시 실행하면 이 단계만 다시 합니다." }
} else {
    Warn "Claude Code를 설치하지 못했습니다. https://claude.ai/code 에서 설치 후 install.bat을 다시 실행하세요."
}

# ---------- 4. GPT (선택)
Head "[4/7] GPT 사용량"
Say "  GPT 숫자는 ChatGPT 에이전트 한도(Codex, ChatGPT Work)입니다. ChatGPT 채팅 한도가 아닙니다."
$providers = "claude"
$ans = Ask "Codex나 ChatGPT Work를 쓰시나요? 쓰면 Y, 채팅만 쓰면 N [Y/N]"
if ($ans -match "^[Yy]") {
    $providers = "claude,codex"
    if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            Say "  Node.js(Codex 설치에 필요)를 설치합니다 (1~2분, '허용' 창이 뜨면 예)..."
            winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements --silent | Out-Null
            $env:Path = "$env:ProgramFiles\nodejs;$env:APPDATA\npm;" + $env:Path
        }
        if (Get-Command npm -ErrorAction SilentlyContinue) {
            Say "  Codex CLI를 설치합니다..."
            npm install -g @openai/codex 2>&1 | Out-Null
            $env:Path = "$env:APPDATA\npm;" + $env:Path
        }
    }
    if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
        Warn "Codex CLI를 설치하지 못했습니다. 나중에 터미널에서  npm install -g @openai/codex  후  codex login  을 실행하세요."
    } elseif (Test-Path "$env:USERPROFILE\.codex\auth.json") {
        Say "  이미 로그인되어 있습니다."
    } else {
        Say "  브라우저가 열리면 ChatGPT 계정으로 로그인하세요."
        codex login
    }
} else {
    Say "  GPT는 숨깁니다. 나중에 위젯 우클릭 → 'GPT 표시'로 켤 수 있습니다."
    $stateFile = Join-Path $Here "widget_state.json"
    if (-not (Test-Path $stateFile)) { '{"show_gpt": false}' | Set-Content $stateFile -Encoding ASCII }
}

# ---------- 5. Win-CodexBar 설정 자동 기록
Head "[5/7] Win-CodexBar 설정"
$settings = Join-Path $env:APPDATA "CodexBar\settings.json"
if (-not (Test-Path $settings)) {
    Say "  설정 파일을 만들기 위해 CodexBar를 잠깐 켰다 끕니다 (창이 잠깐 보일 수 있음)..."
    Start-Process $app
    for ($i = 0; $i -lt 20 -and -not (Test-Path $settings); $i++) { Start-Sleep 1 }
    Stop-Process -Name codexbar -Force -ErrorAction SilentlyContinue
}
$out = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Here "configure_codexbar.ps1") -Providers $providers
if ($LASTEXITCODE -eq 0) { Say "  자동 설정 완료 (Claude 읽기 허용, 표시 항목, 트레이 자동 실행 끔)." }
else { Warn "자동 설정 실패. CodexBar 트레이 아이콘 우클릭 → Settings → 제공업체 → Claude → 'Allow reading Claude Code's credentials' 체크해 주세요." }
& $cli autostart --disable 2>&1 | Out-Null

# ---------- 6. 바로가기 / 자동 실행
Head "[6/7] 바로가기"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath("Desktop"), "AI 사용량 위젯.lnk"))
$sc.TargetPath = Join-Path $Here "toggle_widget.bat"
$sc.WorkingDirectory = $Here
$sc.IconLocation = Join-Path $env:LOCALAPPDATA "Programs\CodexBar\icon.ico"
$sc.WindowStyle = 7
$sc.Save()
Say "  바탕화면에 'AI 사용량 위젯' 바로가기를 만들었습니다 (더블클릭: 켜기/끄기)."
$ans = Ask "Windows를 켤 때 위젯도 자동으로 켤까요? [Y/N]"
if ($ans -match "^[Yy]") {
    $su = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\ai-usage-widget.bat"
    "@echo off`r`ncall `"$(Join-Path $Here 'toggle_widget.bat')`" /boot`r`n" | Set-Content $su -Encoding ASCII
    Say "  자동 실행을 켰습니다."
}

# ---------- 7. 실행
Head "[7/7] 위젯 실행"
& (Join-Path $Here "toggle_widget.bat") /start
Say ""
Say "  설치가 끝났습니다. 화면 왼쪽 위에 카드가 뜹니다 (첫 조회 5~10초)."
Say "  - 켜고 끄기: 바탕화면 'AI 사용량 위젯' 더블클릭"
Say "  - 숫자가 안 뜨면: 같은 폴더의 doctor.bat 더블클릭"
Say "  - 위젯 폴더: $Here"
Say ""
Pause-Enter "닫으려면 Enter"

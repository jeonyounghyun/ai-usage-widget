# AI Usage Widget 설치/복구 스크립트 (한글 안내). 런처: install.bat / relogin.bat / connect_gpt.bat / uninstall.bat
#   (없음)      처음 설치 (이미 된 단계는 건너뜀)
#   -Relogin    Claude 다시 로그인만
#   -Gpt        GPT 나중에 연결 (Codex CLI 설치·로그인, 위젯에 GPT 표시)
#   -Uninstall  위젯 제거 (보조 프로그램은 남김)
param([switch]$Relogin, [switch]$Gpt, [switch]$Uninstall)
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Say($t) { Write-Host $t }
function Head($t) { Write-Host ""; Write-Host ("  " + $t) -ForegroundColor Cyan }
function Warn($t) { Write-Host ("  ! " + $t) -ForegroundColor Yellow }
function Ask($q) { return (Read-Host ("  " + $q)) }
function Pause-Enter($t = "계속하려면 Enter") { [void](Read-Host ("  " + $t)) }
function Blocked($what) {
    Warn "$what 설치가 막혔거나 10분 넘게 진행되지 않습니다."
    Say "   - 회사 PC라면 '허용' 창이 안 뜨거나 설치가 차단될 수 있습니다. IT 담당자에게 '$what 설치'를 요청하세요."
    Say "   - 인터넷이 느리면 창을 그대로 두고 기다리세요. 창을 닫았다면 install.bat을 다시 실행하면 이미 된 단계는 건너뜁니다."
}

$cli = Join-Path $env:LOCALAPPDATA "Programs\CodexBar\codexbar-cli.exe"
$app = Join-Path $env:LOCALAPPDATA "Programs\CodexBar\codexbar.exe"
$claudeCred = "$env:USERPROFILE\.claude\.credentials.json"
$stateFile = Join-Path $Here "widget_state.json"

# ---------------------------------------------------------------- 공용
function Find-Python {
    foreach ($c in @(@("py", @("-3")), @("python", @()), @("python3", @()))) {
        if (Get-Command $c[0] -ErrorAction SilentlyContinue) {
            & cmd /c "$($c[0]) $($c[1] -join ' ') -c `"import sys`" >nul 2>&1"
            if ($LASTEXITCODE -eq 0) { return $c }
        }
    }
    return $null
}

function Find-Claude {
    if (Get-Command claude -ErrorAction SilentlyContinue) { return "claude" }
    if (Test-Path "$env:USERPROFILE\.local\bin\claude.exe") { return "$env:USERPROFILE\.local\bin\claude.exe" }
    return $null
}

function Claude-LoginState {
    # 로그인 파일이 있어도 만료됐을 수 있으므로 만료 시각까지 본다: ok / expired / none
    if (-not (Test-Path $claudeCred)) { return "none" }
    try {
        $j = (Get-Content $claudeCred -Raw -Encoding UTF8 | ConvertFrom-Json).claudeAiOauth
        $nowMs = [double](([DateTimeOffset]::UtcNow).ToUnixTimeMilliseconds())
        if ($j.refreshTokenExpiresAt -and [double]$j.refreshTokenExpiresAt -lt $nowMs) { return "expired" }
        if (-not $j.accessToken) { return "none" }
        return "ok"
    } catch { return "expired" }
}

function Do-ClaudeLogin([string]$reason) {
    $exe = Find-Claude
    if (-not $exe) {
        Say "  Claude 로그인 도구(Claude Code)를 설치합니다. 위젯이 Claude 사용량을 읽으려면 이 도구의 로그인이 필요합니다."
        Say "  (도구를 직접 쓸 일은 없습니다. claude.ai 채팅과 같은 한도를 씁니다)"
        try { irm https://claude.ai/install.ps1 | iex | Out-Null } catch { Warn "설치 실패: $($_.Exception.Message)" }
        if (Test-Path "$env:USERPROFILE\.local\bin\claude.exe") {
            [Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";$env:USERPROFILE\.local\bin", "User")
            $exe = "$env:USERPROFILE\.local\bin\claude.exe"
        } else { Blocked "Claude Code"; return $false }
    }
    Say ""
    Say "  $reason"
    Say "  잠시 후 검은 화면이 열립니다:"
    Say "    1) 로그인 방식을 물으면 방향키로 'Claude account with subscription' 을 고르고 Enter"
    Say "    2) 브라우저가 열리면 Claude 계정으로 로그인하고 'Authorize'(허용) 클릭"
    Say "    3) 브라우저에 코드가 보이면 복사해서 검은 화면에 붙여넣고 Enter (자동으로 넘어가기도 함)"
    Say "    4) 검은 화면에 '>' 입력창이 나타나면 로그인 완료입니다. /exit 를 입력하고 Enter → 여기로 돌아옵니다"
    Say "  이미 로그인된 상태면 1~3이 안 나오고 바로 '>' 입력창이 뜹니다. 그때는 /exit 만 입력하세요."
    Say "  (다른 계정으로 바꾸려면 '>' 입력창에 /login 을 입력)"
    Pause-Enter "준비되면 Enter"
    & $exe
    $st = Claude-LoginState
    if ($st -eq "ok") { Say "  Claude 로그인 완료."; return $true }
    Warn "로그인이 확인되지 않았습니다 (상태: $st). 나중에 relogin.bat 을 더블클릭하면 이 단계만 다시 합니다."
    return $false
}

function Configure-CodexBar([string]$providers) {
    if (-not (Test-Path $cli)) { return $false }
    $settings = Join-Path $env:APPDATA "CodexBar\settings.json"
    if (-not (Test-Path $settings)) {
        # 새로 깐 CodexBar는 앱을 켜도 설정 파일을 만들지 않는다(값을 바꿔야 저장). CLI로 제공자를 켜면 파일이 생긴다.
        & $cli config enable claude 2>&1 | Out-Null
    }
    if (-not (Test-Path $settings)) {
        Say "  설정 파일을 만들기 위해 CodexBar를 잠깐 켰다 끕니다 (창이 잠깐 보일 수 있음)..."
        Start-Process $app
        for ($i = 0; $i -lt 20 -and -not (Test-Path $settings); $i++) { Start-Sleep 1 }
        Stop-Process -Name codexbar -Force -ErrorAction SilentlyContinue
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Here "configure_codexbar.ps1") -Providers $providers | Out-Null
    $ok = ($LASTEXITCODE -eq 0)
    & $cli autostart --disable 2>&1 | Out-Null
    return $ok
}

function Set-WidgetState([string]$key, $value) {
    $obj = @{}
    if (Test-Path $stateFile) { try { $obj = Get-Content $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $obj = @{} } }
    if ($obj -is [System.Management.Automation.PSCustomObject]) {
        if ($null -ne $obj.PSObject.Properties[$key]) { $obj.$key = $value } else { $obj | Add-Member -NotePropertyName $key -NotePropertyValue $value }
    } else { $obj = [PSCustomObject]@{ $key = $value } }
    ($obj | ConvertTo-Json -Depth 10 -Compress) | Set-Content $stateFile -Encoding UTF8
}

function Do-GptConnect {
    if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            Say "  GPT 로그인 도구(Codex CLI)를 설치하려면 Node.js가 먼저 필요합니다. 설치합니다 (1~2분, '허용' 창이 뜨면 예)..."
            winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements --silent | Out-Null
            $env:Path = "$env:ProgramFiles\nodejs;$env:APPDATA\npm;" + $env:Path
        }
        if (Get-Command npm -ErrorAction SilentlyContinue) {
            Say "  GPT 로그인 도구(Codex CLI)를 설치합니다..."
            npm install -g @openai/codex 2>&1 | Out-Null
            $env:Path = "$env:APPDATA\npm;" + $env:Path
        }
    }
    if (-not (Get-Command codex -ErrorAction SilentlyContinue)) { Blocked "Node.js / Codex CLI"; return $false }
    if (Test-Path "$env:USERPROFILE\.codex\auth.json") {
        Say "  GPT는 이미 로그인되어 있습니다."
    } else {
        Say "  브라우저가 열리면 ChatGPT 계정으로 로그인하세요. 끝나면 이 창으로 자동으로 돌아옵니다."
        codex login
    }
    if (-not (Test-Path "$env:USERPROFILE\.codex\auth.json")) { Warn "GPT 로그인이 확인되지 않았습니다. 나중에 connect_gpt.bat 을 다시 실행하세요."; return $false }
    Set-WidgetState "show_gpt" $true
    if ($Gpt) { [void](Configure-CodexBar "claude,codex") }   # 처음 설치 때는 [5/7]에서 한 번에 설정
    Say "  GPT 연결 완료. 위젯을 켜면 GPT 칸이 나타납니다 (켜져 있으면 우클릭 → 지금 새로고침)."
    return $true
}

# ================================================================ 모드: 다시 로그인
if ($Relogin) {
    Head "Claude 다시 로그인"
    $st = Claude-LoginState
    if ($st -eq "ok") { Say "  로그인 파일은 유효합니다. 그래도 위젯이 '재로그인 필요'라고 하면 아래를 진행하세요." }
    [void](Do-ClaudeLogin "Claude 로그인을 다시 합니다.")
    Say "  위젯이 켜져 있으면 우클릭 → '지금 새로고침'을 누르세요."
    Pause-Enter "닫으려면 Enter"; exit 0
}

# ================================================================ 모드: GPT 연결
if ($Gpt) {
    Head "GPT 연결"
    Say "  GPT 숫자는 Codex·ChatGPT Work(에이전트) 사용량입니다. 일반 채팅은 한도가 없어 해당 없습니다."
    [void](Do-GptConnect)
    Pause-Enter "닫으려면 Enter"; exit 0
}

# ================================================================ 모드: 제거
if ($Uninstall) {
    Head "AI 사용량 위젯 제거"
    Say "  다음을 제거합니다: 위젯 실행 중지, 바탕화면 바로가기, Windows 시작 시 자동 실행, 위젯 폴더."
    Say "  다음은 남깁니다 (다른 용도로도 쓰일 수 있음): Python, Win-CodexBar, Claude Code, Node.js/Codex CLI."
    Say "  이것들도 지우려면 Windows 설정 → 앱 → 설치된 앱에서 각각 제거하세요."
    $ans = Ask "계속할까요? [Y/N]"
    if ($ans -notmatch "^[Yy]") { Say "  취소했습니다."; Pause-Enter "닫으려면 Enter"; exit 0 }
    & (Join-Path $Here "toggle_widget.bat") /stop
    Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "AI 사용량 위젯.lnk") -ErrorAction SilentlyContinue
    Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "AI Usage Widget.lnk") -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\ai-usage-widget.bat") -ErrorAction SilentlyContinue
    Say "  바로가기와 자동 실행을 제거했습니다."
    $ans = Ask "위젯 폴더($Here)도 지울까요? 설정과 로그가 함께 지워집니다 [Y/N]"
    if ($ans -match "^[Yy]") {
        Say "  이 창을 닫으면 폴더가 삭제됩니다."
        Start-Process cmd -ArgumentList "/c ping -n 3 127.0.0.1 >nul & rmdir /s /q `"$Here`"" -WindowStyle Hidden
    }
    Say "  제거가 끝났습니다."
    Pause-Enter "닫으려면 Enter"; exit 0
}

# ================================================================ 모드: 처음 설치
Say ""
Say "  =============================================="
Say "    AI 사용량 위젯 설치"
Say "  =============================================="
Say ""
Say "  이 위젯이 보여주는 것:"
Say "   - Claude: claude.ai 채팅 사용량 (Claude Code와 같은 한도)"
Say "   - GPT: Codex·ChatGPT Work 사용량 (일반 채팅은 한도가 없어 해당 없음)"
Say ""
Say "  설치 중 이런 창이 뜨면:"
Say "   - 파란색 'Windows의 PC 보호' → '추가 정보' → '실행'"
Say "   - '이 앱이 디바이스를 변경하도록 허용하시겠어요?' → '예'"
Say "  이미 된 단계는 자동으로 건너뛰므로, 중간에 닫혔으면 install.bat을 다시 실행하면 됩니다."
Say ""

# ---------- 0. 영구 폴더로 이동 (Downloads/임시 폴더에서 실행하면 나중에 지워져 깨짐)
$tempish = @($env:TEMP, (Join-Path $env:USERPROFILE "Downloads"), [Environment]::GetFolderPath("Desktop"))
$permanent = Join-Path $env:LOCALAPPDATA "Programs\ai-usage-widget"
if ($tempish | Where-Object { $Here.StartsWith($_, [System.StringComparison]::OrdinalIgnoreCase) }) {
    Head "[0/7] 설치 폴더"
    Say "  지금 폴더는 나중에 지워질 수 있는 위치입니다. 위젯 파일을 아래로 복사해서 거기서 설치합니다:"
    Say "  $permanent"
    New-Item -ItemType Directory -Force $permanent | Out-Null
    Get-ChildItem $Here -File | ForEach-Object { Copy-Item $_.FullName $permanent -Force }
    if (Test-Path (Join-Path $Here "docs")) { Copy-Item (Join-Path $Here "docs") $permanent -Recurse -Force }
    $Here = $permanent
    $stateFile = Join-Path $Here "widget_state.json"
    Say "  (원래 압축 푼 폴더는 지워도 됩니다)"
}
Set-Location $Here

# ---------- 1. Python
Head "[1/7] Python (위젯을 움직이는 엔진)"
$found = Find-Python
if (-not $found) {
    Say "  설치합니다 (1~2분)..."
    winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements --silent | Out-Null
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    $found = Find-Python
}
if (-not $found) { Blocked "Python"; Say "  (직접 설치: https://python.org → Download → 설치 화면에서 'Add python.exe to PATH' 체크)"; Pause-Enter; exit 1 }
$py = $found[0]; $pyArgs = $found[1]
Say "  확인됨. 그림 부품(Pillow) 설치..."
& $py @pyArgs -m pip install --user --quiet --disable-pip-version-check pillow
if ($LASTEXITCODE -ne 0) { Warn "그림 부품 설치 실패. 인터넷 연결을 확인한 뒤 install.bat을 다시 실행하세요."; Pause-Enter; exit 1 }

# ---------- 2. Win-CodexBar
Head "[2/7] Win-CodexBar (사용량을 읽어 오는 도구)"
if (-not (Test-Path $cli)) {
    Say "  설치합니다..."
    winget install -e --id Finesssee.Win-CodexBar --accept-package-agreements --accept-source-agreements --silent | Out-Null
}
if (-not (Test-Path $cli)) { Blocked "Win-CodexBar"; Say "  (직접 설치: https://github.com/nesszer/Win-CodexBar/releases)"; Pause-Enter; exit 1 }
Say "  확인됨."

# ---------- 3. Claude 로그인
Head "[3/7] Claude 로그인"
$st = Claude-LoginState
if ($st -eq "ok") { Say "  이미 로그인되어 있습니다." }
elseif ($st -eq "expired") { [void](Do-ClaudeLogin "로그인이 만료되어 다시 로그인합니다.") }
else { [void](Do-ClaudeLogin "위젯이 Claude 사용량을 읽으려면 한 번 로그인이 필요합니다.") }

# ---------- 4. GPT (선택)
Head "[4/7] GPT 사용량"
Say "  GPT 숫자는 Codex·ChatGPT Work(에이전트) 사용량입니다. 일반 채팅은 한도가 없어 해당 없습니다."
$providers = "claude"
$ans = Ask "Codex나 ChatGPT Work를 쓰시나요? 쓰면 Y, 채팅만 쓰면 N [Y/N]"
if ($ans -match "^[Yy]") {
    if (Do-GptConnect) { $providers = "claude,codex" }
} else {
    Say "  GPT는 숨깁니다. 나중에 connect_gpt.bat (또는 위젯 우클릭 → 문제 해결 → GPT 연결하기)로 켤 수 있습니다."
    Set-WidgetState "show_gpt" $false
}

# ---------- 5. Win-CodexBar 설정 자동 기록
Head "[5/7] Win-CodexBar 설정"
if (Configure-CodexBar $providers) { Say "  자동 설정 완료 (Claude 읽기 허용, 표시 항목, 트레이 자동 실행 끔)." }
else { Warn "자동 설정 실패. 위젯 우클릭 → 문제 해결 → 점검 실행 결과를 설치해 준 사람에게 보여주세요." }

# ---------- 6. 바로가기 / 자동 실행
Head "[6/7] 바로가기"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath("Desktop"), "AI 사용량 위젯.lnk"))
$sc.TargetPath = Join-Path $Here "toggle_widget.bat"
$sc.WorkingDirectory = $Here
$sc.IconLocation = Join-Path $env:LOCALAPPDATA "Programs\CodexBar\icon.ico"
$sc.WindowStyle = 7
$sc.Save()
Say "  바탕화면에 'AI 사용량 위젯' 바로가기를 만들었습니다 (더블클릭: 켜기/다시 보이기. 끄기는 위젯 우클릭 → 종료)."
$ans = Ask "Windows를 켤 때 위젯도 자동으로 켤까요? [Y/N]"
if ($ans -match "^[Yy]") {
    $su = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\ai-usage-widget.bat"
    "@echo off`r`ncall `"$(Join-Path $Here 'toggle_widget.bat')`" /boot`r`n" | Set-Content $su -Encoding ASCII
    Say "  자동 실행을 켰습니다. (끄기: 위젯 우클릭 → 'Windows 시작 시 자동 실행' 해제)"
}

# ---------- 7. 실행
Head "[7/7] 위젯 실행"
& (Join-Path $Here "toggle_widget.bat") /start
Say ""
Say "  설치가 끝났습니다. 화면 왼쪽 위에 카드가 뜹니다 (첫 조회 5~10초)."
Say "  - 다시 보이기: 바탕화면 'AI 사용량 위젯' 더블클릭"
Say "  - 문제가 생기면: 위젯 우클릭 → 문제 해결 (점검 실행 / 다시 로그인 / GPT 연결 / 폴더 열기)"
Say "  - 위젯 폴더: $Here"
Say ""
Pause-Enter "닫으려면 Enter"

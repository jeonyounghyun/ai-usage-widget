# Win-CodexBar 설정을 자동으로 맞춘다 (install.bat이 호출).
#  - Claude 토큰 읽기 허용 (claude_allow_reading_claude_code_credentials = true)
#  - 표시할 제공자만 켬 (enabled_providers)
#  - 트레이 앱 부팅 자동 실행/플로팅 바 끔 (위젯과 중복 조회 방지)
# 설정 파일은 사용자 DPAPI로 암호화돼 있어 같은 사용자 계정에서만 읽고 쓸 수 있다.
# JSON을 통째로 재조립하면 CodexBar가 못 읽는 경우가 있어, 원문에서 해당 값만 치환한다.
# 사용: powershell -ExecutionPolicy Bypass -File configure_codexbar.ps1 [-Providers claude,codex] [-Path <settings.json>]
param(
    [string]$Providers = "claude,codex",
    [string]$Path = "$env:APPDATA\CodexBar\settings.json"
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Security
$list = @($Providers -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })

if (-not (Test-Path $Path)) { Write-Output "settings.json not found: $Path"; exit 2 }
$envelope = Get-Content $Path -Raw -Encoding UTF8 | ConvertFrom-Json
if ($envelope.protection -ne "windows-dpapi-user") { Write-Output "unexpected protection: $($envelope.protection)"; exit 3 }
$plain = [System.Security.Cryptography.ProtectedData]::Unprotect([Convert]::FromBase64String($envelope.payload), $null, "CurrentUser")
$json = [System.Text.Encoding]::UTF8.GetString($plain)

function Set-Bool([string]$text, [string]$key, [bool]$value) {
    $v = if ($value) { "true" } else { "false" }
    $pattern = '("' + [regex]::Escape($key) + '"\s*:\s*)(true|false)'
    if ($text -match $pattern) { return [regex]::Replace($text, $pattern, ('${1}' + $v), 1) }
    # 키가 없으면 맨 앞에 추가
    return $text -replace '^\s*\{', ('{' + "`n  `"$key`": $v,")
}
$json = Set-Bool $json "claude_allow_reading_claude_code_credentials" $true
$json = Set-Bool $json "start_at_login" $false
$json = Set-Bool $json "float_bar_enabled" $false
$arr = '"enabled_providers": [' + (($list | ForEach-Object { "`n    `"$_`"" }) -join ",") + "`n  ]"
$provPattern = '"enabled_providers"\s*:\s*\[[^\]]*\]'
if ($json -match $provPattern) { $json = [regex]::Replace($json, $provPattern, $arr.Replace('$', '$$'), 1) }
else { $json = $json -replace '^\s*\{', ('{' + "`n  " + $arr + ",") }

$cipher = [System.Security.Cryptography.ProtectedData]::Protect([System.Text.Encoding]::UTF8.GetBytes($json), $null, "CurrentUser")
$payload = [Convert]::ToBase64String($cipher)
# 봉투는 원문 형식을 유지하고, BOM 없는 UTF-8로 저장 (BOM이 붙으면 CodexBar가 파일을 못 읽음)
$raw = Get-Content $Path -Raw -Encoding UTF8
$raw = [regex]::Replace($raw, '("payload"\s*:\s*")[^"]*(")', ('${1}' + $payload + '${2}'), 1)
Copy-Item $Path "$Path.bak" -Force
[System.IO.File]::WriteAllText($Path, $raw, (New-Object System.Text.UTF8Encoding($false)))
Write-Output ("configured: providers=" + ($list -join ",") + ", claude credentials allowed, autostart/floatbar off")

# 배포 ZIP 생성: 설치에 필요한 파일만 담는다. (개인 캐시/로그 제외)
# 사용: powershell -ExecutionPolicy Bypass -File make_release.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$ver = (Select-String -Path usage_widget.py -Pattern '^VERSION = "([^"]+)"').Matches[0].Groups[1].Value
$name = "ai-usage-widget-v$ver"
$stage = Join-Path $env:TEMP $name
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory $stage | Out-Null
Copy-Item install.bat, toggle_widget.bat, usage_widget.py, toast.ps1, README.md, LICENSE $stage
New-Item -ItemType Directory (Join-Path $stage "docs") | Out-Null
Copy-Item docs\*.png (Join-Path $stage "docs")
New-Item -ItemType Directory dist -Force | Out-Null
$zip = Join-Path (Resolve-Path dist) "$name.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "$stage\*" -DestinationPath $zip
Remove-Item $stage -Recurse -Force
"created: $zip"

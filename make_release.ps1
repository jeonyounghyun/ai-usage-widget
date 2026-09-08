# 배포 ZIP 생성: 설치에 필요한 파일만 담는다. (개인 캐시/로그 제외)
# ZIP 안 경로 구분자는 반드시 '/' (Compress-Archive는 '\'를 넣어 다른 도구에서 폴더가 깨짐) → Python zipfile 사용
# 사용: powershell -ExecutionPolicy Bypass -File make_release.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$ver = (Select-String -Path usage_widget.py -Pattern '^VERSION = "([^"]+)"').Matches[0].Groups[1].Value
$name = "ai-usage-widget-v$ver"
New-Item -ItemType Directory dist -Force | Out-Null
$zip = Join-Path (Resolve-Path dist) "$name.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
$files = @("install.bat", "install.ps1", "configure_codexbar.ps1", "toggle_widget.bat", "usage_widget.py", "toast.ps1",
           "doctor.py", "doctor.bat", "README.md", "LICENSE") + (Get-ChildItem docs -Filter *.png | ForEach-Object { "docs/" + $_.Name })
$py = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
$list = ($files -join ";")
& $py -c "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1],'w',zipfile.ZIP_DEFLATED); [z.write(f, f) for f in sys.argv[2].split(';')]; z.close()" $zip $list
"created: $zip"

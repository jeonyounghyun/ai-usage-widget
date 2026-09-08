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
$files = @("처음_읽어주세요.txt", "install.bat", "install.ps1", "configure_codexbar.ps1", "toggle_widget.bat", "usage_widget.py", "toast.ps1",
           "relogin.bat", "connect_gpt.bat", "uninstall.bat", "doctor.py", "doctor.bat", "README.md", "LICENSE") + (Get-ChildItem docs -Filter *.png | ForEach-Object { "docs/" + $_.Name })
# py 런처만 있고 Python이 없는 경우가 있어 실제 실행되는 것을 고른다
$py = $null; $pyArgs = @()
$prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"   # 런처의 stderr 출력이 스크립트를 멈추지 않게
foreach ($c in @(@("py", @("-3")), @("python", @()))) {
    if (Get-Command $c[0] -ErrorAction SilentlyContinue) {
        & cmd /c "$($c[0]) $($c[1] -join ' ') -c `"import sys`" >nul 2>&1"
        if ($LASTEXITCODE -eq 0) { $py = $c[0]; $pyArgs = $c[1]; break }
    }
}
$ErrorActionPreference = $prev
if (-not $py) { throw "Python not found" }
# 파일 목록은 한글 파일명이 명령줄에서 깨지지 않도록 UTF-8 파일로 넘긴다
$listFile = Join-Path $env:TEMP "aiw_release_files.txt"
[System.IO.File]::WriteAllLines($listFile, $files, (New-Object System.Text.UTF8Encoding($false)))
& $py @pyArgs -c "import zipfile,sys; names=[l.strip() for l in open(sys.argv[2],encoding='utf-8') if l.strip()]; z=zipfile.ZipFile(sys.argv[1],'w',zipfile.ZIP_DEFLATED); [z.write(f, f) for f in names]; z.close()" $zip $listFile
Remove-Item $listFile -ErrorAction SilentlyContinue
if (-not (Test-Path $zip)) { throw "zip not created" }
"created: $zip"

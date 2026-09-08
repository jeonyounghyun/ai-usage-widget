"""
AI Usage Widget 점검 도구.
설치 후 위젯에 숫자가 안 뜰 때 실행하면 어디서 막혔는지와 해결 방법을 알려준다.
사용: doctor.bat 더블클릭 (또는 python doctor.py)
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

OK, BAD, WARN = "[OK] ", "[X]  ", "[!]  "
HOME = Path.home()
LOCAL = Path(os.environ.get("LOCALAPPDATA", HOME / "AppData" / "Local"))
CLI = LOCAL / "Programs" / "CodexBar" / "codexbar-cli.exe"
CLAUDE_CRED = HOME / ".claude" / ".credentials.json"
CODEX_AUTH = HOME / ".codex" / "auth.json"

FIXES = {
    "cred_off": "Win-CodexBar 트레이 아이콘 우클릭 -> Settings -> 제공업체(Providers) -> Claude -> "
                "'Allow reading Claude Code's credentials' 체크",
    "expired": "로그인이 만료됨. install.bat을 다시 실행하면 로그인 화면이 뜸 (또는 터미널에서  claude  실행)",
    "rate": "조회가 너무 잦아 잠시 차단됨. 5~10분 뒤 자동 회복. Win-CodexBar 트레이 앱이 켜져 있으면 종료",
    "claude_login": "Claude 로그인이 없음. install.bat을 다시 실행하면 설치와 로그인 화면이 뜸 (Claude account with subscription 선택)",
    "codex_login": "Codex CLI 로그인:  codex login   (Codex를 안 쓰면 위젯 우클릭 -> 'GPT(Codex) 표시' 해제)",
    "cli": "Win-CodexBar 설치:  winget install Finesssee.Win-CodexBar   (또는 https://github.com/nesszer/Win-CodexBar/releases)",
}


def section(title):
    print()
    print("=" * 60)
    print(" " + title)
    print("=" * 60)


def check_python():
    section("1. Python / Pillow")
    print(OK + f"Python {sys.version.split()[0]}  ({sys.executable})")
    try:
        import PIL  # noqa: F401
        print(OK + f"Pillow {PIL.__version__}")
    except ImportError:
        print(BAD + "Pillow 없음  ->  pip install pillow")
    try:
        import tkinter  # noqa: F401
        print(OK + "tkinter")
    except ImportError:
        print(BAD + "tkinter 없음  ->  Python을 python.org 설치본으로 다시 설치 (tcl/tk 포함)")


def check_cli():
    section("2. Win-CodexBar CLI")
    if CLI.exists():
        print(OK + str(CLI))
        return True
    print(BAD + f"{CLI} 없음")
    print("     " + FIXES["cli"])
    return False


def check_files():
    section("3. 로그인 파일")
    ok_claude = CLAUDE_CRED.exists()
    ok_codex = CODEX_AUTH.exists()
    if ok_claude:
        try:
            d = json.loads(CLAUDE_CRED.read_text(encoding="utf-8")).get("claudeAiOauth", {})
            sub = d.get("subscriptionType") or "?"
            print(OK + f"Claude 토큰 파일 있음 (구독: {sub})")
            if sub in ("?", "", None):
                print(WARN + "구독 정보가 없음. API 키 방식 로그인이면 한도가 표시되지 않음 -> " + FIXES["claude_login"])
        except Exception as ex:  # noqa: BLE001
            print(WARN + f"Claude 토큰 파일은 있으나 읽기 실패: {ex}")
    else:
        print(BAD + f"Claude 토큰 파일 없음 ({CLAUDE_CRED})")
        print("     " + FIXES["claude_login"])
    if ok_codex:
        print(OK + "Codex 토큰 파일 있음")
    else:
        print(WARN + f"Codex 토큰 파일 없음 ({CODEX_AUTH}) - Codex를 안 쓰면 무시")
        print("     " + FIXES["codex_login"])
    which = shutil.which("claude")
    print((OK if which else WARN) + ("claude 명령 위치: " + which if which else
          "claude 명령을 PATH에서 못 찾음 (Claude Code 미설치이거나 PATH 미등록). 위젯 동작에는 필수 아님"))
    return ok_claude, ok_codex


def diagnose(msg):
    m = msg.lower()
    if "reading claude code's credentials is off" in m or "credentials is off" in m:
        return FIXES["cred_off"]
    if "expired" in m or "401" in m or "re-authenticate" in m:
        return FIXES["expired"]
    if "rate limit" in m:
        return FIXES["rate"]
    if "not logged in" in m or "no auth" in m or "auth.json" in m:
        return FIXES["codex_login"]
    if "no cookies" in m or "app-bound" in m:
        return "브라우저 쿠키 관련 안내는 무시해도 됨 (위젯은 쿠키를 쓰지 않음)"
    return "알 수 없는 오류. widget.log 와 함께 문의"


def check_usage():
    section("4. 실제 조회 (위젯과 같은 방식: --source oauth)")
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        out = subprocess.run([str(CLI), "usage", "-p", "both", "--source", "oauth", "--json", "--no-color"],
                             capture_output=True, text=True, timeout=90, creationflags=flags,
                             encoding="utf-8", errors="replace")
    except Exception as ex:  # noqa: BLE001
        print(BAD + f"CLI 실행 실패: {ex}")
        return
    if not out.stdout.strip():
        print(BAD + "CLI가 결과를 주지 않음")
        print("     stderr: " + out.stderr.strip()[-300:])
        return
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        print(BAD + "CLI 출력이 JSON이 아님: " + out.stdout[:200])
        return
    names = {"claude": "Claude", "codex": "GPT(Codex)"}
    for item in data:
        prov = names.get(item.get("provider"), item.get("provider"))
        usage = item.get("usage") or {}
        if usage:
            p5 = (usage.get("primary") or {}).get("used_percent")
            p7 = (usage.get("secondary") or {}).get("used_percent")
            print(OK + f"{prov}: 5시간 {p5}% / 7일 {p7}%  ({usage.get('login_method', '')})")
        else:
            err = item.get("error") or "no data"
            print(BAD + f"{prov}: {err[:220]}")
            print("     해결: " + diagnose(err))


def main():
    print("AI Usage Widget 점검 도구")
    check_python()
    if check_cli():
        check_files()
        check_usage()
    else:
        check_files()
    section("끝")
    print("[X] 항목을 위 '해결' 안내대로 처리한 뒤 위젯을 다시 켜세요 (바탕화면 바로가기).")
    print("그래도 안 되면 위젯 폴더의 widget.log 를 함께 보내주세요.")


if __name__ == "__main__":
    try:
        main()
    finally:
        if os.environ.get("DOCTOR_PAUSE") != "0":
            try:
                input("\n닫으려면 Enter...")
            except EOFError:
                pass

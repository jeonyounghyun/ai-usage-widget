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
    "cred_off": "사용량 읽기 허용이 꺼져 있음 -> 이 폴더의 install.bat 을 더블클릭 (설정을 자동으로 고침, 이미 된 단계는 건너뜀)",
    "expired": "Claude 로그인이 만료됨 -> 이 폴더의 relogin.bat 을 더블클릭 (또는 위젯 우클릭 -> 문제 해결 -> Claude 다시 로그인)",
    "rate": "조회가 너무 잦아 잠시 막힘 -> 5~10분 뒤 저절로 풀림. 작업표시줄 시계 옆에 CodexBar 아이콘이 있으면 우클릭 -> Quit",
    "claude_login": "Claude 로그인이 없음 -> 이 폴더의 relogin.bat 을 더블클릭 (Claude account with subscription 선택)",
    "codex_login": "GPT 로그인이 없거나 거부됨 -> 이 폴더의 connect_gpt.bat 을 더블클릭 (다시 로그인함). GPT를 안 보면 위젯 우클릭 -> 'GPT 표시' 해제",
    "cli": "사용량 읽는 도구(Win-CodexBar)가 없음 -> 이 폴더의 install.bat 을 더블클릭",
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
        print(BAD + "그림 부품(Pillow) 없음 -> 이 폴더의 install.bat 을 더블클릭")
    try:
        import tkinter  # noqa: F401
        print(OK + "tkinter")
    except ImportError:
        print(BAD + "화면 부품(tkinter) 없음 -> Python을 python.org 에서 다시 설치 (기본 설정 그대로)")


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
    print((OK if which else WARN) + ("Claude 로그인 도구 위치: " + which if which else
          "Claude 로그인 도구(Claude Code)를 못 찾음. 위젯 동작에는 필수 아님 (로그인 파일만 있으면 됨)"))
    return ok_claude, ok_codex


def diagnose(msg):
    m = msg.lower()
    if "reading claude code's credentials is off" in m or "credentials is off" in m:
        return FIXES["cred_off"]
    if "expired" in m or "401" in m or "re-authenticate" in m:
        return FIXES["expired"]
    if "rate limit" in m:
        return FIXES["rate"]
    if "not logged in" in m or "no auth" in m or "auth.json" in m or "authentication required" in m or "account not found" in m:
        return FIXES["codex_login"]
    if "no cookies" in m or "app-bound" in m:
        return "브라우저 쿠키 관련 안내는 무시해도 됨 (위젯은 쿠키를 쓰지 않음)"
    return "알 수 없는 오류 -> 이 화면을 캡처해서 설치해 준 사람에게 보여주세요"


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


def check_widget():
    """위젯이 왜 안 뜨는지: 바로가기가 쓸 pythonw, 실행 중인지, 마지막 로그."""
    section("5. 위젯 실행 상태")
    here = Path(__file__).resolve().parent
    rec = here / "pythonw.txt"
    pyw = rec.read_text(encoding="utf-8").strip() if rec.exists() else ""
    if pyw and Path(pyw).exists():
        print(OK + f"위젯 실행용 pythonw: {pyw}")
    else:
        cand = Path(sys.executable).with_name("pythonw.exe")
        if cand.exists():
            rec.write_text(str(cand), encoding="utf-8")
            print(OK + f"위젯 실행용 pythonw 기록함: {cand}")
        else:
            print(BAD + "pythonw.exe 를 찾지 못함 -> 이 폴더의 install.bat 을 더블클릭")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*usage_widget*' } | Measure-Object | Select-Object -Expand Count"],
                             capture_output=True, text=True, timeout=30)
        n = int((out.stdout or "0").strip() or 0)
    except Exception:  # noqa: BLE001
        n = -1
    if n > 0:
        print(OK + "위젯이 실행 중 (안 보이면 바탕화면 'AI 사용량 위젯' 더블클릭 -> 앞으로 나옴)")
    elif n == 0:
        print(BAD + "위젯이 꺼져 있음 -> 바탕화면 'AI 사용량 위젯' 더블클릭. 그래도 안 뜨면 아래 로그를 캡처")
    log = here / "widget.log"
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
        print("     마지막 로그:")
        for ln in lines:
            print("       " + ln)
    else:
        print("     widget.log 없음 (위젯이 한 번도 안 켜졌음 = Python 실행 문제일 가능성)")


def main():
    print("AI Usage Widget 점검 도구")
    check_python()
    if check_cli():
        check_files()
        check_usage()
    else:
        check_files()
    check_widget()
    section("끝")
    print("[X] 항목을 위 '해결' 안내대로 처리한 뒤 바탕화면 'AI 사용량 위젯'을 더블클릭하세요.")
    print("그래도 안 되면 이 화면을 캡처해서 설치해 준 사람에게 보여주세요.")


if __name__ == "__main__":
    try:
        main()
    finally:
        if os.environ.get("DOCTOR_PAUSE") != "0":
            try:
                input("\n닫으려면 Enter...")
            except EOFError:
                pass

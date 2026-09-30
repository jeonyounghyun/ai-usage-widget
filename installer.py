"""exe 설치/복구 창. AIUsageWidget.exe 하나로 설치·재로그인·GPT 연결·제거를 한다 (install.ps1을 옮긴 것).

  exe를 설치 폴더 밖에서 실행      → 설치 창 (자기 자신을 설치 폴더로 복사 후 진행)
  AIUsageWidget.exe --setup        → 설치 창 (이미 된 단계는 건너뜀)
  AIUsageWidget.exe --relogin      → Claude 다시 로그인만
  AIUsageWidget.exe --gpt          → GPT 연결만
  AIUsageWidget.exe --uninstall    → 제거
테스트용: 환경변수 AIW_SETUP_ANSWERS="gpt=y,autostart=y,login=skip" 가 있으면 질문에 자동으로 답한다.
"""
import base64
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import queue
import threading
import time
import tkinter as tk
import webbrowser
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox

from hidden_console import HiddenConsole, clean_env

LOCAL = Path(os.environ["LOCALAPPDATA"])
INSTALL_DIR = LOCAL / "Programs" / "ai-usage-widget"
EXE_NAME = "AIUsageWidget.exe"
INSTALLED_EXE = INSTALL_DIR / EXE_NAME
STATE_FILE = INSTALL_DIR / "widget_state.json"
QUIT_FLAG = INSTALL_DIR / "quit.flag"          # 실행 중인 위젯에게 "꺼져 달라"는 신호 (위젯이 1초마다 확인)
CLI = LOCAL / "Programs" / "CodexBar" / "codexbar-cli.exe"
CODEXBAR_APP = LOCAL / "Programs" / "CodexBar" / "codexbar.exe"
CODEXBAR_SETTINGS = Path(os.environ["APPDATA"]) / "CodexBar" / "settings.json"
CLAUDE_CRED = Path.home() / ".claude" / ".credentials.json"
CODEX_AUTH = Path.home() / ".codex" / "auth.json"
DESKTOP_LNK = "AI 사용량 위젯.lnk"
START_MENU_LNK = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / DESKTOP_LNK
STARTUP_BAT = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "ai-usage-widget.bat"
NO_WINDOW = 0x08000000
NEW_CONSOLE = 0x00000010
DETACHED = 0x00000008 | 0x00000200

CARD, EDGE, INK, SOFT, ACCENT = "#fff8f1", "#f0e1d2", "#4a3f3a", "#a3928a", "#f28c6b"
OK_C, WARN_C, RUN_C, TODO_C = "#7fd1a8", "#f8c66d", "#f28c6b", "#d9cfc7"
FONT = "Malgun Gothic"
SETUP_LOG = INSTALL_DIR / "setup.log"


def slog(msg):
    """설치 창에서 일어난 일을 setup.log에 남긴다 (문제 생겼을 때 이 파일을 보면 됨)."""
    try:
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        with open(SETUP_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


ANSWERS = dict(kv.split("=", 1) for kv in os.environ.get("AIW_SETUP_ANSWERS", "").split(",") if "=" in kv)


# ---------------------------------------------------------------- 공용 도구
def run(cmd, timeout=None):
    """창 없이 실행하고 (종료코드, 출력)을 돌려준다."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as ex:
        return -1, str(ex)


def powershell(script, timeout=None):
    """한글이 섞인 PowerShell 명령을 깨지지 않게 실행 (-EncodedCommand)."""
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    return run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc], timeout)


def add_path(*dirs):
    """이 프로세스의 PATH에 폴더 추가 (방금 설치한 도구를 바로 찾기 위해)."""
    cur = os.environ.get("PATH", "")
    for d in dirs:
        if d and d.lower() not in cur.lower():
            cur = d + os.pathsep + cur
    os.environ["PATH"] = cur


def find_tool(name):
    """claude / codex / npm 실행 파일. npm 설치본은 .cmd, 공식 설치본은 .exe."""
    extra = {"claude": [Path.home() / ".local" / "bin" / "claude.exe"]}.get(name, [])
    for p in extra:
        if p.exists():
            return str(p)
    return shutil.which(name)


def console_cmd(exe, *args, title="", pause=False):
    """로그인 도구를 새 CMD 창에서 실행하고 끝날 때까지 기다린다 (브라우저 로그인·코드 붙여넣기용).
    pause: 끝나도 창을 닫지 않고 키 입력을 기다림 (오류 문구를 읽을 수 있게)."""
    inner = " ".join([f'"{exe}"'] + list(args)) + (" & pause" if pause else "")
    cmd = f'cmd /c "title {title} & {inner}"'
    return subprocess.Popen(cmd, creationflags=NEW_CONSOLE, env=clean_env()).wait()


def claude_login_state():
    """ok / expired / none (로그인 파일과 만료 시각 기준)."""
    try:
        o = json.loads(CLAUDE_CRED.read_text(encoding="utf-8"))["claudeAiOauth"]
    except FileNotFoundError:
        return "none"
    except Exception:  # noqa: BLE001
        return "expired"
    exp = o.get("refreshTokenExpiresAt")
    if exp and float(exp) < time.time() * 1000:
        return "expired"
    return "ok" if o.get("accessToken") else "none"


def probe(provider):
    """CodexBar로 실제 조회. 성공이면 '', 실패면 오류 문구."""
    if not CLI.exists():
        return "cli missing"
    code, out = run([str(CLI), "usage", "-p", provider, "--source", "oauth", "--json", "--no-color"], timeout=90)
    m = re.search(r'"error"\s*:\s*"((?:[^"\\]|\\.)*)"', out)
    if m:
        return m.group(1)
    return "" if '"used_percent"' in out else "no data"


def set_state(key, value):
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        st = {}
    st[key] = value
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- CodexBar 설정 (configure_codexbar.ps1을 옮김)
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data, protect):
    """현재 사용자 DPAPI로 암호화/복호화 (CodexBar 설정 파일은 이 방식으로 보호됨)."""
    crypt = ctypes.windll.crypt32
    buf = ctypes.create_string_buffer(data, len(data))
    src, dst = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), _Blob()
    fn = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(dst)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(dst.pbData, dst.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(dst.pbData)


def configure_codexbar(providers):
    """Claude 토큰 읽기 허용, 표시 제공자, 트레이 자동 실행·플로팅 바 끔. 값만 바꾸고 봉투 형식은 그대로 (재조립하면 CodexBar가 못 읽음)."""
    if not CLI.exists():
        return False
    if not CODEXBAR_SETTINGS.exists():   # 새로 깐 CodexBar는 CLI로 제공자를 켜야 설정 파일이 생긴다
        run([str(CLI), "config", "enable", "claude"], timeout=60)
    if not CODEXBAR_SETTINGS.exists() and CODEXBAR_APP.exists():
        subprocess.Popen([str(CODEXBAR_APP)])
        for _ in range(20):
            if CODEXBAR_SETTINGS.exists():
                break
            time.sleep(1)
        run(["taskkill", "/f", "/im", "codexbar.exe"])
    try:
        raw = CODEXBAR_SETTINGS.read_text(encoding="utf-8-sig")
        env = json.loads(raw)
        if env.get("protection") != "windows-dpapi-user":
            return False
        text = _dpapi(base64.b64decode(env["payload"]), False).decode("utf-8")

        def set_bool(t, key, val):
            pat = r'("' + re.escape(key) + r'"\s*:\s*)(true|false)'
            if re.search(pat, t):
                return re.sub(pat, r"\g<1>" + ("true" if val else "false"), t, count=1)
            return re.sub(r"^\s*\{", "{\n  \"%s\": %s," % (key, "true" if val else "false"), t, count=1)
        text = set_bool(text, "claude_allow_reading_claude_code_credentials", True)
        text = set_bool(text, "start_at_login", False)
        text = set_bool(text, "float_bar_enabled", False)
        arr = '"enabled_providers": [' + ",".join("\n    \"%s\"" % p for p in providers) + "\n  ]"
        pat = r'"enabled_providers"\s*:\s*\[[^\]]*\]'
        text = re.sub(pat, lambda _m: arr, text, count=1) if re.search(pat, text) else re.sub(r"^\s*\{", lambda _m: "{\n  " + arr + ",", text, count=1)
        payload = base64.b64encode(_dpapi(text.encode("utf-8"), True)).decode()
        shutil.copy2(CODEXBAR_SETTINGS, str(CODEXBAR_SETTINGS) + ".bak")
        out = re.sub(r'("payload"\s*:\s*")[^"]*(")', lambda m: m.group(1) + payload + m.group(2), raw, count=1)
        CODEXBAR_SETTINGS.write_bytes(out.encode("utf-8"))   # BOM 없이 (BOM이 붙으면 CodexBar가 못 읽음)
    except Exception:  # noqa: BLE001
        return False
    run([str(CLI), "autostart", "--disable"], timeout=30)
    return True


# ---------------------------------------------------------------- 위젯 켜기/끄기, 바로가기
def stop_widget(wait=8):
    """실행 중인 위젯을 부드럽게 끈다 (quit.flag). 안 꺼지면 강제 종료."""
    # 예전 파이썬 설치본(pythonw usage_widget.py)은 quit.flag를 모르고, 같은 '이미 실행 중' 표시를 잡고 있어
    # 새 exe 위젯이 안 뜬다 → 먼저 끈다
    powershell("Get-CimInstance Win32_Process | Where-Object { $_.Name -in 'pythonw.exe','python.exe' -and "
               "$_.CommandLine -like '*usage_widget*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }", timeout=30)
    def running():
        code, out = run(["tasklist", "/fi", f"imagename eq {EXE_NAME}", "/fo", "csv", "/nh"])
        mine = {str(os.getpid()), str(os.getppid())}
        return [l for l in out.splitlines() if EXE_NAME.lower() in l.lower() and l.split(",")[1].strip('"') not in mine]
    if not running():
        return
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    QUIT_FLAG.write_text("quit")
    for _ in range(wait * 2):
        time.sleep(0.5)
        if not running():
            return
    for line in running():
        run(["taskkill", "/f", "/pid", line.split(",")[1].strip('"')])
    time.sleep(1)


def launch_widget(*args):
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    subprocess.Popen([str(INSTALLED_EXE), *args], creationflags=DETACHED, close_fds=True, env=env, cwd=str(INSTALL_DIR))


def make_shortcut(folder="Desktop"):
    """바로가기 생성. folder: "Desktop"(바탕화면) / "Programs"(시작 메뉴 — 검색창에 '위젯'만 쳐도 나옴)."""
    ps = ('$ws = New-Object -ComObject WScript.Shell; '
          f'$sc = $ws.CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath("{folder}"), "{DESKTOP_LNK}")); '
          f'$sc.TargetPath = "{INSTALLED_EXE}"; $sc.WorkingDirectory = "{INSTALL_DIR}"; '
          f'$sc.IconLocation = "{INSTALLED_EXE},0"; $sc.Save()')
    return powershell(ps, timeout=30)[0] == 0


def set_autostart(on):
    if on:
        STARTUP_BAT.parent.mkdir(parents=True, exist_ok=True)
        STARTUP_BAT.write_text(f'@echo off\r\nstart "" "{INSTALLED_EXE}" --boot\r\n', encoding="utf-8")
    else:
        STARTUP_BAT.unlink(missing_ok=True)


# ---------------------------------------------------------------- 설치 창
STEPS = [
    ("files", "위젯 설치", "설치 폴더에 위젯을 복사합니다"),
    ("codexbar", "사용량 읽는 도구", "Win-CodexBar (Claude·GPT 사용량을 읽어 옵니다)"),
    ("claude", "Claude 로그인", "위젯이 Claude 사용량을 읽으려면 한 번 로그인이 필요합니다"),
    ("gpt", "GPT 사용량 (선택)", "Codex·ChatGPT Work 사용량. 일반 채팅은 한도가 없어 해당 없음"),
    ("config", "설정 자동 맞춤", "CodexBar가 Claude 로그인을 읽도록 허용, 트레이 자동 실행 끔"),
    ("shortcut", "바로가기 · 자동 실행", "바탕화면 바로가기, Windows 켤 때 자동 실행"),
    ("launch", "위젯 켜기", ""),
]


class SetupWindow(tk.Tk):
    def __init__(self, mode):
        super().__init__()
        self.mode = mode
        self.title({"setup": "AI 사용량 위젯 설치", "relogin": "Claude 다시 로그인", "gpt": "GPT 연결"}[mode])
        self.configure(bg=CARD)
        self.resizable(False, False)
        try:
            self.iconbitmap(sys.executable)
        except tk.TclError:
            pass
        self.protocol("WM_DELETE_WINDOW", self._close)
        tk.Label(self, text=self.title(), bg=CARD, fg=ACCENT, font=(FONT, 17, "bold")).pack(anchor="w", padx=22, pady=(18, 2))
        tk.Label(self, text="Claude·GPT를 얼마나 썼는지 화면 한구석에 보여주는 위젯", bg=CARD, fg=SOFT,
                 font=(FONT, 10)).pack(anchor="w", padx=22)
        box = tk.Frame(self, bg=CARD)
        box.pack(fill="x", padx=18, pady=(12, 4))
        wanted = {"setup": [s[0] for s in STEPS], "relogin": ["claude"], "gpt": ["gpt", "config"]}[mode]
        self.rows = {}
        for key, name, desc in STEPS:
            if key not in wanted:
                continue
            r = tk.Frame(box, bg=CARD)
            r.pack(fill="x", pady=3)
            dot = tk.Canvas(r, width=18, height=18, bg=CARD, highlightthickness=0)
            dot.pack(side="left", padx=(4, 10), anchor="n", pady=3)
            col = tk.Frame(r, bg=CARD)
            col.pack(side="left", fill="x")
            tk.Label(col, text=name, bg=CARD, fg=INK, font=(FONT, 11, "bold"), anchor="w").pack(anchor="w")
            d = tk.Label(col, text=desc, bg=CARD, fg=SOFT, font=(FONT, 9), anchor="w", justify="left", wraplength=440)
            d.pack(anchor="w")
            self.rows[key] = (dot, d)
            self._dot(key, TODO_C)
        self.ask_frame = tk.Frame(self, bg="#fff1e4", highlightbackground=EDGE, highlightthickness=1)
        self.ask_label = tk.Label(self.ask_frame, text="", bg="#fff1e4", fg=INK, font=(FONT, 10), justify="left", wraplength=440)
        self.ask_label.pack(anchor="w", padx=14, pady=(10, 6))
        self.ask_btns = tk.Frame(self.ask_frame, bg="#fff1e4")
        self.ask_btns.pack(anchor="e", padx=10, pady=(0, 10))
        # 로그인 패널: 로그인 도구는 보이지 않는 창에서 돌고, 사용자는 여기서만 진행
        BG = "#fff1e4"
        self.login_frame = tk.Frame(self, bg=BG, highlightbackground=EDGE, highlightthickness=1)
        self.login_label = tk.Label(self.login_frame, text="", bg=BG, fg=INK, font=(FONT, 10), justify="left", wraplength=440)
        self.login_label.pack(anchor="w", padx=14, pady=(10, 6))
        self.code_row = tk.Frame(self.login_frame, bg=BG)
        tk.Label(self.code_row, text="코드", bg=BG, fg=SOFT, font=(FONT, 9)).pack(side="left", padx=(0, 6))
        self.code_entry = tk.Entry(self.code_row, font=("Consolas", 10), width=34, relief="solid", bd=1)
        self.code_entry.pack(side="left", ipady=3)
        self.code_entry.bind("<Return>", lambda _e: self._login_cmd("code"))
        self._btn(self.code_row, "보내기", lambda: self._login_cmd("code")).pack(side="left", padx=6)
        lb = tk.Frame(self.login_frame, bg=BG)
        lb.pack(fill="x", padx=10, pady=(4, 10))
        self.reopen_btn = self._btn(lb, "브라우저 다시 열기", lambda: self._login_cmd("open"), primary=False)
        self.reopen_btn.pack(side="left", padx=4)
        self._btn(lb, "나중에", lambda: self._login_cmd("cancel"), primary=False).pack(side="right", padx=4)
        self._btn(lb, "CMD 창에서 하기", lambda: self._login_cmd("console"), primary=False).pack(side="right", padx=4)
        self.bottom = tk.Frame(self, bg=CARD)
        self.bottom.pack(fill="x", padx=18, pady=(6, 16))
        self.status = tk.Label(self.bottom, text="", bg=CARD, fg=SOFT, font=(FONT, 9), anchor="w", justify="left", wraplength=330)
        self.status.pack(side="left")
        self.close_btn = self._btn(self.bottom, "닫기", self._close, primary=False)
        self.close_btn.pack(side="right")
        self._answer = None
        self._event = threading.Event()
        self.done = False
        self.geometry("+%d+%d" % (self.winfo_screenwidth() // 2 - 260, self.winfo_screenheight() // 2 - 300))
        self.after(300, lambda: threading.Thread(target=self._work, daemon=True).start())

    # ---------- UI 도우미 (작업 스레드에서 호출 → after로 넘김)
    def _btn(self, parent, text, cmd, primary=True):
        return tk.Button(parent, text=text, command=cmd, relief="flat", cursor="hand2", font=(FONT, 10, "bold" if primary else "normal"),
                         bg=ACCENT if primary else "#f3e7dc", fg="#ffffff" if primary else INK,
                         activebackground="#e67c5a" if primary else "#eadbcd", activeforeground="#ffffff" if primary else INK,
                         padx=14, pady=4, bd=0)

    def _dot(self, key, color, mark=""):
        c = self.rows[key][0]
        c.delete("all")
        c.create_oval(2, 2, 16, 16, fill=color, outline=color)
        if mark == "ok":      # 체크 표시는 선으로 (✓ 글자는 맑은 고딕에 없음)
            c.create_line(5.5, 9.5, 8, 12, 12.5, 6, fill="#ffffff", width=2)
        elif mark:
            c.create_text(9, 9, text=mark, fill="#ffffff", font=(FONT, 8, "bold"))

    def ui(self, fn, *a):
        self.after(0, fn, *a)

    def step(self, key, state, text=None):
        """state: run / ok / warn / skip"""
        slog(f"[{self.mode}] {key}: {state} {text or ''}")
        color, mark = {"run": (RUN_C, "…"), "ok": (OK_C, "ok"), "warn": (WARN_C, "!"), "skip": (TODO_C, "–")}[state]

        def f():
            if key in self.rows:
                self._dot(key, color, mark)
                if text is not None:
                    self.rows[key][1].configure(text=text, fg=WARN_C if state == "warn" else SOFT)
        self.ui(f)

    def say(self, text):
        self.ui(lambda: self.status.configure(text=text))

    def ask(self, key, question, options):
        """질문을 띄우고 버튼 답을 기다린다. options=[(값, 버튼 글자), ...] 첫 번째가 강조 버튼."""
        if key in ANSWERS:
            slog(f"[{self.mode}] ask {key}: auto {ANSWERS[key]}")
            return ANSWERS[key]
        self._event.clear()
        slog(f"[{self.mode}] ask {key}: waiting for user")

        def show():
            self.ask_label.configure(text=question)
            for w in self.ask_btns.winfo_children():
                w.destroy()
            for i, (val, label) in enumerate(options):
                self._btn(self.ask_btns, label, lambda v=val: self._reply(v), primary=(i == 0)).pack(side="left", padx=4)
            self.ask_frame.pack(fill="x", padx=18, pady=(8, 4), before=self.bottom)
            self.lift()
            self.attributes("-topmost", True)
            self.after(200, lambda: self.attributes("-topmost", False))
        self.ui(show)
        self._event.wait()
        return self._answer

    # ---------- 로그인 패널
    def _login_cmd(self, cmd):
        val = self.code_entry.get().strip() if cmd == "code" else None
        if cmd == "code" and not val:
            return
        if cmd == "code":
            self.code_entry.delete(0, "end")
        self._login_q.put((cmd, val))

    def _login_show(self, text):
        self.login_label.configure(text=text)
        self.code_row.pack_forget()
        self.reopen_btn.configure(state="disabled")
        self.login_frame.pack(fill="x", padx=18, pady=(8, 4), before=self.bottom)
        self.lift()

    def hidden_login(self, exe, args, what, fallback=None):
        """로그인 도구를 보이지 않는 창에서 실행하고 설치 창에서 진행. '나중에'를 눌렀으면 True.
        fallback: 주소도 못 보고 끝났을 때 CMD 창에서 대신 실행할 (인자, 안내문). 없으면 같은 명령."""
        self._login_q = queue.Queue()
        # 도구가 끝난 뒤에도 3초간 창을 남겨 마지막 화면(오류 문구)을 읽을 수 있게
        hc = HiddenConsole(f'cmd /c ""{exe}" {" ".join(args)} & ping -n 4 127.0.0.1 >nul"')
        slog(f"[{self.mode}] hidden login start: {what}")
        self.ui(self._login_show, f"브라우저에서 {what} 계정으로 로그인하세요. (브라우저가 열리는 데 몇 초 걸릴 수 있어요)\n"
                                  "허용(Authorize)을 누르면 자동으로 다음 단계로 넘어갑니다.")
        url, code_shown, opened, found_at, last = None, False, False, 0.0, ""
        try:
            while hc.alive():
                scr = hc.screen()
                last = scr.strip() or last
                urls = re.findall(r"https://\S+", scr)
                if urls and urls[-1] != url:
                    url, found_at = urls[-1], time.time()
                    self.ui(lambda: self.reopen_btn.configure(state="normal"))
                    slog(f"[{self.mode}] login url found ({len(url)} chars)")
                # 창을 숨기면 로그인 도구가 브라우저를 못 여는 경우가 있어, 주소를 찾으면 직접 연다
                if url and not opened and time.time() - found_at > 2:
                    opened = True
                    webbrowser.open(url)
                    slog(f"[{self.mode}] opened login url in browser")
                if not code_shown and re.search(r"paste", scr, re.I):
                    code_shown = True
                    self.ui(lambda: (self.login_label.configure(text=self.login_label.cget("text") +
                                                                "\n\n브라우저에 코드가 보이면 복사해서 아래 칸에 붙여넣고 [보내기]"),
                                     self.code_row.pack(anchor="w", padx=14, pady=(0, 6), before=self.reopen_btn.master)))
                try:
                    cmd, val = self._login_q.get(timeout=1)
                except queue.Empty:
                    cmd, val = None, None
                if cmd == "code":
                    slog(f"[{self.mode}] login code sent ({len(val)} chars)")
                    hc.type(val)
                elif cmd == "open" and url:
                    webbrowser.open(url)
                elif cmd == "cancel":
                    slog(f"[{self.mode}] login cancelled")
                    return True
                elif cmd == "console":
                    slog(f"[{self.mode}] login fallback to console")
                    hc.kill()
                    self.ui(self.login_frame.pack_forget)
                    console_cmd(exe, *args, title=f"{what} 로그인")
                    return False
            slog(f"[{self.mode}] login tool exited")
            if not url:   # 주소도 못 보고 끝남 (도구 버전 차이 등) → 기록 남기고 보이는 CMD 창으로 다시
                slog(f"[{self.mode}] no login url; last screen: {last[-600:]!r}")
                self.ui(self.login_frame.pack_forget)
                fargs, guide = fallback or (args, "CMD 창의 안내를 따라 주세요.")
                self.ask("fallback", f"{what} 로그인을 CMD 창에서 진행합니다.\n{guide}", [("ok", "CMD 창 열기")])
                console_cmd(exe, *fargs, title=f"{what} 로그인", pause=fargs == args)
            return False
        finally:
            hc.kill()
            self.ui(self.login_frame.pack_forget)

    def _reply(self, value):
        slog(f"[{self.mode}] answer: {value}")
        self.ask_frame.pack_forget()
        self._answer = value
        self._event.set()

    def _close(self):
        if not self.done and not messagebox.askyesno("설치", "아직 진행 중입니다. 닫을까요?\n나중에 다시 실행하면 된 단계는 건너뜁니다.", parent=self):
            return
        self._answer = None
        self._event.set()
        self.destroy()

    # ---------- 단계
    def _work(self):
        try:
            if self.mode == "setup":
                if self.do_files() and self.do_codexbar():
                    self.do_claude(first=True)
                    self.do_config(self.do_gpt(ask_first=True))
                    self.do_shortcut()
                    self.do_launch()
            elif self.mode == "relogin":
                self.do_claude(first=False, force=True)
                self.say("위젯이 켜져 있으면 우클릭 → '지금 새로고침'을 누르세요.")
            elif self.mode == "gpt":
                self.do_config(self.do_gpt(ask_first=False))
                self.say("위젯이 켜져 있으면 우클릭 → '지금 새로고침'을 누르세요.")
        except Exception as ex:  # noqa: BLE001
            slog(f"[{self.mode}] error: {ex!r}")
            self.say(f"예상하지 못한 오류: {ex}")
        self.done = True
        self.ui(lambda: self.close_btn.configure(text="닫기", bg=ACCENT, fg="#ffffff"))

    def blocked(self, key, what):
        self.step(key, "warn", f"{what} 설치가 막혔거나 오래 걸립니다. 회사 PC라면 IT 담당자에게 '{what} 설치'를 요청하세요. "
                               "설치 후 이 프로그램을 다시 실행하면 된 단계는 건너뜁니다.")

    def do_files(self):
        self.step("files", "run")
        me = Path(sys.executable).resolve()
        if me != INSTALLED_EXE.resolve():
            INSTALL_DIR.mkdir(parents=True, exist_ok=True)
            stop_widget()            # 다시 설치할 때 실행 중인 위젯이 exe를 잡고 있으면 복사가 안 됨
            for i in range(20):
                try:
                    shutil.copy2(me, INSTALLED_EXE)
                    break
                except PermissionError:
                    time.sleep(0.5)
            else:
                self.step("files", "warn", "위젯 파일을 복사하지 못했습니다. 위젯을 끄고 다시 실행하세요.")
                return False
        self.step("files", "ok", f"설치 폴더: {INSTALL_DIR}")
        return True

    def do_codexbar(self):
        self.step("codexbar", "run", "확인 중…")
        if not CLI.exists():
            self.step("codexbar", "run", "설치하는 중… (1~2분, '허용' 창이 뜨면 '예')")
            run(["winget", "install", "-e", "--id", "Finesssee.Win-CodexBar", "--accept-package-agreements",
                 "--accept-source-agreements", "--silent"], timeout=900)
        if not CLI.exists():
            self.blocked("codexbar", "Win-CodexBar")
            return False
        self.step("codexbar", "ok", "확인됨")
        return True

    def do_claude(self, first, force=False):
        self.step("claude", "run", "로그인 상태 확인 중…")
        st = claude_login_state()
        if st == "ok":
            configure_codexbar(["claude", "codex"])
            err = probe("claude")
            slog(f"[{self.mode}] claude probe: {err or 'ok'}")
            if not err and not force:
                self.step("claude", "ok", "이미 로그인되어 있습니다")
                return True
            if err and re.search(r"expired|re-authenticate|rejected|401|unauthorized|not logged", err, re.I):
                st = "expired"
            elif not err and force:
                if self.ask("relogin", "로그인은 정상입니다. 그래도 다시 로그인할까요? (다른 계정으로 바꿀 때)",
                            [("y", "다시 로그인"), ("n", "그만두기")]) != "y":
                    self.step("claude", "ok", "로그인 정상 (변경 없음)")
                    return True
            elif err and not force:
                self.step("claude", "ok", f"로그인되어 있습니다 (조회 확인 실패: {err[:60]} — 위젯이 잠시 뒤 다시 시도)")
                return True
        exe = find_tool("claude")
        if not exe:
            self.step("claude", "run", "Claude 로그인 도구(Claude Code)를 설치하는 중… 직접 쓸 일은 없습니다")
            powershell("irm https://claude.ai/install.ps1 | iex", timeout=600)
            local_bin = str(Path.home() / ".local" / "bin")
            powershell(f'$p=[Environment]::GetEnvironmentVariable("Path","User"); if ($p -notlike "*{local_bin}*") '
                       f'{{ [Environment]::SetEnvironmentVariable("Path", $p + ";{local_bin}", "User") }}', timeout=30)
            add_path(local_bin)
            exe = find_tool("claude")
            if not exe:
                self.blocked("claude", "Claude Code")
                return False
        reason = ("로그인이 만료되어 다시 로그인합니다." if st == "expired" else
                  "Claude 로그인을 다시 합니다." if force else "Claude 사용량을 읽으려면 한 번 로그인이 필요합니다.")
        for attempt in range(2):
            ans = self.ask("login", f"{reason}\n\n[로그인 시작]을 누르면 브라우저가 열립니다.\n"
                                    "Claude 계정으로 로그인하고 'Authorize'(허용)를 누르면 됩니다.",
                           [("go", "로그인 시작"), ("skip", "나중에")])
            if ans != "go":
                self.step("claude", "warn", "건너뜀 — 나중에 위젯 우클릭 → 문제 해결 → Claude 다시 로그인")
                return True
            self.step("claude", "run", "브라우저에서 로그인 진행 중…")
            before = CLAUDE_CRED.stat().st_mtime if CLAUDE_CRED.exists() else 0
            # 오래된 Claude Code에는 'auth login'이 없어 바로 끝남 → 대화형 claude의 /login으로
            old_way = ([], "① 로그인 방식을 물으면 'Claude account with subscription' 선택\n"
                           "② 브라우저에서 로그인 → Authorize, 코드가 나오면 CMD 창에 붙여넣고 Enter\n"
                           "③ '>' 입력창이 바로 뜨면 /login 입력 → 로그인 → 끝나면 /exit 입력")
            if self.hidden_login(exe, ["auth", "login"], "Claude", fallback=old_way):
                self.step("claude", "warn", "건너뜀 — 나중에 위젯 우클릭 → 문제 해결 → Claude 다시 로그인")
                return True
            renewed = CLAUDE_CRED.exists() and CLAUDE_CRED.stat().st_mtime > before and claude_login_state() == "ok"
            slog(f"[{self.mode}] claude credentials renewed: {renewed}")
            configure_codexbar(["claude", "codex"])
            err = probe("claude")
            slog(f"[{self.mode}] claude probe after login: {err or 'ok'}")
            if not err:
                self.step("claude", "ok", "로그인 완료 (조회 확인)")
                return True
            if renewed or "rate limit" in err.lower():
                self.step("claude", "ok", "로그인 완료 (사용량 확인은 위젯이 잠시 뒤에 합니다)")
                return True
            reason = (f"아직 로그인이 확인되지 않습니다 ({err[:60]}). 한 번 더 해 볼까요?\n"
                      "브라우저 로그인을 처음부터 다시 해 주세요 (한 번 쓴 코드는 다시 쓸 수 없어요).")
        self.step("claude", "warn", "로그인이 확인되지 않았습니다 — 나중에 위젯 우클릭 → 문제 해결 → Claude 다시 로그인")
        return True

    def do_gpt(self, ask_first):
        """GPT 연결. 표시할 제공자 목록을 돌려준다."""
        if ask_first:
            ans = self.ask("gpt", "Codex나 ChatGPT Work를 쓰시나요?\n(채팅만 쓰면 한도가 없어 볼 숫자가 없습니다)",
                           [("y", "씁니다"), ("n", "채팅만 써요")])
            if ans != "y":
                set_state("show_gpt", False)
                self.step("gpt", "skip", "숨김 — 나중에 위젯 우클릭 → 문제 해결 → GPT 연결하기")
                return ["claude"]
        self.step("gpt", "run", "GPT 로그인 도구 확인 중…")
        if not find_tool("codex"):
            if not find_tool("npm"):
                self.step("gpt", "run", "Node.js 설치 중… (1~2분, '허용' 창이 뜨면 '예')")
                run(["winget", "install", "-e", "--id", "OpenJS.NodeJS.LTS", "--accept-package-agreements",
                     "--accept-source-agreements", "--silent"], timeout=900)
                add_path(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "nodejs"),
                         os.path.join(os.environ["APPDATA"], "npm"))
            npm = find_tool("npm")
            if npm:
                self.step("gpt", "run", "GPT 로그인 도구(Codex CLI) 설치 중…")
                run(f'cmd /c ""{npm}" install -g @openai/codex"', timeout=900)   # 경로 전체를 따옴표로 (사용자 폴더에 괄호가 있어도)
                add_path(os.path.join(os.environ["APPDATA"], "npm"))
        codex = find_tool("codex")
        if not codex:
            self.blocked("gpt", "Node.js / Codex CLI")
            return ["claude"]
        need = not CODEX_AUTH.exists()
        if not need:
            configure_codexbar(["claude", "codex"])
            err = probe("codex")
            if err and re.search(r"authentication|not logged|auth|expired|401|unauthorized|account not found", err, re.I):
                run(f'cmd /c ""{codex}" logout"', timeout=60)
                need = True
        if need:
            ans = self.ask("gptlogin", "[로그인 시작]을 누르면 브라우저가 열립니다.\nChatGPT 계정으로 로그인하면 자동으로 넘어갑니다.",
                           [("go", "로그인 시작"), ("skip", "나중에")])
            if ans == "go":
                self.step("gpt", "run", "브라우저에서 로그인 진행 중…")
                self.hidden_login(codex, ["login"], "ChatGPT")
        if not CODEX_AUTH.exists():
            self.step("gpt", "warn", "GPT 로그인이 확인되지 않았습니다 — 나중에 위젯 우클릭 → 문제 해결 → GPT 연결하기")
            return ["claude"]
        set_state("show_gpt", True)
        self.step("gpt", "ok", "연결됨")
        return ["claude", "codex"]

    def do_config(self, providers):
        self.step("config", "run")
        if configure_codexbar(providers):
            self.step("config", "ok", "완료 (Claude 읽기 허용, 표시 항목, 트레이 자동 실행 끔)")
        else:
            self.step("config", "warn", "자동 설정 실패 — 위젯 우클릭 → 문제 해결 → 점검 실행")

    def do_shortcut(self):
        self.step("shortcut", "run")
        ok = make_shortcut()
        make_shortcut("Programs")
        auto = self.ask("autostart", "Windows를 켤 때 위젯도 자동으로 켤까요?", [("y", "켤게요"), ("n", "아니요")]) == "y"
        set_autostart(auto)
        self.step("shortcut", "ok" if ok else "warn",
                  ("바탕화면 'AI 사용량 위젯' 바로가기 생성" if ok else "바로가기를 만들지 못했습니다")
                  + (" · 자동 실행 켬" if auto else " · 자동 실행 끔"))

    def do_launch(self):
        self.step("launch", "run")
        stop_widget()
        launch_widget()
        self.step("launch", "ok", "화면 왼쪽 위에 카드가 뜹니다 (첫 조회 5~10초). 끄기: 위젯 우클릭 → 종료")
        self.say("설치가 끝났습니다. 받은 파일(다운로드 폴더의 exe)은 지워도 됩니다.")


def run_uninstall():
    root = tk.Tk()
    root.withdraw()
    if not messagebox.askyesno("위젯 제거", "AI 사용량 위젯을 제거할까요?\n\n지우는 것: 위젯, 바탕화면 바로가기, 자동 실행\n"
                               "남기는 것: Win-CodexBar, Claude Code, Node.js/Codex (다른 용도로도 쓰일 수 있음.\n"
                               "지우려면 Windows 설정 → 앱에서 각각 제거)", parent=root):
        return
    stop_widget()
    desktop = Path(os.environ["USERPROFILE"]) / "Desktop"
    code, out = powershell('[Environment]::GetFolderPath("Desktop")', timeout=20)
    if code == 0 and out.strip():
        desktop = Path(out.strip().splitlines()[-1])
    for name in (DESKTOP_LNK, "AI Usage Widget.lnk"):
        (desktop / name).unlink(missing_ok=True)
    STARTUP_BAT.unlink(missing_ok=True)
    START_MENU_LNK.unlink(missing_ok=True)
    wipe = messagebox.askyesno("위젯 제거", "위젯 폴더도 지울까요? 설정과 기록이 함께 지워집니다.\n" + str(INSTALL_DIR), parent=root)
    if wipe:
        # 실행 중인 exe는 자기 자신을 지울 수 없으므로, 이 창이 닫힌 뒤 3초 있다가 지운다
        subprocess.Popen(f'cmd /c ping -n 4 127.0.0.1 >nul & rmdir /s /q "{INSTALL_DIR}"', creationflags=NO_WINDOW | DETACHED)
    messagebox.showinfo("위젯 제거", "제거가 끝났습니다.", parent=root)


def main(mode):
    if mode == "uninstall":
        run_uninstall()
        return
    SetupWindow(mode).mainloop()

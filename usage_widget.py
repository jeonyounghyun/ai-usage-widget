"""
AI Usage Widget - Claude / GPT(Codex) 사용량 한도를 화면에 항상 표시하는 파스텔 카드 위젯.
RunCat처럼 픽셀 고양이가 달리며, 5시간 한도를 많이 쓸수록 빨리 달리고 100%면 잠든다.

데이터 소스: Win-CodexBar CLI (codexbar-cli.exe usage -p both --json)
  - 인증/토큰 갱신은 Win-CodexBar가 처리하므로 이 위젯은 결과만 읽는다.

조작:
  - 드래그: 위치 이동 (자동 저장)
  - 우상단 ↻: 즉시 새로고침, ✕: 종료
  - 우클릭: 메뉴 (새로고침 / 투명도 / 페이스 예측 / 클릭 통과 / 알림 소리 / 항상 위 / 전체화면 시 숨김 / 시작 시 자동 실행 / 종료)
  - 클릭 통과 모드: 다른 창이 활성일 땐 마우스가 위젯을 통과. 바탕화면이 활성이거나 Ctrl을 누른 동안만 조작 가능

기능:
  - 80% 도달, 100% 도달, 한도 리셋 시 카드 하단에 알림 배너 + (선택) 알림음
  - Claude의 Fable 전용 주간 한도를 작은 막대로 표시
  - 전체화면 앱(영상/게임/발표) 감지 시 자동 숨김, 종료되면 복귀
  - 적응형 폴링: 사용률이 오르는 중이면 60초, 멈춰 있으면 180→300초, 조회 실패면 2배씩 물러남(최대 10분)
  - 조회 실패 시 마지막 값을 평소처럼 컬러로 유지, 10분 넘게 갱신 안 되면 "N분 전 값" 표시, 1시간 넘으면 회색
  - 카드 본체는 값이 바뀔 때만 다시 그리고, 매 틱에는 고양이만 얹음 (CPU 절약)
  - 자동 업데이트: 하루 1회 GitHub Releases 확인 → 새 버전이면 팝업, 클릭하면 내려받아 교체 후 재시작
"""

import ctypes
import io
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import winsound
import zipfile
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageTk

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

import logging
from logging.handlers import RotatingFileHandler

VERSION = "1.0.2"
LOG_PATH = Path(__file__).with_name("widget.log")
logging.basicConfig(handlers=[RotatingFileHandler(LOG_PATH, maxBytes=200_000, backupCount=1, encoding="utf-8")],
                    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("widget")


def acquire_single_instance():
    """이미 떠 있으면 False (Windows 이름 있는 뮤텍스)."""
    ctypes.windll.kernel32.CreateMutexW(None, False, r"Local\AIUsageWidget")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


# ---------------------------------------------------------------- 설정
CODEXBAR_CLI = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "CodexBar" / "codexbar-cli.exe"
# 적응형 폴링: 사용률이 오르는 중이면 빠르게, 멈춰 있으면 느리게, 조회 실패면 물러남
REFRESH_FAST = 60                     # 직전 조회보다 5시간 사용률이 올랐을 때
REFRESH_SEC = 180                     # 변화 없을 때 기본 주기 (60초 고정이면 Anthropic 조회 API가 일시 차단함)
REFRESH_IDLE = 300                    # IDLE_AFTER번 연속 변화 없으면
IDLE_AFTER = 6
BACKOFF_MAX = 600                     # 조회 실패 시 간격을 2배씩 늘리되 이 값까지
STALE_WARN_MIN = 10                   # 갱신이 이 분수 넘게 안 되면 "N분 전 값"으로 표시
CLI_TIMEOUT = 90
ANIM_MS = 100                         # 애니메이션 틱
BANNER_SEC = 90                       # 알림 배너 유지 시간
STALE_AFTER_SEC = 3600                # 마지막 성공 후 이 시간이 지나야 회색(오래된 값) 처리
CONFIG_PATH = Path(__file__).with_name("widget_state.json")
UPDATE_REPO = "jeonyounghyun/ai-usage-widget"
UPDATE_API = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
UPDATE_CHECK_SEC = 24 * 3600          # 자동 업데이트 확인 주기
UPDATE_FILES = ("usage_widget.py", "toast.ps1", "toggle_widget.bat", "install.bat", "README.md", "LICENSE")
STARTUP_DIR = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_BAT = STARTUP_DIR / "ai-usage-widget.bat"
FONT_DIR = Path("C:/Windows/Fonts")

# 팔레트 (파스텔)
CHROMA = "#8c8c8c"        # 투명 처리용 키 색 (둥근 모서리 바깥)
CARD = "#fff8f1"
CARD_EDGE = "#f0e1d2"
INK = "#4a3f3a"
INK_SOFT = "#a3928a"
TRACK = "#f2e7dd"
C_OK, C_WARN, C_BAD, C_STALE = "#7fd1a8", "#f8c66d", "#f58c8c", "#d9cfc7"
PROVIDERS_ALL = [
    # key, 표시명, 강조색, 고양이 몸색, 고양이 무늬색
    ("claude", "Claude", "#f28c6b", "#f4a460", "#d98a3f"),
    ("codex", "GPT", "#6fbfa3", "#a9b4c2", "#7f8b9b"),
]
PROVIDERS = list(PROVIDERS_ALL)   # 현재 표시 중인 제공자 (apply_layout이 갱신)
WINDOWS = [("primary", "5시간"), ("secondary", "7일")]

# 레이아웃 (논리 px). 카드는 SS배 슈퍼샘플링 후 축소, 고양이는 원본 도트.
SS = 2
SEC_W = 278                # 제공자 한 칸 너비 (카드)
MINI_SEC_W = 128           # 제공자 한 칸 너비 (미니)
W, H = 4 + SEC_W * 2, 126
RADIUS = 16
MINI_W, MINI_H = MINI_SEC_W * 2, 34   # 작업표시줄 미니 모드 크기


def apply_layout(show_gpt=True):
    """표시할 제공자에 맞춰 카드/미니 폭을 다시 계산한다."""
    global PROVIDERS, W, MINI_W
    PROVIDERS = [p for p in PROVIDERS_ALL if show_gpt or p[0] != "codex"]
    n = max(1, len(PROVIDERS))
    W = 4 + SEC_W * n
    MINI_W = MINI_SEC_W * n
GAUGE = 56
RING_W = 7

# ---------------------------------------------------------------- 픽셀 고양이 (18x12, 옆모습 달리기)
# b=몸, s=무늬, e=눈, p=귀 안쪽, m=입, '-'=감은 눈
CAT_BODY = [
    "............b...b.",
    "............bpbpb.",
    "............bbbbb.",
    "...........bbbbbbb",
    "b..........bbeebbb",
    ".b........bbbeebbb",
    "..bb...bbbbbbbbmb.",
    "....bbbbbsbbbbbbb.",
    "....bbbbbbbsbbbb..",
    "....bbbsbbbbbbbb..",
]
CAT_LEGS = [
    ["...bb......bb.....", "..bb........bb...."],
    [".....bb..bb.......", ".....bb..bb......."],
    ["......bb.bb.......", ".................."],
    ["......bb..bb......", ".....bb....bb....."],
]
CAT_BOUNCE = [0, -1, -2, -1]   # 프레임별 몸 높이(도트 단위)
CAT_SLEEP_BODY = [r.replace("e", "-") for r in CAT_BODY]
CAT_SLEEP_LEGS = ["....bbbbbbbbbbbb..", ".................."]
CAT_PX = 2  # 위젯 고양이 도트 크기 (논리 px)
CAT_PX_POPUP = 3  # 알림 팝업 고양이 도트 크기

# 미니 모드용 얼굴 아이콘 (11x9). 달릴 땐 위아래로 까딱, 잠들면 눈 감음
CAT_HEAD = [
    ".b.......b.",
    ".bb.....bb.",
    ".bpb...bpb.",
    ".bbbbbbbbb.",
    "bbbbbbbbbbb",
    "bbeebbbeebb",
    "bbbbbbbbbbb",
    "bbbbmbmbbbb",
    ".bbbbbbbbb.",
]
CAT_HEAD_SLEEP = [r.replace("e", "-") for r in CAT_HEAD]
CAT_HEAD_BOB = [0, -1, 0, 1]
CAT_PX_MINI = 2


# ---------------------------------------------------------------- 유틸
def pct_color(p):
    if p is None:
        return C_STALE
    if p >= 80:
        return C_BAD
    if p >= 50:
        return C_WARN
    return C_OK


def fmt_remaining(resets_at):
    if not resets_at:
        return ""
    try:
        t = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
    except ValueError:
        return ""
    sec = int((t - datetime.now(timezone.utc)).total_seconds())
    if sec <= 0:
        return "리셋됨"
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}일 {h}시간 후"
    if h:
        return f"{h}시간 {m}분 후"
    return f"{m}분 후"


def fetch_usage(keys=("claude", "codex")):
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    prov_arg = "both" if len(keys) > 1 else keys[0]
    out = subprocess.run(
        [str(CODEXBAR_CLI), "usage", "-p", prov_arg, "--json", "--no-color"],
        capture_output=True, text=True, timeout=CLI_TIMEOUT, creationflags=flags,
        encoding="utf-8", errors="replace",
    )
    if out.returncode != 0 and not out.stdout.strip():
        raise RuntimeError(out.stderr.strip()[-200:] or f"exit {out.returncode}")
    result, errors = {}, {}
    for item in json.loads(out.stdout):
        prov = item.get("provider")
        if not prov:
            continue
        usage = item.get("usage") or {}
        if usage:
            usage["_pace"] = item.get("pace") or {}
            result[prov] = usage
        else:
            errors[prov] = item.get("error") or "no data"
    return result, errors


TOAST_PS1 = Path(__file__).with_name("toast.ps1")


def notify_windows(title, body):
    """Windows 알림 센터 토스트. 백그라운드 스레드에서 PowerShell 호출 (창 없음)."""
    def run():
        try:
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TOAST_PS1),
                            "-Title", title, "-Body", body], creationflags=flags, timeout=20,
                           capture_output=True)
        except Exception:  # noqa: BLE001
            log.exception("toast failed")
    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------- 자동 업데이트 (GitHub Releases)
def _ver_tuple(v):
    return tuple(int(x) for x in v.strip().lstrip("v").split(".") if x.isdigit())


def check_update():
    """최신 릴리즈 조회. 새 버전이면 (version, zip_url), 아니면 None. 실패 시 예외."""
    req = urllib.request.Request(UPDATE_API, headers={"User-Agent": f"ai-usage-widget/{VERSION}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read().decode("utf-8"))
    tag = d.get("tag_name", "")
    if _ver_tuple(tag) <= _ver_tuple(VERSION):
        return None
    for a in d.get("assets", []):
        if a.get("name", "").endswith(".zip"):
            return tag.lstrip("v"), a["browser_download_url"]
    return None


def apply_update(zip_url, target_dir):
    """ZIP을 받아 target_dir의 프로그램 파일을 교체한다 (설정/로그는 건드리지 않음)."""
    req = urllib.request.Request(zip_url, headers={"User-Agent": f"ai-usage-widget/{VERSION}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        blob = r.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()
        if "usage_widget.py" not in names:
            raise RuntimeError("zip에 usage_widget.py가 없음")
        for n in names:
            base = n.replace("\\", "/")
            if base in UPDATE_FILES or base.startswith("docs/"):
                dest = Path(target_dir) / base
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(n) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
    return True


def extra_window(usage, keyword):
    """extra_rate_windows에서 id/title에 keyword가 들어간 창을 찾는다 (예: Fable 전용 주간)."""
    for ew in usage.get("extra_rate_windows") or []:
        text = f"{ew.get('id', '')} {ew.get('title', '')}".lower()
        if keyword in text:
            return ew.get("window") or {}
    return {}


def pace_hint(usage, wkey):
    """CLI의 pace 정보를 한 줄 힌트로. (문구, 색) 또는 None."""
    p = (usage.get("_pace") or {}).get(wkey) or {}
    if not p:
        return None
    pct = ((usage.get(wkey) or {}).get("used_percent"))
    if pct is not None and pct >= 100:
        return None
    if p.get("willLastToReset") is False:
        return "부족 예상", C_BAD
    stage = p.get("stage", "")
    if stage in ("farahead", "ahead"):
        return "빠듯", C_WARN
    return "여유", C_OK


def font(name, size, scale=SS):
    for f in (name, "malgunbd.ttf", "malgun.ttf"):
        p = FONT_DIR / f
        if p.exists():
            return ImageFont.truetype(str(p), int(size * scale))
    return ImageFont.load_default()


# ---------------------------------------------------------------- Win32: 전체화면 감지 / 화면 범위
_user32 = ctypes.windll.user32

# 64비트에서 HWND/포인터 인자가 32비트 int로 잘리지 않도록 시그니처 명시 (없으면 SetWindowPos(HWND_TOPMOST)가 조용히 실패)
_HWND = wintypes.HWND
_user32.GetForegroundWindow.restype = _HWND
_user32.GetAncestor.argtypes = [_HWND, wintypes.UINT]
_user32.GetAncestor.restype = _HWND
_user32.SetWindowPos.argtypes = [_HWND, _HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.GetWindowLongW.argtypes = [_HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = wintypes.LONG
_user32.SetWindowLongW.argtypes = [_HWND, ctypes.c_int, wintypes.LONG]
_user32.SetWindowLongW.restype = wintypes.LONG
_user32.GetWindowRect.argtypes = [_HWND, ctypes.c_void_p]
_user32.GetClassNameW.argtypes = [_HWND, ctypes.c_wchar_p, ctypes.c_int]
_user32.MonitorFromWindow.argtypes = [_HWND, wintypes.DWORD]
_user32.MonitorFromWindow.restype = ctypes.c_void_p
_user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
_user32.FindWindowW.restype = _HWND
_user32.FindWindowExW.argtypes = [_HWND, _HWND, ctypes.c_wchar_p, ctypes.c_wchar_p]
_user32.FindWindowExW.restype = _HWND
HWND_TOPMOST = _HWND(-1)


class _RECT(ctypes.Structure):
    _fields_ = [("l", wintypes.LONG), ("t", wintypes.LONG), ("r", wintypes.LONG), ("b", wintypes.LONG)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT), ("rcWork", _RECT), ("dwFlags", wintypes.DWORD)]


def foreground_is_fullscreen(own_hwnd):
    """전경 창이 (위젯과 같은 모니터를) 꽉 채우고 있으면 True (바탕화면/작업표시줄/자기 자신 제외)."""
    try:
        h = _user32.GetForegroundWindow()
        if not h or h == own_hwnd:
            return False
        if _user32.MonitorFromWindow(h, 2) != _user32.MonitorFromWindow(own_hwnd, 2):
            return False  # 다른 모니터의 전체화면은 무시
        cls = ctypes.create_unicode_buffer(64)
        _user32.GetClassNameW(h, cls, 64)
        if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"):
            return False
        r = _RECT()
        _user32.GetWindowRect(h, ctypes.byref(r))
        mon = _user32.MonitorFromWindow(h, 2)  # MONITOR_DEFAULTTONEAREST
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        _user32.GetMonitorInfoW(mon, ctypes.byref(mi))
        m = mi.rcMonitor
        return r.l <= m.l and r.t <= m.t and r.r >= m.r and r.b >= m.b
    except Exception:  # noqa: BLE001
        return False


def desktop_is_foreground(own_hwnd):
    h = _user32.GetForegroundWindow()
    if not h or h == own_hwnd:
        return True
    cls = ctypes.create_unicode_buffer(64)
    _user32.GetClassNameW(h, cls, 64)
    return cls.value in ("Progman", "WorkerW")


def ctrl_down():
    return bool(_user32.GetAsyncKeyState(0x11) & 0x8000)  # VK_CONTROL


GWL_EXSTYLE, WS_EX_TRANSPARENT, WS_EX_LAYERED = -20, 0x20, 0x80000


def set_click_through(hwnd, enable):
    """실제 창 스타일을 읽어 필요할 때만 바꾼다. 바뀌었으면 True."""
    style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    new = (style | WS_EX_TRANSPARENT | WS_EX_LAYERED) if enable else (style & ~WS_EX_TRANSPARENT)
    if new != style:
        _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new)
        return True
    return False


def taskbar_slot(w, h):
    """작업표시줄 알림 영역(시계) 왼쪽에 w x h 를 놓을 좌표. 작업표시줄이 가로가 아니면 None."""
    try:
        tb = _user32.FindWindowW("Shell_TrayWnd", None)
        if not tb:
            return None
        r = _RECT()
        _user32.GetWindowRect(tb, ctypes.byref(r))
        if (r.b - r.t) > (r.r - r.l):
            return None  # 세로 작업표시줄
        tray = _user32.FindWindowExW(tb, 0, "TrayNotifyWnd", None)
        tr = _RECT()
        if tray:
            _user32.GetWindowRect(tray, ctypes.byref(tr))
            right = tr.l
        else:
            right = r.r - 200
        x = right - w - 8
        y = r.t + ((r.b - r.t) - h) // 2
        return x, y
    except Exception:  # noqa: BLE001
        return None


def clamp_to_screen(x, y):
    vx, vy = _user32.GetSystemMetrics(76), _user32.GetSystemMetrics(77)
    vw, vh = _user32.GetSystemMetrics(78), _user32.GetSystemMetrics(79)
    x = max(vx, min(x, vx + vw - W))
    y = max(vy, min(y, vy + vh - H))
    return x, y


# ---------------------------------------------------------------- 알림 팝업 (위젯과 같은 디자인)
POP_W, POP_H, POP_SEC = 370, 96, 8
_popups = []   # 떠 있는 팝업 (아래에서부터 쌓기)


def work_area():
    r = _RECT()
    _user32.SystemParametersInfoW(48, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA (주 모니터, 작업표시줄 제외)
    return r.l, r.t, r.r, r.b


class Popup(tk.Toplevel):
    """오른쪽 아래에서 올라오는 파스텔 알림 카드. 클릭하면 닫힘, POP_SEC 뒤 자동으로 사라짐."""

    def __init__(self, master, text, color, prov, on_click=None, seconds=POP_SEC):
        super().__init__(master)
        self.master_widget = master
        self.text, self.color = text, color
        self.on_click, self.seconds = on_click, seconds
        self.body, self.mark = "#f4a460", "#d98a3f"
        for k, n, a, b, m in PROVIDERS_ALL:
            if k == prov:
                self.body, self.mark = b, m
        self.overrideredirect(True)
        self.configure(bg=CHROMA)
        self.attributes("-transparentcolor", CHROMA)
        self.attributes("-topmost", True)
        self.canvas = tk.Canvas(self, width=POP_W, height=POP_H, bg=CHROMA, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._clicked)
        self._frame, self._t0 = 0, time.monotonic()
        self._photo = None
        _popups.append(self)
        self._place()
        self._anim()

    def _place(self):
        l, t, r, b = work_area()
        idx = _popups.index(self)
        x = r - POP_W - 16
        y = b - POP_H - 16 - idx * (POP_H + 10)
        self.geometry(f"{POP_W}x{POP_H}+{x}+{y}")

    def _render(self):
        S = SS
        img = Image.new("RGB", (POP_W * S, POP_H * S), CARD)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, POP_W * S - 1, POP_H * S - 1), radius=16 * S, outline=CARD_EDGE, width=2 * S)
        d.rounded_rectangle((10 * S, 14 * S, 14 * S, (POP_H - 14) * S), radius=2 * S, fill=self.color)  # 강조 바
        w = self.master_widget
        d.text((84 * S, 10 * S), "AI 사용량", font=w.f_tiny, fill=INK_SOFT)
        # 본문: 두 줄까지 접기
        words, lines, cur = self.text.split(" "), [], ""
        for wd in words:
            trial = (cur + " " + wd).strip()
            if d.textlength(trial, font=w.f_pop) > (POP_W - 98) * S and cur:
                lines.append(cur); cur = wd
            else:
                cur = trial
        lines.append(cur)
        for i, ln in enumerate(lines[:2]):
            d.text((84 * S, (32 + i * 22) * S), ln, font=w.f_pop, fill=INK)
        out = img.resize((POP_W, POP_H), Image.LANCZOS)
        mask = Image.new("L", (POP_W, POP_H), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, POP_W - 1, POP_H - 1), radius=16, fill=255)
        out = Image.composite(out, Image.new("RGB", (POP_W, POP_H), CHROMA), mask)
        w._cat(ImageDraw.Draw(out), 22, 30, self._frame, self.body, self.mark, False, px=CAT_PX_POPUP)
        return out

    def _anim(self):
        try:
            if time.monotonic() - self._t0 > self.seconds:
                self.close(); return
            self._frame = (self._frame + 1) % len(CAT_LEGS)
            self._photo = ImageTk.PhotoImage(self._render())
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
            self.after(140, self._anim)
        except tk.TclError:
            pass

    def _clicked(self, _e):
        cb = self.on_click
        self.close()
        if cb:
            cb()

    def close(self):
        if self in _popups:
            _popups.remove(self)
        try:
            self.destroy()
        except tk.TclError:
            pass
        for p in _popups:
            try:
                p._place()
            except tk.TclError:
                pass


# ---------------------------------------------------------------- 위젯
class Widget(tk.Tk):
    def __init__(self):
        super().__init__()
        self.state = self._load_state()
        self.usage = self.state.get("last_usage") or {}
        self.errors = {}
        self.error = None
        self.last_ok = None
        self.banner = None          # (text, color, expire_monotonic)
        self._prev = {}             # 알림 판정용 직전 값: (prov, win) -> (pct, resets_at)
        self._drag = None
        self._photo = None
        self._base = None           # 캐시된 카드 렌더 (고양이 제외)
        self._base_key = None
        self._last_frame_key = None
        self._hidden = False
        self.mini = bool(self.state.get("mini", False))
        self._anim = {k: {"frame": 0, "next": 0.0} for k, *_ in PROVIDERS_ALL}
        apply_layout(self.state.get("show_gpt", True))
        self._buttons = {}

        self.f_title = font("Paperlogy-7Bold.ttf", 19)
        self.f_num = font("Paperlogy-7Bold.ttf", 15)
        self.f_num_s = font("Paperlogy-7Bold.ttf", 12)
        self.f_small = font("Pretendard-SemiBold.ttf", 12)
        self.f_tiny = font("Pretendard-Medium.ttf", 11)
        self.f_pop = font("Pretendard-SemiBold.ttf", 13)
        self.f_btn = font("Pretendard-Bold.ttf", 11)
        self.f_z = font("Pretendard-Bold.ttf", 9, scale=1)

        self.title("AI Usage")
        self.overrideredirect(True)
        self.configure(bg=CHROMA)
        self.attributes("-transparentcolor", CHROMA)
        self.attributes("-topmost", self.state.get("topmost", True))
        self.attributes("-alpha", self.state.get("alpha", 1.0))
        x, y = clamp_to_screen(self.state.get("x", 12), self.state.get("y", 12))
        self.geometry(f"{W}x{H}+{x}+{y}")

        self.canvas = tk.Canvas(self, width=W, height=H, bg=CHROMA, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.canvas.bind("<Double-Button-1>", lambda _e: self.toggle_mini())
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", self._popup_menu)
        self.canvas.bind("<Motion>", self._motion)

        self._build_menu()
        self._apply_geometry()
        self._ticks = 0
        self._fetching = False
        self._interval = REFRESH_SEC
        self._next_fetch = 0.0
        self._unchanged = 0
        self._last_pcts = None
        self.refresh()
        self._tick()

    # ------------------------------------------------------------ 메뉴
    def _build_menu(self):
        kw = dict(tearoff=0, bg=CARD, fg=INK, activebackground="#ffe9d6", activeforeground=INK)
        self.menu = tk.Menu(self, **kw)
        self.menu.add_command(label="지금 새로고침", command=self.refresh)
        self.gpt_var = tk.BooleanVar(value=self.state.get("show_gpt", True))
        self.menu.add_checkbutton(label="GPT(Codex) 표시", variable=self.gpt_var, command=self._toggle_gpt)
        self.mini_var = tk.BooleanVar(value=self.mini)
        self.menu.add_checkbutton(label="작업표시줄 미니 모드 (더블클릭으로 전환)", variable=self.mini_var,
                                  command=lambda: self.toggle_mini(self.mini_var.get()))

        alpha_menu = tk.Menu(self.menu, **kw)
        self.alpha_var = tk.DoubleVar(value=self.state.get("alpha", 1.0))
        for label, v in (("100%", 1.0), ("85%", 0.85), ("70%", 0.7), ("55%", 0.55)):
            alpha_menu.add_radiobutton(label=label, value=v, variable=self.alpha_var, command=self._set_alpha)
        self.menu.add_cascade(label="투명도", menu=alpha_menu)

        self.pace_var = tk.BooleanVar(value=self.state.get("pace", False))
        self.menu.add_checkbutton(label="페이스 예측 표시", variable=self.pace_var,
                                  command=lambda: self._set("pace", self.pace_var.get()))
        self.ct_var = tk.BooleanVar(value=self.state.get("click_through", False))
        self.menu.add_checkbutton(label="클릭 통과 (바탕화면·Ctrl 누를 때만 조작)", variable=self.ct_var,
                                  command=lambda: self._set("click_through", self.ct_var.get()))
        self.popup_var = tk.BooleanVar(value=self.state.get("popup", True))
        self.menu.add_checkbutton(label="알림 팝업 (고양이 카드)", variable=self.popup_var,
                                  command=lambda: self._set("popup", self.popup_var.get()))
        self.toast_var = tk.BooleanVar(value=self.state.get("toast", False))
        self.menu.add_checkbutton(label="Windows 알림 센터로도 알림", variable=self.toast_var,
                                  command=lambda: self._set("toast", self.toast_var.get()))
        self.sound_var = tk.BooleanVar(value=self.state.get("sound", True))
        self.menu.add_checkbutton(label="알림 소리", variable=self.sound_var,
                                  command=lambda: self._set("sound", self.sound_var.get()))
        self.topmost_var = tk.BooleanVar(value=self.state.get("topmost", True))
        self.menu.add_checkbutton(label="항상 위에 표시", variable=self.topmost_var, command=self._toggle_topmost)
        self.fs_var = tk.BooleanVar(value=self.state.get("hide_fullscreen", True))
        self.menu.add_checkbutton(label="전체화면 앱 실행 시 숨김", variable=self.fs_var,
                                  command=lambda: self._set("hide_fullscreen", self.fs_var.get()))
        self.autostart_var = tk.BooleanVar(value=STARTUP_BAT.exists())
        self.menu.add_checkbutton(label="Windows 시작 시 자동 실행", variable=self.autostart_var,
                                  command=self._toggle_autostart)
        self.menu.add_separator()
        self.upd_var = tk.BooleanVar(value=self.state.get("auto_update", True))
        self.menu.add_checkbutton(label="새 버전 자동 확인 (하루 1회)", variable=self.upd_var,
                                  command=lambda: self._set("auto_update", self.upd_var.get()))
        self.menu.add_command(label=f"지금 업데이트 확인 (현재 v{VERSION})", command=lambda: self.check_update(manual=True))
        self.menu.add_separator()
        self.menu.add_command(label="종료", command=self.destroy)

    def _toggle_gpt(self):
        v = self.gpt_var.get()
        self._set("show_gpt", v)
        apply_layout(v)
        self._base_key = None
        self._apply_geometry()
        self.refresh()

    def toggle_mini(self, value=None):
        self.mini = (not self.mini) if value is None else bool(value)
        self.mini_var.set(self.mini)
        self._set("mini", self.mini)
        self._base_key = None
        self._apply_geometry()

    def _apply_geometry(self):
        if self.mini:
            w, h = MINI_W, MINI_H
            slot = taskbar_slot(w, h)
            if slot is None:
                l, t, r, b = work_area()
                slot = (r - w - 12, b - h - 12)
            self._mini_slot = slot
            x, y = slot[0] + int(self.state.get("mini_dx", 0)), slot[1]   # mini_dx: 사용자가 드래그로 정한 좌우 오프셋
        else:
            w, h = W, H
            x, y = clamp_to_screen(self.state.get("x", 12), self.state.get("y", 12))
        self.canvas.config(width=w, height=h)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self._last_frame_key = None
        if self.mini:  # 작업표시줄보다 위에 있도록 재확인 (HWND_TOPMOST, NOSIZE|NOMOVE|NOACTIVATE)
            _user32.SetWindowPos(self._hwnd(), HWND_TOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)

    def _set(self, key, value):
        self.state[key] = value
        self._save_state()

    def _set_alpha(self):
        v = self.alpha_var.get()
        self.attributes("-alpha", v)
        self._set("alpha", v)

    def _toggle_topmost(self):
        v = self.topmost_var.get()
        self.attributes("-topmost", v)
        self._set("topmost", v)

    def _toggle_autostart(self):
        if self.autostart_var.get():
            launcher = Path(os.environ["LOCALAPPDATA"]) / "Python" / "bin" / "pythonw.exe"  # 버전 무관 런처
            pyw = Path(sys.executable).with_name("pythonw.exe")
            exe = launcher if launcher.exists() else (pyw if pyw.exists() else Path(sys.executable))
            STARTUP_DIR.mkdir(parents=True, exist_ok=True)
            STARTUP_BAT.write_text(
                f'@echo off\r\nstart "" "{exe}" "{Path(__file__).resolve()}"\r\n', encoding="utf-8")
        else:
            try:
                STARTUP_BAT.unlink()
            except FileNotFoundError:
                pass

    # ------------------------------------------------------------ 상태 저장
    def _load_state(self):
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _save_state(self):
        try:
            CONFIG_PATH.write_text(json.dumps(self.state), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 입력
    def _hit(self, x, y):
        for name, (x0, y0, x1, y1) in self._buttons.items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return name
        return None

    def _motion(self, e):
        self.canvas.config(cursor="hand2" if self._hit(e.x, e.y) else "")

    def _press(self, e):
        if self._hit(e.x, e.y):
            self._drag = None
            return
        self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _drag_move(self, e):
        if self._drag:
            if self.mini:   # 미니 모드: 작업표시줄 안에서 좌우로만 이동
                self.geometry(f"+{e.x_root - self._drag[0]}+{self.winfo_y()}")
            else:
                self.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _release(self, e):
        if self._drag:
            self._drag = None
            if self.mini:
                self.state["mini_dx"] = self.winfo_x() - self._mini_slot[0]
            else:
                self.state["x"], self.state["y"] = self.winfo_x(), self.winfo_y()
            self._save_state()
            return
        hit = self._hit(e.x, e.y)
        if hit == "close":
            self.destroy()
        elif hit == "refresh":
            self.refresh()

    def _popup_menu(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)

    # ------------------------------------------------------------ 데이터
    def refresh(self):
        if self._fetching:
            return
        self._fetching = True
        threading.Thread(target=self._fetch_bg, daemon=True).start()

    def _fetch_bg(self):
        try:
            data, errors = fetch_usage(tuple(k for k, *_ in PROVIDERS))
            self.after(0, self._apply, data, errors, None)
        except Exception as ex:  # noqa: BLE001
            self.after(0, self._apply, None, {}, str(ex))

    def _pcts_snapshot(self):
        return tuple(((self.usage.get(k) or {}).get("primary") or {}).get("used_percent") for k, *_ in PROVIDERS)

    def _schedule_next(self, ok):
        """적응형 간격 결정. ok=False면 백오프."""
        if not ok:
            self._interval = min(max(self._interval * 2, REFRESH_SEC), BACKOFF_MAX)
        else:
            now_pcts = self._pcts_snapshot()
            rising = (self._last_pcts is not None and any(
                a is not None and b is not None and b > a for a, b in zip(self._last_pcts, now_pcts)))
            self._last_pcts = now_pcts
            if rising:
                self._unchanged = 0
                self._interval = REFRESH_FAST
            else:
                self._unchanged += 1
                if self._interval == REFRESH_FAST and self._unchanged < 2:
                    pass  # 퍼센트는 정수라 1분 안에 안 오를 수 있음 → 빠른 주기를 한 번 더 유지
                else:
                    self._interval = REFRESH_IDLE if self._unchanged >= IDLE_AFTER else REFRESH_SEC
        self._next_fetch = time.monotonic() + self._interval
        log.info("next fetch in %ds (%s)", self._interval, "ok" if ok else "backoff")

    def _apply(self, data, errors, err):
        self._fetching = False
        if data:
            self._check_alerts(data)
            self.usage.update(data)
            self.last_ok = datetime.now()
            self.error = None
            ok_at = self.state.setdefault("ok_at", {})
            for prov in data:
                ok_at[prov] = time.time()
            self.state["last_usage"] = self.usage
            self._save_state()
        else:
            self.error = err or "조회 실패"
            log.warning("fetch failed: %s", self.error)
        self.errors = errors or {}
        for prov, msg in self.errors.items():
            log.info("provider %s: %s", prov, msg[:160])
        self._schedule_next(ok=not (self.errors or self.error))

    def _check_alerts(self, data):
        """80% 돌파 / 100% 도달 / 리셋을 감지해 배너를 띄운다."""
        names = {k: n for k, n, *_ in PROVIDERS}
        accents = {k: a for k, n, a, *_ in PROVIDERS}
        for prov, u in data.items():
            for wkey, wname in WINDOWS:
                win = u.get(wkey) or {}
                pct, reset = win.get("used_percent"), win.get("resets_at")
                if pct is None:
                    continue
                prev_pct, prev_reset = self._prev.get((prov, wkey), (None, None))
                self._prev[(prov, wkey)] = (pct, reset)
                if prev_pct is None:
                    continue
                label = f"{names.get(prov, prov)} {wname}"
                if prev_reset and reset and reset != prev_reset and pct < prev_pct:
                    self._alert(f"{label} 한도가 리셋됐어요 ({int(pct)}%)", C_OK, prov)
                elif prev_pct < 100 <= pct:
                    self._alert(f"{label} 한도 소진 · {fmt_remaining(reset)} 리셋", C_BAD, prov)
                elif prev_pct < 80 <= pct:
                    self._alert(f"{label} 80% 넘었어요 · {fmt_remaining(reset)} 리셋", accents.get(prov, C_WARN), prov)

    # ------------------------------------------------------------ 자동 업데이트
    def check_update(self, manual=False):
        def run():
            try:
                found = check_update()
            except Exception as ex:  # noqa: BLE001
                log.warning("update check failed: %s", ex)
                if manual:
                    self.after(0, lambda: Popup(self, f"업데이트 확인 실패: {str(ex)[:60]}", C_WARN, None))
                return
            self.after(0, self._update_found, found, manual)
        self.state["last_update_check"] = time.time()
        self._save_state()
        threading.Thread(target=run, daemon=True).start()

    def _update_found(self, found, manual):
        if not found:
            if manual:
                Popup(self, f"최신 버전이에요 (v{VERSION})", C_OK, None)
            return
        ver, url = found
        log.info("update available: v%s", ver)
        Popup(self, f"새 버전 v{ver} 있어요 · 여기를 클릭하면 업데이트", C_OK, None,
              on_click=lambda: self._do_update(ver, url), seconds=60)

    def _do_update(self, ver, url):
        Popup(self, f"v{ver} 내려받는 중…", INK_SOFT, None, seconds=30)

        def run():
            try:
                apply_update(url, Path(__file__).resolve().parent)
                self.after(0, self._restart_after_update, ver)
            except Exception as ex:  # noqa: BLE001
                log.exception("update failed")
                self.after(0, lambda: Popup(self, f"업데이트 실패: {str(ex)[:60]}", C_BAD, None))
        threading.Thread(target=run, daemon=True).start()

    def _restart_after_update(self, ver):
        log.info("updated to v%s, restarting", ver)
        # 콘솔 없는 프로세스에서 cmd/timeout은 신뢰할 수 없으므로, 파이썬 헬퍼가 3초 기다렸다가
        # (현재 프로세스가 끝나 뮤텍스가 풀린 뒤) 새 버전을 띄운다.
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        if exe.name.lower() == "python.exe" and pyw.exists():
            exe = pyw
        script = str(Path(__file__).resolve())
        helper = ("import time, subprocess, sys; time.sleep(3); "
                  f"subprocess.Popen([sys.executable, r'{script}'], close_fds=True)")
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        subprocess.Popen([str(exe), "-c", helper], creationflags=flags | 0x00000008 | 0x00000200, close_fds=True)
        self.destroy()

    def _alert(self, text, color, prov=None):
        self.banner = (text, color, time.monotonic() + BANNER_SEC)
        log.info("alert: %s", text)
        if self.state.get("popup", True):
            try:
                Popup(self, text, color, prov)
            except Exception:  # noqa: BLE001
                log.exception("popup failed")
        if self.state.get("toast", False) and TOAST_PS1.exists():
            notify_windows("AI 사용량 위젯", text)
        if self.state.get("sound", True):
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ 루프
    def _tick(self):
        try:
            self._ticks += 1
            if time.monotonic() >= self._next_fetch:
                self._next_fetch = time.monotonic() + BACKOFF_MAX  # 응답 전 중복 방지, _apply에서 재설정
                self.refresh()
            if self._ticks % 2 == 0:
                self._update_click_through()
            if self._ticks % 10 == 0:
                self._check_fullscreen()
                if (self._ticks >= 300 and self.state.get("auto_update", True)
                        and time.time() - self.state.get("last_update_check", 0) > UPDATE_CHECK_SEC):
                    self.check_update()
                if self.mini and not self._hidden and not self._drag:
                    self._apply_geometry()
            if self.banner and time.monotonic() > self.banner[2]:
                self.banner = None
            self._advance_cats()
            if not self._hidden:
                self.draw()
        except Exception:  # noqa: BLE001  루프가 죽어 위젯이 멈추는 일 방지
            log.exception("tick failed")
        finally:
            self.after(ANIM_MS, self._tick)

    def _hwnd(self):
        return _user32.GetAncestor(self.winfo_id(), 2)  # GA_ROOT

    def _update_click_through(self):
        want = (self.state.get("click_through", False)
                and not desktop_is_foreground(self._hwnd())
                and not ctrl_down())
        changed = set_click_through(self._hwnd(), want)
        if changed or want != getattr(self, "_ct_now", None):
            self._ct_now = want
            self._base_key = None  # 상태 표시 갱신

    def _check_fullscreen(self):
        want_hide = self.state.get("hide_fullscreen", True) and foreground_is_fullscreen(self._hwnd())
        if want_hide and not self._hidden:
            self._hidden = True
            self.withdraw()
        elif not want_hide and self._hidden:
            self._hidden = False
            self.deiconify()
            self.overrideredirect(True)
            self.attributes("-topmost", self.state.get("topmost", True))

    def _advance_cats(self):
        now = time.monotonic()
        for key, *_ in PROVIDERS:
            pct = ((self.usage.get(key) or {}).get("primary") or {}).get("used_percent")
            a = self._anim[key]
            if pct is None or pct >= 100:
                continue
            interval = max(0.07, 0.42 - pct * 0.0035)   # 0%: 0.42s, 100%: 0.07s
            if now >= a["next"]:
                a["frame"] = (a["frame"] + 1) % len(CAT_LEGS)
                a["next"] = now + interval

    # ------------------------------------------------------------ 그리기
    def _is_stale(self, prov):
        """마지막 성공이 STALE_AFTER_SEC보다 오래됐을 때만 회색 처리."""
        ok = (self.state.get("ok_at") or {}).get(prov)
        return ok is None or (time.time() - ok) > STALE_AFTER_SEC

    def _fail_note(self):
        """조회 실패 중인 제공자를 상태줄 문구로 (값은 그대로 컬러 표시)."""
        names = {k: n for k, n, *_ in PROVIDERS}
        failed = list(self.errors) if self.error is None else [k for k, *_ in PROVIDERS]
        if not failed:
            return None
        ok_at = self.state.get("ok_at") or {}
        parts = []
        for k in failed:
            t = ok_at.get(k)
            when = datetime.fromtimestamp(t).strftime("%H:%M") + " 값" if t else "값 없음"
            parts.append(f"{names.get(k, k)} 조회 지연 ({when})")
        return " · ".join(parts)

    def _status(self):
        if self.banner:
            return self.banner[0], self.banner[1], True
        note = self._fail_note()
        if note:
            return note, INK_SOFT, False
        if self.last_ok:
            ct = " · 클릭 통과 중" if getattr(self, "_ct_now", False) else ""
            age_min = int((datetime.now() - self.last_ok).total_seconds() // 60)
            if age_min >= STALE_WARN_MIN:   # 오래된 값은 숨기지 않고 드러냄
                return f"{age_min}분 전 값{ct}", C_WARN, False
            fast = " ⚡" if self._interval == REFRESH_FAST else ""
            return f"갱신 {self.last_ok.strftime('%H:%M')}{fast}{ct}", INK_SOFT, False
        return "불러오는 중…", INK_SOFT, False

    def _base_key_now(self):
        """카드 본체를 다시 그려야 하는지 판단하는 키 (값·문구가 바뀔 때만 재렌더)."""
        parts = []
        for key, *_ in PROVIDERS:
            u = self.usage.get(key) or {}
            for wkey, _ in WINDOWS:
                win = u.get(wkey) or {}
                parts.append((win.get("used_percent"), fmt_remaining(win.get("resets_at"))))
            fb = extra_window(u, "fable")
            parts.append((fb.get("used_percent"), u.get("login_method"), self._is_stale(key)))
        parts.append(self._status()[:2])
        parts.append((tuple(sorted(self.errors)), self.error, self.state.get("pace", False), getattr(self, "_ct_now", False)))
        return tuple(parts)

    def draw(self):
        key = (self._base_key_now(), self.mini)
        if key != self._base_key:
            self._base = self._render_mini() if self.mini else self._render_base()
            self._base_key = key
        # 고양이 프레임/z 위치가 안 바뀌었으면 화면 갱신 생략 (CPU 절약)
        cat_key = tuple((k, self._anim[k]["frame"], (self._ticks // 6) % 3) for k, *_ in PROVIDERS)
        frame_key = (key, cat_key)
        if frame_key == self._last_frame_key:
            return
        self._last_frame_key = frame_key

        out = self._base.copy()
        d = ImageDraw.Draw(out)
        for i, (pkey, name, accent, body, mark) in enumerate(PROVIDERS):
            pct5 = ((self.usage.get(pkey) or {}).get("primary") or {}).get("used_percent")
            sleeping = pct5 is None or pct5 >= 100
            if self.mini:
                self._cat_head(d, 9 + i * MINI_SEC_W, 8, self._anim[pkey]["frame"], body, mark, sleeping)
            else:
                ox = 10 + i * SEC_W
                self._cat(d, ox, 9, self._anim[pkey]["frame"], body, mark, sleeping)
        if os.environ.get("WIDGET_SNAP"):
            out.save(os.environ["WIDGET_SNAP"])
        self._photo = ImageTk.PhotoImage(out)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")

    def _render_mini(self):
        """작업표시줄용 알약: [고양이] 5h% · 7d%  |  [고양이] 5h% · 7d%"""
        S = SS
        img = Image.new("RGB", (MINI_W * S, MINI_H * S), CARD)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, MINI_W * S - 1, MINI_H * S - 1), radius=(MINI_H // 2) * S,
                            outline=CARD_EDGE, width=2 * S)
        self._buttons = {}
        half = MINI_SEC_W
        for i, (key, name, accent, body, mark) in enumerate(PROVIDERS):
            ox = 8 + i * half
            u = self.usage.get(key) or {}
            stale = self._is_stale(key)
            p5 = (u.get("primary") or {}).get("used_percent")
            p7 = (u.get("secondary") or {}).get("used_percent")
            t5 = "–" if p5 is None else f"{int(round(p5))}%"
            t7 = "–" if p7 is None else f"{int(round(p7))}%"
            x = ox + 30
            d.text((x * S, (MINI_H / 2) * S), t5, font=self.f_num,
                   fill=(C_STALE if stale else pct_color(p5)), anchor="lm")
            x += d.textlength(t5, font=self.f_num) / S + 4
            d.text((x * S, (MINI_H / 2) * S), "·", font=self.f_tiny, fill=INK_SOFT, anchor="lm")
            x += 7
            d.text((x * S, (MINI_H / 2) * S), t7, font=self.f_small,
                   fill=(C_STALE if stale else pct_color(p7)), anchor="lm")
            if i < len(PROVIDERS) - 1:
                lx = (ox + half - 6) * S
                d.line((lx, 8 * S, lx, (MINI_H - 8) * S), fill=TRACK, width=2 * S)
        out = img.resize((MINI_W, MINI_H), Image.LANCZOS)
        mask = Image.new("L", (MINI_W, MINI_H), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, MINI_W - 1, MINI_H - 1), radius=MINI_H // 2, fill=255)
        return Image.composite(out, Image.new("RGB", (MINI_W, MINI_H), CHROMA), mask)

    def _render_base(self):
        S = SS
        img = Image.new("RGB", (W * S, H * S), CARD)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, W * S - 1, H * S - 1), radius=RADIUS * S, outline=CARD_EDGE, width=2 * S)

        self._buttons = {}
        half = SEC_W
        for i, (key, name, accent, body, mark) in enumerate(PROVIDERS):
            ox = 10 + i * half
            u = self.usage.get(key) or {}
            stale = self._is_stale(key)

            d.text(((ox + 40) * S, 4 * S), name, font=self.f_title, fill=accent)
            sub = "오래된 값 (1시간 이상 조회 실패)" if stale and u else (u.get("login_method") or "")
            d.text(((ox + 40) * S, 29 * S), sub, font=self.f_tiny, fill=C_WARN if stale and u else INK_SOFT)

            # 추가 창 (Claude: Fable 전용 주간) - 작은 막대
            fb = extra_window(u, "fable")
            if fb.get("used_percent") is not None:
                fp = fb["used_percent"]
                bx0, bx1, by = ox + 146, ox + half - 30, 49
                d.text(((ox + 40) * S, (by - 5) * S), f"Fable 주간 {int(fp)}%", font=self.f_tiny, fill=INK_SOFT)
                d.rounded_rectangle((bx0 * S, by * S, bx1 * S, (by + 4) * S), radius=2 * S, fill=TRACK)
                fx = bx0 + (bx1 - bx0) * min(fp, 100) / 100
                if fx > bx0 + 2:
                    d.rounded_rectangle((bx0 * S, by * S, fx * S, (by + 4) * S), radius=2 * S,
                                        fill=C_STALE if stale else pct_color(fp))

            for j, (wkey, wname) in enumerate(WINDOWS):
                win = u.get(wkey) or {}
                gx, gy = ox + j * 138, 62
                self._gauge(d, gx, gy, win.get("used_percent"), stale)
                d.text(((gx + GAUGE + 6) * S, (gy + 9) * S), wname, font=self.f_small, fill=INK)
                d.text(((gx + GAUGE + 6) * S, (gy + 27) * S), fmt_remaining(win.get("resets_at")),
                       font=self.f_tiny, fill=INK_SOFT)
                if self.state.get("pace", False) and not stale:
                    hint = pace_hint(u, wkey)
                    if hint:
                        d.ellipse(((gx + GAUGE + 7) * S, (gy + 48) * S, (gx + GAUGE + 12) * S, (gy + 53) * S), fill=hint[1])
                        d.text(((gx + GAUGE + 15) * S, (gy + 43) * S), hint[0], font=self.f_tiny, fill=hint[1])

            if i < len(PROVIDERS) - 1:
                lx = (ox + half - 6) * S
                d.line((lx, 12 * S, lx, (H - 12) * S), fill=TRACK, width=2 * S)

        # 상태 / 알림 배너 (우하단)
        msg, col, is_banner = self._status()
        rx, cy = W - 56, 14   # 새로고침 버튼 왼쪽에 붙임
        if is_banner:
            tw = d.textlength(msg, font=self.f_tiny)
            d.rounded_rectangle((rx * S - tw - 12 * S, (cy - 8) * S, rx * S, (cy + 8) * S), radius=6 * S, fill=col)
            d.text(((rx - 6) * S, cy * S), msg, font=self.f_tiny, fill="#ffffff", anchor="rm")
        else:
            d.text((rx * S, cy * S), msg, font=self.f_tiny, fill=col, anchor="rm")

        # 버튼 (↻, ✕)
        for label, bx in (("refresh", W - 38), ("close", W - 18)):
            r, cx, cy = 7, bx, 14
            d.ellipse(((cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S), fill="#f6eadf")
            if label == "refresh":
                d.text((cx * S, cy * S), "↻", font=self.f_btn, fill=INK_SOFT, anchor="mm")
            else:
                a = 2.8
                d.line(((cx - a) * S, (cy - a) * S, (cx + a) * S, (cy + a) * S), fill=INK_SOFT, width=2 * S)
                d.line(((cx - a) * S, (cy + a) * S, (cx + a) * S, (cy - a) * S), fill=INK_SOFT, width=2 * S)
            self._buttons[label] = (cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2)

        out = img.resize((W, H), Image.LANCZOS)
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), radius=RADIUS, fill=255)
        return Image.composite(out, Image.new("RGB", (W, H), CHROMA), mask)

    def _gauge(self, d, x, y, pct, stale):
        S = SS
        R = GAUGE * S / 2
        w = RING_W * S
        cx, cy = x * S + R, y * S + R
        outer = (cx - R, cy - R, cx + R, cy + R)
        inner = (cx - R + w, cy - R + w, cx + R - w, cy + R - w)
        d.ellipse(outer, fill=TRACK)
        if pct is not None:
            col = C_STALE if stale else pct_color(pct)
            sweep = max(1, min(359.9, pct * 3.6))
            d.pieslice(outer, -90, -90 + sweep, fill=col)
            rm = R - w / 2
            for ang in (-90, -90 + sweep):
                a = math.radians(ang)
                px, py = cx + rm * math.cos(a), cy + rm * math.sin(a)
                d.ellipse((px - w / 2, py - w / 2, px + w / 2, py + w / 2), fill=col)
            txt = f"{int(round(pct))}%"
        else:
            txt = "–"
        d.ellipse(inner, fill=CARD)
        f = self.f_num_s if len(txt) >= 4 else self.f_num
        d.text((cx, cy), txt, font=f, fill=INK_SOFT if stale else INK, anchor="mm")

    def _cat_head(self, d, x, y, fi, body, mark, sleeping, px=CAT_PX_MINI):
        """미니 모드용 얼굴 아이콘."""
        colors = {"b": body, "e": "#2f2a28", "p": "#ffb7c5", "m": "#2f2a28", "-": "#2f2a28"}
        rows = CAT_HEAD_SLEEP if sleeping else CAT_HEAD
        dy = 0 if sleeping else CAT_HEAD_BOB[fi]
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                col = colors.get(ch)
                if col:
                    x0, y0 = x + c * px, y + dy + r * px
                    d.rectangle((x0, y0, x0 + px - 1, y0 + px - 1), fill=col)
        if sleeping:
            phase = (self._ticks // 6) % 3
            d.text((x + 11 * px - 2, y - 6 + phase * 2), "z", font=self.f_z, fill=INK_SOFT)

    def _cat(self, d, x, y, fi, body, mark, sleeping, px=CAT_PX):
        colors = {"b": body, "s": mark, "e": "#2f2a28", "p": "#ffb7c5", "m": "#2f2a28", "-": "#2f2a28"}
        if sleeping:
            rows, bounce = CAT_SLEEP_BODY + CAT_SLEEP_LEGS, 0
        else:
            rows, bounce = CAT_BODY + CAT_LEGS[fi], CAT_BOUNCE[fi]
        for r, row in enumerate(rows):
            dy = bounce if r < len(CAT_BODY) else 0
            for c, ch in enumerate(row):
                col = colors.get(ch)
                if col:
                    x0, y0 = x + c * px, y + dy + r * px
                    d.rectangle((x0, y0, x0 + px - 1, y0 + px - 1), fill=col)
        if sleeping:
            phase = (self._ticks // 6) % 3
            d.text((x + 17 * px - 4, y - 2 + phase * 2), "z", font=self.f_z, fill=INK_SOFT)


if __name__ == "__main__":
    if not acquire_single_instance():
        sys.exit(0)  # 이미 실행 중
    if not CODEXBAR_CLI.exists():
        import tkinter.messagebox as mb
        root = tk.Tk(); root.withdraw()
        mb.showerror("AI Usage Widget", f"codexbar-cli.exe를 찾을 수 없습니다:\n{CODEXBAR_CLI}\n\nWin-CodexBar를 먼저 설치하세요.")
        sys.exit(1)
    log.info("start v%s", VERSION)
    Widget().mainloop()
    log.info("exit")

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
  - 조회 실패 시 마지막 값을 평소처럼 컬러로 유지(상태줄에만 표시), 1시간 넘게 실패해야 회색 처리 + 다음 조회 1회 건너뛰기
  - 카드 본체는 값이 바뀔 때만 다시 그리고, 매 틱에는 고양이만 얹음 (CPU 절약)
"""

import ctypes
import json
import math
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import winsound
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
REFRESH_SEC = 180                     # 사용량 재조회 주기 (너무 짧으면 Anthropic 조회 API가 일시 차단함)
CLI_TIMEOUT = 90
ANIM_MS = 100                         # 애니메이션 틱
BANNER_SEC = 90                       # 알림 배너 유지 시간
STALE_AFTER_SEC = 3600                # 마지막 성공 후 이 시간이 지나야 회색(오래된 값) 처리
CONFIG_PATH = Path(__file__).with_name("widget_state.json")
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
PROVIDERS = [
    # key, 표시명, 강조색, 고양이 몸색, 고양이 무늬색
    ("claude", "Claude", "#f28c6b", "#f4a460", "#d98a3f"),
    ("codex", "GPT", "#6fbfa3", "#a9b4c2", "#7f8b9b"),
]
WINDOWS = [("primary", "5시간"), ("secondary", "7일")]

# 레이아웃 (논리 px). 카드는 SS배 슈퍼샘플링 후 축소, 고양이는 원본 도트.
SS = 2
W, H = 440, 122
RADIUS = 18
GAUGE = 50
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
CAT_PX = 3  # 픽셀 1칸 = 3px (논리)


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


def fetch_usage():
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    out = subprocess.run(
        [str(CODEXBAR_CLI), "usage", "-p", "both", "--json", "--no-color"],
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
        mi = _MONITORINFO(); mi.cbSize = ctypes.sizeof(_MONITORINFO)
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


def clamp_to_screen(x, y):
    vx, vy = _user32.GetSystemMetrics(76), _user32.GetSystemMetrics(77)
    vw, vh = _user32.GetSystemMetrics(78), _user32.GetSystemMetrics(79)
    x = max(vx, min(x, vx + vw - W))
    y = max(vy, min(y, vy + vh - H))
    return x, y


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
        self._anim = {k: {"frame": 0, "next": 0.0} for k, *_ in PROVIDERS}
        self._buttons = {}

        self.f_title = font("Paperlogy-7Bold.ttf", 14)
        self.f_num = font("Paperlogy-7Bold.ttf", 11)
        self.f_num_s = font("Paperlogy-7Bold.ttf", 9)
        self.f_small = font("Pretendard-Medium.ttf", 9)
        self.f_tiny = font("Pretendard-Medium.ttf", 8)
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
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", self._popup_menu)
        self.canvas.bind("<Motion>", self._motion)

        self._build_menu()
        self._ticks = 0
        self._skip = 0
        self.refresh()
        self._tick()

    # ------------------------------------------------------------ 메뉴
    def _build_menu(self):
        kw = dict(tearoff=0, bg=CARD, fg=INK, activebackground="#ffe9d6", activeforeground=INK)
        self.menu = tk.Menu(self, **kw)
        self.menu.add_command(label="지금 새로고침", command=self.refresh)

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
        self.toast_var = tk.BooleanVar(value=self.state.get("toast", True))
        self.menu.add_checkbutton(label="Windows 알림 센터로 알림", variable=self.toast_var,
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
        self.menu.add_command(label="종료", command=self.destroy)

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
            self.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _release(self, e):
        if self._drag:
            self._drag = None
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
        threading.Thread(target=self._fetch_bg, daemon=True).start()

    def _fetch_bg(self):
        try:
            data, errors = fetch_usage()
            self.after(0, self._apply, data, errors, None)
        except Exception as ex:  # noqa: BLE001
            self.after(0, self._apply, None, {}, str(ex))

    def _apply(self, data, errors, err):
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
        if self.errors or self.error:
            self._skip = 1

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
                    self._alert(f"{label} 한도가 리셋됐어요 ({int(pct)}%)", C_OK)
                elif prev_pct < 100 <= pct:
                    self._alert(f"{label} 한도 소진 · {fmt_remaining(reset)} 리셋", C_BAD)
                elif prev_pct < 80 <= pct:
                    self._alert(f"{label} 80% 넘었어요 · {fmt_remaining(reset)} 리셋", accents.get(prov, C_WARN))

    def _alert(self, text, color):
        self.banner = (text, color, time.monotonic() + BANNER_SEC)
        log.info("alert: %s", text)
        if self.state.get("toast", True) and TOAST_PS1.exists():
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
            if self._ticks % int(REFRESH_SEC * 1000 / ANIM_MS) == 0:
                if self._skip:
                    self._skip -= 1
                else:
                    self.refresh()
            if self._ticks % 2 == 0:
                self._update_click_through()
            if self._ticks % 10 == 0:
                self._check_fullscreen()
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
            return f"갱신 {self.last_ok.strftime('%H:%M')}{ct}", INK_SOFT, False
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
        key = self._base_key_now()
        if key != self._base_key:
            self._base = self._render_base()
            self._base_key = key
        # 고양이 프레임/z 위치가 안 바뀌었으면 화면 갱신 생략 (CPU 절약)
        cat_key = tuple((k, self._anim[k]["frame"], (self._ticks // 6) % 3) for k, *_ in PROVIDERS)
        frame_key = (key, cat_key)
        if frame_key == self._last_frame_key:
            return
        self._last_frame_key = frame_key

        out = self._base.copy()
        d = ImageDraw.Draw(out)
        half = W // 2
        for i, (pkey, name, accent, body, mark) in enumerate(PROVIDERS):
            ox = 12 + i * (half - 2)
            pct5 = ((self.usage.get(pkey) or {}).get("primary") or {}).get("used_percent")
            sleeping = pct5 is None or pct5 >= 100
            self._cat(d, ox - 2, 6, self._anim[pkey]["frame"], body, mark, sleeping)
        if os.environ.get("WIDGET_SNAP"):
            out.save(os.environ["WIDGET_SNAP"])
        self._photo = ImageTk.PhotoImage(out)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")

    def _render_base(self):
        S = SS
        img = Image.new("RGB", (W * S, H * S), CARD)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, W * S - 1, H * S - 1), radius=RADIUS * S, outline=CARD_EDGE, width=2 * S)

        self._buttons = {}
        half = W // 2
        for i, (key, name, accent, body, mark) in enumerate(PROVIDERS):
            ox = 12 + i * (half - 2)
            u = self.usage.get(key) or {}
            stale = self._is_stale(key)

            d.text(((ox + 58) * S, 8 * S), name, font=self.f_title, fill=accent)
            sub = "오래된 값 (1시간 이상 조회 실패)" if stale and u else (u.get("login_method") or "")
            d.text(((ox + 58) * S, 26 * S), sub, font=self.f_tiny, fill=C_WARN if stale and u else INK_SOFT)

            # 추가 창 (Claude: Fable 전용 주간) - 작은 막대
            fb = extra_window(u, "fable")
            if fb.get("used_percent") is not None:
                fp = fb["used_percent"]
                bx0, bx1, by = ox + 122, ox + half - 26, 39
                d.text(((ox + 58) * S, (by - 3) * S), f"Fable 주간 {int(fp)}%", font=self.f_tiny, fill=INK_SOFT)
                d.rounded_rectangle((bx0 * S, by * S, bx1 * S, (by + 4) * S), radius=2 * S, fill=TRACK)
                fx = bx0 + (bx1 - bx0) * min(fp, 100) / 100
                if fx > bx0 + 2:
                    d.rounded_rectangle((bx0 * S, by * S, fx * S, (by + 4) * S), radius=2 * S,
                                        fill=C_STALE if stale else pct_color(fp))

            for j, (wkey, wname) in enumerate(WINDOWS):
                win = u.get(wkey) or {}
                gx, gy = ox + j * 104, 52
                self._gauge(d, gx, gy, win.get("used_percent"), stale)
                d.text(((gx + GAUGE + 5) * S, (gy + 12) * S), wname, font=self.f_small, fill=INK)
                d.text(((gx + GAUGE + 5) * S, (gy + 27) * S), fmt_remaining(win.get("resets_at")),
                       font=self.f_tiny, fill=INK_SOFT)
                if self.state.get("pace", False) and not stale:
                    hint = pace_hint(u, wkey)
                    if hint:
                        d.ellipse(((gx + GAUGE + 6) * S, (gy + 42) * S, (gx + GAUGE + 10) * S, (gy + 46) * S), fill=hint[1])
                        d.text(((gx + GAUGE + 13) * S, (gy + 39) * S), hint[0], font=self.f_tiny, fill=hint[1])

            if i == 0:
                lx = (half + 2) * S
                d.line((lx, 14 * S, lx, (H - 14) * S), fill=TRACK, width=2 * S)

        # 상태 / 알림 배너 (우하단)
        msg, col, is_banner = self._status()
        if is_banner:
            tw = d.textlength(msg, font=self.f_tiny)
            d.rounded_rectangle((10 * S, (H - 19) * S, 20 * S + tw + 10 * S, (H - 4) * S),
                                radius=6 * S, fill=col)
            d.text((15 * S, (H - 11.5) * S), msg, font=self.f_tiny, fill="#ffffff", anchor="lm")
        else:
            d.text((14 * S, (H - 6) * S), msg, font=self.f_tiny, fill=col, anchor="ld")

        # 버튼 (↻, ✕)
        for label, bx in (("refresh", W - 40), ("close", W - 20)):
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

    def _cat(self, d, x, y, fi, body, mark, sleeping):
        px = CAT_PX
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
            d.text((x + 50, y - 2 + phase * 2), "z", font=self.f_z, fill=INK_SOFT)


if __name__ == "__main__":
    if not acquire_single_instance():
        sys.exit(0)  # 이미 실행 중
    if not CODEXBAR_CLI.exists():
        import tkinter.messagebox as mb
        root = tk.Tk(); root.withdraw()
        mb.showerror("AI Usage Widget", f"codexbar-cli.exe를 찾을 수 없습니다:\n{CODEXBAR_CLI}\n\nWin-CodexBar를 먼저 설치하세요.")
        sys.exit(1)
    log.info("start")
    Widget().mainloop()
    log.info("exit")

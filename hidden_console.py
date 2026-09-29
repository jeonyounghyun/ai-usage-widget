"""보이지 않는 콘솔에서 대화형 도구(로그인 도구)를 실행하고, 그 화면 글자를 읽거나 키 입력을 대신 넣는다.

로그인 도구(claude auth login, codex login)는 '사람이 보는 콘솔'이 있어야 동작한다. CREATE_NO_WINDOW로 띄우면
콘솔은 있지만 창은 없다(Windows Terminal로 넘어가지도 않음). 설치 창은 그 콘솔에 잠깐 붙어(AttachConsole)
화면 버퍼를 읽고(ReadConsoleOutputCharacterW) 입력을 넣는다(WriteConsoleInputW).
"""
import ctypes
import os
import subprocess
import threading
from ctypes import wintypes

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.AttachConsole.argtypes = [wintypes.DWORD]
k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
k32.CreateFileW.restype = wintypes.HANDLE
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.GetConsoleScreenBufferInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
k32.ReadConsoleOutputCharacterW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes._COORD, ctypes.POINTER(wintypes.DWORD)]
k32.GetStdHandle.argtypes = [wintypes.DWORD]
k32.GetStdHandle.restype = wintypes.HANDLE
k32.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
STD_HANDLES = (0xFFFFFFF6, 0xFFFFFFF5, 0xFFFFFFF4)   # 입력, 출력, 오류
k32.WriteConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]

GENERIC_RW = 0x80000000 | 0x40000000
SHARE_RW = 0x1 | 0x2
OPEN_EXISTING = 3
INVALID = wintypes.HANDLE(-1).value
NO_WINDOW = 0x08000000
_lock = threading.Lock()          # 한 프로세스는 한 번에 한 콘솔에만 붙을 수 있다


class _CSBI(ctypes.Structure):
    _fields_ = [("dwSize", wintypes._COORD), ("dwCursorPosition", wintypes._COORD), ("wAttributes", wintypes.WORD),
                ("srWindow", wintypes.SMALL_RECT), ("dwMaximumWindowSize", wintypes._COORD)]


class _KEY(ctypes.Structure):
    _fields_ = [("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD), ("wVirtualKeyCode", wintypes.WORD),
                ("wVirtualScanCode", wintypes.WORD), ("UnicodeChar", wintypes.WCHAR), ("dwControlKeyState", wintypes.DWORD)]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("KeyEvent", _KEY), ("_pad", ctypes.c_byte * 16)]
    _fields_ = [("EventType", wintypes.WORD), ("Event", _U)]


class HiddenConsole:
    def __init__(self, cmdline, env=None):
        clean = {k: v for k, v in (env or os.environ).items() if not k.startswith(("_PYI", "_MEI", "TCL_", "TK_"))}
        self.proc = subprocess.Popen(cmdline, creationflags=NO_WINDOW, env=clean,
                                     stdin=None, stdout=None, stderr=None)

    def alive(self):
        return self.proc.poll() is None

    def _attached(self, fn):
        """이 프로세스의 콘솔에 잠깐 붙어서 fn(conout, conin)을 실행."""
        with _lock:
            # AttachConsole은 이 프로세스의 표준 입출력을 그 콘솔로 바꾸고, FreeConsole 뒤엔 그 핸들이 무효가 된다.
            # (창 프로그램 exe에서 이후 subprocess가 '핸들이 잘못되었습니다'로 실패) → 전후로 저장·복원
            saved = [k32.GetStdHandle(n) for n in STD_HANDLES]
            k32.FreeConsole()
            if not k32.AttachConsole(self.proc.pid):
                for n, hnd in zip(STD_HANDLES, saved):
                    k32.SetStdHandle(n, hnd)
                return None
            try:
                out = k32.CreateFileW("CONOUT$", GENERIC_RW, SHARE_RW, None, OPEN_EXISTING, 0, None)
                inp = k32.CreateFileW("CONIN$", GENERIC_RW, SHARE_RW, None, OPEN_EXISTING, 0, None)
                try:
                    return fn(out, inp)
                finally:
                    for h in (out, inp):
                        if h and h != INVALID:
                            k32.CloseHandle(h)
            finally:
                k32.FreeConsole()
                for n, hnd in zip(STD_HANDLES, saved):
                    k32.SetStdHandle(n, hnd)

    def screen(self):
        """콘솔 화면 버퍼 전체를 글자로 (줄 끝 공백 제거)."""
        def read(out, _inp):
            info = _CSBI()
            if not k32.GetConsoleScreenBufferInfo(out, ctypes.byref(info)):
                return ""
            w, h = info.dwSize.X, min(info.dwSize.Y, info.dwCursorPosition.Y + 2)
            buf = ctypes.create_unicode_buffer(w * h)
            n = wintypes.DWORD()
            k32.ReadConsoleOutputCharacterW(out, buf, w * h, wintypes._COORD(0, 0), ctypes.byref(n))
            text = buf.value[:n.value]
            rows = [text[i:i + w] for i in range(0, len(text), w)]
            # 폭을 꽉 채운 줄은 다음 줄로 이어지는 것(긴 로그인 주소) → 줄바꿈 없이 붙인다
            return "".join(r if len(r) == w and not r.endswith(" ") else r.rstrip() + "\n" for r in rows)
        return self._attached(read) or ""

    def type(self, text, enter=True):
        """키 입력을 콘솔에 넣는다 (붙여넣기 코드 + Enter)."""
        def write(_out, inp):
            recs = []
            for ch in text + ("\r" if enter else ""):
                vk = 0x0D if ch == "\r" else 0
                for down in (True, False):
                    r = _INPUT()
                    r.EventType = 1  # KEY_EVENT
                    r.Event.KeyEvent = _KEY(down, 1, vk, 0, ch, 0)
                    recs.append(r)
            arr = (_INPUT * len(recs))(*recs)
            n = wintypes.DWORD()
            return bool(k32.WriteConsoleInputW(inp, arr, len(recs), ctypes.byref(n)))
        return bool(self._attached(write))

    def kill(self):
        if self.alive():
            subprocess.run(["taskkill", "/f", "/t", "/pid", str(self.proc.pid)], capture_output=True,
                           stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)

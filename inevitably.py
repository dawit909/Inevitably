import asyncio
import ctypes
import io
import json
import math
import os
import queue
import re
import ssl
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageGrab, ImageStat, ImageTk

if not getattr(sys, "frozen", False):
    _script_dir = str(Path(__file__).resolve().parent)
    if _script_dir not in sys.path:
        sys.path.insert(0, _script_dir)

from langs import detect_language, get_parser

if sys.platform == "win32":
    from ctypes import wintypes

    # Keep Tkinter, ImageGrab, and WH_MOUSE_LL screen coordinates 1:1 on scaled displays
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# Optional native Windows OCR imports
WINRT_OCR_AVAILABLE = False
if sys.platform == "win32":
    try:
        from winrt.windows.globalization import Language as WinRTLanguage
        from winrt.windows.graphics.imaging import (
            BitmapAlphaMode,
            BitmapPixelFormat,
            SoftwareBitmap,
        )
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter

        WINRT_OCR_AVAILABLE = True
    except ImportError:
        WINRT_OCR_AVAILABLE = False

# --- Config ---
APP_NAME = "Inevitably"
LIVE_API_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
DDRAGON_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DDRAGON_CDN = "https://ddragon.leagueoflegends.com/cdn"

# Store config and icon cache next to the .exe when packaged with PyInstaller
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

CONFIG_PATH = BASE_DIR / "inevitably_config.json"
CACHE_DIR = BASE_DIR / "inevitably_cache"

DEFAULT_TILE_SIZE = 38
MIN_TILE_SIZE = 24
MAX_TILE_SIZE = 72
TILE_GAP = 2
GRID_PAD = 3
TOP_BAR_H = 22
DOT_RADIUS = 6.75
REACTION_OFFSET_SEC = 2  # Subtracts N seconds on manual start for click delay

# Default League chat box region as normalized screen fractions [left, top, right, bottom]
DEFAULT_CHAT_BOX = [0.005, 0.58, 0.34, 0.84]
OCR_POLL_INTERVAL_SEC = 0.45
OCR_NO_TS_LOCKOUT_SEC = 30.0
OCR_MAX_STALE_TS_SEC = 25.0

ROLE_ORDER = {"TOP": 0, "JUNGLE": 1, "MIDDLE": 2, "BOTTOM": 3, "UTILITY": 4}
ROLE_SHORT = {"TOP": "TOP", "JUNGLE": "JGL", "MIDDLE": "MID", "BOTTOM": "BOT", "UTILITY": "SUP"}

# Item IDs granting Summoner Spell Haste
SPELL_HASTE_ITEMS = {
    3158: 10,  # Ionian Boots of Lucidity
    3171: 20,  # Crimson Lucidity
}

# Inspiration tree & rune/item IDs for automatic Cosmic Insight detection
INSPIRATION_TREE_ID = 8300
COSMIC_INSIGHT_RUNE_ID = 8347
COSMIC_INSIGHT_HASTE = 18
ARAM_SPELL_HASTE = 70

INSPIRATION_ITEM_RUNES = {
    2422: "footwear",  # Slightly Magical Footwear
    2010: "biscuit",   # Total Biscuit of Everlasting Will
    2150: "tonic",     # Elixir of Skill (Triple Tonic)
    2151: "tonic",     # Elixir of Avarice (Triple Tonic)
    2152: "tonic",     # Elixir of Force (Triple Tonic)
}

PLATFORM_ROUTING = {
    "na1": "americas", "br1": "americas", "la1": "americas", "la2": "americas",
    "kr": "asia", "jp1": "asia",
    "euw1": "europe", "eun1": "europe", "tr1": "europe", "ru": "europe", "me1": "europe",
    "oc1": "sea", "ph2": "sea", "sg2": "sea", "th2": "sea", "tw2": "sea", "vn2": "sea",
}

# Colors
BG_FRAME = "#12151A"
BG_TILE = "#1C2128"
BORDER_TILE = "#2D333B"
BORDER_HOVER = "#6E7681"
TRACK_COLOR = "#4A5260"
KNOB_GREEN = "#4ADE80"
DOT_RESIZE = "#FEBC2E"
DOT_RESIZE_HOVER = "#FDE047"
DOT_MOVE = "#38BDF8"
DOT_MOVE_HOVER = "#7DD3FC"
CI_PIP_COLOR = "#38BDF8"
FG_WHITE = "#FFFFFF"
FG_WARN = "#FF3B30"

# Win32 constants
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020

WH_MOUSE_LL = 14
WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUIT = 0x0012
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_TRAY_UPDATE = WM_USER + 21

VK_SHIFT = 0x10
VK_CONTROL = 0x11

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

MF_STRING = 0x00000000
MF_GRAYED = 0x00000001
MF_SEPARATOR = 0x00000800
TPM_LEFTALIGN = 0x0000
TPM_RIGHTBUTTON = 0x0002
TPM_BOTTOMALIGN = 0x0020
TPM_NONOTIFY = 0x0080
TPM_RETURNCMD = 0x0100

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
IDI_APPLICATION = 32512

TRAY_ID_STATUS = 1000
TRAY_ID_RESET = 1001
TRAY_ID_FOLDER = 1002
TRAY_ID_EXIT = 1003

RESAMPLING = getattr(Image, "Resampling", Image)
LANCZOS = RESAMPLING.LANCZOS
BILINEAR = RESAMPLING.BILINEAR
BICUBIC = RESAMPLING.BICUBIC


if sys.platform == "win32":
    LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("pt", wintypes.POINT),
            ("mouseData", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HCURSOR),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
            ("hIconSm", wintypes.HICON),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", ctypes.c_wchar * 64),
        ]


def _find_local_icon() -> Path | None:
    for name in ("inevitably.ico", "app.ico"):
        p = BASE_DIR / name
        if p.exists():
            return p
    return None


def is_league_foreground() -> bool:
    """Return True if League of Legends game client is the active foreground window."""
    if sys.platform != "win32":
        return True
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        cls_buf = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, cls_buf, 128)
        if cls_buf.value == "RiotWindowClass":
            return True
        title_buf = ctypes.create_unicode_buffer(128)
        user32.GetWindowTextW(hwnd, title_buf, 128)
        return "League of Legends (TM) Client" in title_buf.value
    except Exception:
        return True


class WindowsTrayIcon:
    """
    Zero-dependency Windows system tray icon using Shell_NotifyIconW.
    Reuses the embedded .exe icon automatically (or inevitably.ico / app.ico next to the script).
    """

    def __init__(self, event_queue: queue.Queue, ocr_label: str = ""):
        self._queue = event_queue
        self._ocr_label = ocr_label
        self._status_lock = threading.Lock()
        self._status_text = "Waiting for game"
        self._hwnd: int | None = None
        self._hicon: int | None = None
        self._owns_icon = False
        self._wnd_proc = None
        self._taskbar_created_msg = 0
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        if sys.platform == "win32":
            self._thread.start()

    def set_status(self, status_text: str) -> None:
        if sys.platform != "win32":
            return
        with self._status_lock:
            if status_text == self._status_text:
                return
            self._status_text = status_text
        hwnd = self._hwnd
        if hwnd:
            ctypes.windll.user32.PostMessageW(hwnd, WM_TRAY_UPDATE, 0, 0)

    def stop(self) -> None:
        if sys.platform != "win32":
            return
        hwnd = self._hwnd
        if hwnd:
            ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=1.2)

    def _get_status(self) -> str:
        with self._status_lock:
            return self._status_text

    def _build_nid(self, hwnd: int, flags: int) -> "NOTIFYICONDATAW":
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = flags
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._hicon or 0
        tip = f"{APP_NAME} - {self._get_status()}"
        nid.szTip = tip[:63]
        return nid

    def _load_icon(self) -> tuple[int, bool]:
        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32

        shell32.ExtractIconExW.argtypes = [
            wintypes.LPCWSTR, ctypes.c_int,
            ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON),
            wintypes.UINT,
        ]
        shell32.ExtractIconExW.restype = wintypes.UINT

        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.LoadImageW.restype = wintypes.HANDLE

        user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        user32.LoadIconW.restype = wintypes.HICON

        if getattr(sys, "frozen", False):
            small_icon = wintypes.HICON()
            large_icon = wintypes.HICON()
            count = shell32.ExtractIconExW(
                sys.executable, 0, ctypes.byref(large_icon), ctypes.byref(small_icon), 1,
            )
            if count > 0:
                if small_icon.value:
                    if large_icon.value:
                        user32.DestroyIcon(large_icon.value)
                    return int(small_icon.value), True
                if large_icon.value:
                    return int(large_icon.value), True

        ico_path = _find_local_icon()
        if ico_path:
            hicon = user32.LoadImageW(
                None, str(ico_path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE,
            )
            if hicon:
                return int(hicon), True

        fallback = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        return int(fallback or 0), False

    def _show_menu(self, hwnd: int) -> None:
        user32 = ctypes.windll.user32
        hmenu = user32.CreatePopupMenu()
        if not hmenu:
            return
        try:
            status_line = f"{APP_NAME}: {self._get_status()}"
            if self._ocr_label:
                status_line = f"{status_line} ({self._ocr_label})"
            user32.AppendMenuW(hmenu, MF_STRING | MF_GRAYED, TRAY_ID_STATUS, status_line)
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(hmenu, MF_STRING, TRAY_ID_RESET, "Reset Position && Size")
            user32.AppendMenuW(hmenu, MF_STRING, TRAY_ID_FOLDER, "Open App Folder")
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(hmenu, MF_STRING, TRAY_ID_EXIT, "Exit")

            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(hwnd)
            cmd = user32.TrackPopupMenu(
                hmenu,
                TPM_LEFTALIGN | TPM_BOTTOMALIGN | TPM_RIGHTBUTTON | TPM_NONOTIFY | TPM_RETURNCMD,
                pt.x, pt.y, 0, hwnd, None,
            )
            user32.PostMessageW(hwnd, WM_NULL, 0, 0)

            if cmd == TRAY_ID_RESET:
                self._queue.put(("tray_reset",))
            elif cmd == TRAY_ID_FOLDER:
                try:
                    os.startfile(str(BASE_DIR))
                except OSError:
                    pass
            elif cmd == TRAY_ID_EXIT:
                self._queue.put(("tray_quit",))
        finally:
            user32.DestroyMenu(hmenu)

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        shell32 = ctypes.windll.shell32

        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

        user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
        user32.RegisterClassExW.restype = wintypes.ATOM
        user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        user32.UnregisterClassW.restype = wintypes.BOOL
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        user32.PostQuitMessage.argtypes = [ctypes.c_int]
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = wintypes.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = LRESULT
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
        user32.AppendMenuW.restype = wintypes.BOOL
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        user32.DestroyMenu.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, wintypes.HWND, ctypes.c_void_p,
        ]
        user32.TrackPopupMenu.restype = ctypes.c_int
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        user32.DestroyIcon.restype = wintypes.BOOL
        user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
        user32.RegisterWindowMessageW.restype = wintypes.UINT

        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL

        self._hicon, self._owns_icon = self._load_icon()
        self._taskbar_created_msg = user32.RegisterWindowMessageW("TaskbarCreated")
        hinstance = kernel32.GetModuleHandleW(None)
        class_name = f"{APP_NAME}Tray_{os.getpid()}"

        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_TRAYICON:
                ev = lparam & 0xFFFF
                if ev in (WM_RBUTTONUP, WM_LBUTTONUP):
                    self._show_menu(hwnd)
                    return 0
            elif msg == WM_TRAY_UPDATE:
                nid = self._build_nid(hwnd, NIF_TIP)
                shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
                return 0
            elif self._taskbar_created_msg and msg == self._taskbar_created_msg:
                nid = self._build_nid(hwnd, NIF_MESSAGE | NIF_ICON | NIF_TIP)
                shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
                return 0
            elif msg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            elif msg == WM_DESTROY:
                nid = self._build_nid(hwnd, 0)
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wnd_proc = WNDPROC(wnd_proc)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wnd_proc
        wc.hInstance = hinstance
        wc.lpszClassName = class_name

        if not user32.RegisterClassExW(ctypes.byref(wc)):
            return

        hwnd = user32.CreateWindowExW(
            0, class_name, f"{APP_NAME}Tray", 0,
            0, 0, 0, 0, None, None, hinstance, None,
        )
        if not hwnd:
            user32.UnregisterClassW(class_name, hinstance)
            return

        self._hwnd = int(hwnd)
        nid = self._build_nid(hwnd, NIF_MESSAGE | NIF_ICON | NIF_TIP)
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            self._hwnd = None
            if self._owns_icon and self._hicon:
                user32.DestroyIcon(self._hicon)
                self._hicon = None
            user32.UnregisterClassW(class_name, hinstance)


class LeftClickInterceptor:
    """
    Intercepts ONLY left-clicks inside the overlay bounds while the window stays
    WS_EX_TRANSPARENT so all right-clicks, middle-clicks, and scrolls pass straight to League.
    """

    def __init__(self, get_rect_fn, event_queue: queue.Queue):
        self._get_rect = get_rect_fn
        self._queue = event_queue
        self._thread_id: int | None = None
        self._hook_handle = None
        self._hook_proc = None
        self._dragging = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        if sys.platform == "win32":
            self._thread.start()

    def stop(self) -> None:
        if sys.platform == "win32" and self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = LRESULT
        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = wintypes.BOOL
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

        self._thread_id = kernel32.GetCurrentThreadId()

        def proc(nCode, wParam, lParam):
            if nCode >= 0:
                if wParam == WM_LBUTTONDOWN:
                    rect = self._get_rect()
                    if rect is not None:
                        ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                        x, y = ms.pt.x, ms.pt.y
                        x0, y0, x1, y1 = rect
                        if x0 <= x < x1 and y0 <= y < y1:
                            shift = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
                            ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                            self._dragging = True
                            self._queue.put(("ldown", x, y, shift, ctrl))
                            return 1

                elif wParam == WM_MOUSEMOVE:
                    if self._dragging:
                        ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                        self._queue.put(("lmove", ms.pt.x, ms.pt.y))

                elif wParam == WM_LBUTTONUP:
                    if self._dragging:
                        self._dragging = False
                        ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                        self._queue.put(("lup", ms.pt.x, ms.pt.y))
                        return 1

            return user32.CallNextHookEx(self._hook_handle, nCode, wParam, lParam)

        self._hook_proc = HOOKPROC(proc)
        self._hook_handle = user32.SetWindowsHookExW(WH_MOUSE_LL, self._hook_proc, None, 0)
        if not self._hook_handle:
            hmod = kernel32.GetModuleHandleW(None)
            self._hook_handle = user32.SetWindowsHookExW(WH_MOUSE_LL, self._hook_proc, hmod, 0)
        if not self._hook_handle:
            return

        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
        finally:
            if self._hook_handle:
                user32.UnhookWindowsHookEx(self._hook_handle)
                self._hook_handle = None


def resolve_spell(spell_obj: dict, game_time: float, level: int, is_top: bool) -> dict:
    raw = (spell_obj.get("rawDisplayName") or spell_obj.get("displayName") or "").lower()
    disp = (spell_obj.get("displayName") or "").strip()

    if "summonerflash" in raw and "hextech" not in raw:
        return {"key": "SummonerFlash", "en_name": "Flash", "display_name": disp or "Flash", "short": "F", "cd": 300, "color": "#CA8A04", "is_hexflash": False}
    if "hextech" in raw and "flash" in raw:
        return {"key": "SummonerFlash", "en_name": "Flash", "display_name": disp or "Flash", "short": "F", "cd": 300, "color": "#CA8A04", "is_hexflash": True}
    if "teleport" in raw:
        if game_time >= 600:
            steps = max(0, min(9, level - 9))
            base = (300 if is_top else 330) - steps * 10
            return {"key": "SummonerTeleport", "en_name": "Teleport", "display_name": disp or "Teleport", "short": "TP", "cd": base, "color": "#7E22CE", "is_hexflash": False}
        return {"key": "SummonerTeleport", "en_name": "Teleport", "display_name": disp or "Teleport", "short": "TP", "cd": 300, "color": "#7E22CE", "is_hexflash": False}
    if "summonerdot" in raw or "ignite" in raw:
        return {"key": "SummonerDot", "en_name": "Ignite", "display_name": disp or "Ignite", "short": "IG", "cd": 180, "color": "#DC2626", "is_hexflash": False}
    if "summonerbarrier" in raw or "barrier" in raw:
        return {"key": "SummonerBarrier", "en_name": "Barrier", "display_name": disp or "Barrier", "short": "BR", "cd": 180, "color": "#D97706", "is_hexflash": False}
    if "summonerheal" in raw or "heal" in raw:
        return {"key": "SummonerHeal", "en_name": "Heal", "display_name": disp or "Heal", "short": "HL", "cd": 240, "color": "#16A34A", "is_hexflash": False}
    if "summonerexhaust" in raw or "exhaust" in raw:
        return {"key": "SummonerExhaust", "en_name": "Exhaust", "display_name": disp or "Exhaust", "short": "EX", "cd": 240, "color": "#EA580C", "is_hexflash": False}
    if "summonerboost" in raw or "cleanse" in raw:
        return {"key": "SummonerBoost", "en_name": "Cleanse", "display_name": disp or "Cleanse", "short": "CL", "cd": 240, "color": "#0284C7", "is_hexflash": False}
    if "summonerhaste" in raw or "ghost" in raw:
        return {"key": "SummonerHaste", "en_name": "Ghost", "display_name": disp or "Ghost", "short": "GH", "cd": 240, "color": "#2563EB", "is_hexflash": False}
    if "summonersmite" in raw or "smite" in raw:
        return {"key": "SummonerSmite", "en_name": "Smite", "display_name": disp or "Smite", "short": "SM", "cd": 90, "color": "#B45309", "is_hexflash": False}
    if "summonersnowball" in raw or "mark" in raw:
        return {"key": "SummonerSnowball", "en_name": "Mark", "display_name": disp or "Mark", "short": "MK", "cd": 80, "color": "#3B82F6", "is_hexflash": False}
    if "summonermana" in raw or "clarity" in raw:
        return {"key": "SummonerMana", "en_name": "Clarity", "display_name": disp or "Clarity", "short": "MN", "cd": 240, "color": "#1D4ED8", "is_hexflash": False}

    short = (disp or "??")[:2].upper()
    return {"key": "", "en_name": disp, "display_name": disp, "short": short, "cd": 240, "color": "#4B5563", "is_hexflash": False}


def effective_cooldown(base_cd: float, haste: int) -> int:
    return max(1, round(base_cd * 100.0 / (100.0 + max(0, haste))))


def format_timer(seconds: float) -> str:
    s = max(1, math.ceil(seconds))
    if s < 60:
        return str(s)
    return f"{s // 60}:{s % 60:02d}"


class ChatOcrWatcher:
    """
    Lightweight background watcher that captures only the chat-box region while League is
    in the foreground, gates OCR behind a fast thumbnail pixel-diff check, runs Windows OCR,
    and delegates parsing to the active language module in `langs/`.
    """

    def __init__(
        self,
        get_state_fn,
        get_ult_names_fn,
        trigger_queue: queue.Queue,
        chat_box_cfg: list[float] | None = None,
        ocr_lang: str = "",
        demo: bool = False,
        debug: bool = False,
    ):
        self._get_state = get_state_fn
        self._get_ult_names = get_ult_names_fn
        self._trigger_queue = trigger_queue
        self._chat_box_cfg = chat_box_cfg or list(DEFAULT_CHAT_BOX)
        self._ocr_lang = (ocr_lang or "").strip()
        self._demo = demo
        self._debug = debug

        self._running = False
        self._thread: threading.Thread | None = None
        self._prev_thumb: Image.Image | None = None
        self._engine = None
        self._engine_lang = ""

    @property
    def available(self) -> bool:
        return WINRT_OCR_AVAILABLE and sys.platform == "win32"

    def start(self) -> None:
        if not self.available:
            if self._debug:
                print("[OCR] WinRT OCR packages not installed; chat detection disabled.")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def reset(self) -> None:
        self._prev_thumb = None

    def _resolve_bbox(self) -> tuple[int, int, int, int]:
        user32 = ctypes.windll.user32
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        x0, y0, x1, y1 = self._chat_box_cfg
        if max(x0, y0, x1, y1) <= 1.0:
            return int(sw * x0), int(sh * y0), int(sw * x1), int(sh * y1)
        return int(x0), int(y0), int(x1), int(y1)

    def _ensure_engine(self, lang_code: str, preferred_tags: tuple[str, ...]):
        if self._engine is not None and (self._ocr_lang or lang_code == self._engine_lang):
            return self._engine

        avail_tags: list[str] = []
        avail_langs = []
        try:
            avail_langs = list(OcrEngine.available_recognizer_languages)
            avail_tags = [lang.language_tag for lang in avail_langs]
        except Exception as exc:
            if self._debug:
                print(f"[OCR] Could not enumerate OCR languages: {exc}")

        engine = None
        tags_to_try: list[str] = [self._ocr_lang] if self._ocr_lang else list(preferred_tags)

        for tag in tags_to_try:
            try:
                lang = WinRTLanguage(tag)
                if OcrEngine.is_language_supported(lang):
                    engine = OcrEngine.try_create_from_language(lang)
                    if engine is not None:
                        break
            except Exception:
                continue

        if engine is None:
            for avail in avail_langs:
                tag = (avail.language_tag or "").lower()
                if tag == lang_code or tag.startswith(f"{lang_code}-"):
                    try:
                        engine = OcrEngine.try_create_from_language(avail)
                        if engine is not None:
                            break
                    except Exception:
                        continue

        if engine is None:
            try:
                engine = OcrEngine.try_create_from_user_profile_languages()
            except Exception:
                engine = None

        self._engine = engine
        self._engine_lang = lang_code
        if self._debug:
            chosen = engine.recognizer_language.language_tag if engine else "None"
            print(f"[OCR] Installed languages: {avail_tags} | Parser: {lang_code} | Using: {chosen}")
            if chosen and not chosen.lower().startswith(lang_code):
                print(f"[OCR] TIP: Install Windows '{lang_code}' OCR language pack for higher accuracy.")
        return engine

    @staticmethod
    def _pil_to_software_bitmap(img: Image.Image):
        rgba = img.convert("RGBA")
        writer = DataWriter()
        writer.write_bytes(rgba.tobytes())
        buf = writer.detach_buffer()
        return SoftwareBitmap.create_copy_from_buffer(
            buf,
            BitmapPixelFormat.RGBA8,
            rgba.width,
            rgba.height,
            BitmapAlphaMode.STRAIGHT,
        )

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while self._running:
                state = self._get_state()
                if not state or not state.get("enemies"):
                    self._prev_thumb = None
                    time.sleep(1.0)
                    continue

                if not self._demo and not is_league_foreground():
                    time.sleep(OCR_POLL_INTERVAL_SEC)
                    continue

                lang_code = detect_language(state["enemies"])
                parser = get_parser(lang_code)
                engine = self._ensure_engine(lang_code, parser.preferred_ocr_tags)
                if engine is None:
                    time.sleep(3.0)
                    continue

                bbox = self._resolve_bbox()
                try:
                    shot = ImageGrab.grab(bbox=bbox)
                except Exception:
                    time.sleep(OCR_POLL_INTERVAL_SEC)
                    continue

                thumb = shot.convert("L").resize((64, 32), BILINEAR)
                if self._prev_thumb is not None:
                    diff = ImageChops.difference(thumb, self._prev_thumb)
                    mean_diff = ImageStat.Stat(diff).mean[0]
                    if mean_diff < 1.0:
                        time.sleep(OCR_POLL_INTERVAL_SEC)
                        continue
                self._prev_thumb = thumb

                up = shot.resize((int(shot.width * 2.5), int(shot.height * 2.5)), BICUBIC)
                try:
                    swbmp = self._pil_to_software_bitmap(up)
                    result = loop.run_until_complete(engine.recognize_async(swbmp))
                    raw_lines = [ln.text for ln in result.lines]
                except Exception as exc:
                    if self._debug:
                        print(f"[OCR] Error: {exc}")
                    time.sleep(OCR_POLL_INTERVAL_SEC)
                    continue

                ult_names = self._get_ult_names()
                for ln in parser.preprocess_lines(raw_lines):
                    if self._debug:
                        print(f"[OCR line] {ln}")
                    hit = parser.parse_line(ln, state["enemies"], ult_names)
                    if hit is not None:
                        if self._debug:
                            print(f"[OCR MATCH] enemy={hit[0]} col={hit[1]} ts={hit[2]}")
                        self._trigger_queue.put(hit)

                time.sleep(OCR_POLL_INTERVAL_SEC)
        finally:
            loop.close()


class DataDragonCache:
    """Downloads and caches Riot Data Dragon icons, champion ult cooldowns/names, and item haste."""

    def __init__(self):
        self.icons_dir = CACHE_DIR / "icons"
        self.champs_dir = CACHE_DIR / "champs"
        self.icons_dir.mkdir(parents=True, exist_ok=True)
        self.champs_dir.mkdir(parents=True, exist_ok=True)

        self.version = self._load_version()
        self.champ_map: dict[str, str] = {}
        self.champ_key_to_id: dict[int, str] = {}
        self.item_haste_map: dict[int, int] = {}
        self.ult_cd_cache: dict[str, list[float]] = {}
        self.ult_name_cache: dict[str, str] = {}

        self._lock = threading.Lock()
        self._in_flight: set[str] = set()
        self.ready_queue: queue.Queue[tuple[str, Image.Image]] = queue.Queue()

        threading.Thread(target=self._bootstrap_metadata, daemon=True).start()

    def _http_get(self, url: str, timeout: float = 5.0) -> bytes | None:
        req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            return None

    def _load_version(self) -> str:
        ver_file = CACHE_DIR / "version.txt"
        raw = self._http_get(DDRAGON_VERSIONS_URL, timeout=3.0)
        if raw:
            try:
                ver = json.loads(raw.decode("utf-8"))[0]
                ver_file.write_text(ver, encoding="utf-8")
                return ver
            except (json.JSONDecodeError, IndexError, OSError):
                pass
        if ver_file.exists():
            return ver_file.read_text(encoding="utf-8").strip()
        return "16.1.1"

    def _bootstrap_metadata(self) -> None:
        champ_file = CACHE_DIR / f"champion_{self.version}.json"
        if not champ_file.exists():
            raw = self._http_get(f"{DDRAGON_CDN}/{self.version}/data/en_US/champion.json")
            if raw:
                champ_file.write_bytes(raw)
        if champ_file.exists():
            try:
                data = json.loads(champ_file.read_text(encoding="utf-8")).get("data", {})
                cmap = {}
                key_map = {}
                for cid, info in data.items():
                    cmap[cid.lower()] = cid
                    cmap[re.sub(r"[^a-z0-9]", "", cid.lower())] = cid
                    cname = info.get("name", "")
                    cmap[cname.lower()] = cid
                    cmap[re.sub(r"[^a-z0-9]", "", cname.lower())] = cid
                    if info.get("key"):
                        try:
                            key_map[int(info["key"])] = cid
                        except ValueError:
                            pass
                with self._lock:
                    self.champ_map = cmap
                    self.champ_key_to_id = key_map
            except (json.JSONDecodeError, OSError):
                pass

        item_file = CACHE_DIR / f"item_{self.version}.json"
        if not item_file.exists():
            raw = self._http_get(f"{DDRAGON_CDN}/{self.version}/data/en_US/item.json")
            if raw:
                item_file.write_bytes(raw)
        if item_file.exists():
            try:
                data = json.loads(item_file.read_text(encoding="utf-8")).get("data", {})
                hmap = {}
                pattern = re.compile(r"<attention>(\d+)</attention>\s*Ability Haste", re.IGNORECASE)
                for iid_str, info in data.items():
                    m = pattern.search(info.get("description") or "")
                    if m:
                        hmap[int(iid_str)] = int(m.group(1))
                with self._lock:
                    self.item_haste_map = hmap
            except (json.JSONDecodeError, OSError, ValueError):
                pass

    def resolve_champ_id(self, raw_name: str, display_name: str) -> str:
        candidates = []
        if raw_name:
            candidates.append(raw_name.split("_")[-1])
        if display_name:
            candidates.append(display_name)
        with self._lock:
            cmap = self.champ_map
        for cand in candidates:
            low = cand.lower()
            norm = re.sub(r"[^a-z0-9]", "", low)
            if low in cmap:
                return cmap[low]
            if norm in cmap:
                return cmap[norm]
        return re.sub(r"[^A-Za-z0-9]", "", candidates[0]) if candidates else "Unknown"

    def champ_id_from_key(self, numeric_key: int) -> str | None:
        with self._lock:
            return self.champ_key_to_id.get(numeric_key)

    def get_item_ability_haste(self, item_ids: list[int]) -> int:
        with self._lock:
            hmap = self.item_haste_map
        return sum(hmap.get(iid, 0) for iid in item_ids)

    def get_ult_base_cd(self, champ_id: str, level: int) -> float:
        with self._lock:
            cds = self.ult_cd_cache.get(champ_id)
        if not cds:
            return 100.0
        if len(cds) >= 3:
            idx = 0 if level < 11 else (1 if level < 16 else 2)
        else:
            idx = 0
        cd = float(cds[min(idx, len(cds) - 1)])
        return cd if cd > 0 else 60.0

    def get_ult_names_snapshot(self) -> dict[str, str]:
        with self._lock:
            return dict(self.ult_name_cache)

    def request_champ_ult(self, champ_id: str) -> None:
        if not champ_id or champ_id == "Unknown":
            return
        with self._lock:
            if champ_id in self.ult_cd_cache or f"ult:{champ_id}" in self._in_flight:
                return
            self._in_flight.add(f"ult:{champ_id}")
        threading.Thread(target=self._fetch_ult_worker, args=(champ_id,), daemon=True).start()

    def _fetch_ult_worker(self, champ_id: str) -> None:
        try:
            cfile = self.champs_dir / f"{self.version}_{champ_id}.json"
            if not cfile.exists():
                raw = self._http_get(f"{DDRAGON_CDN}/{self.version}/data/en_US/champion/{champ_id}.json")
                if raw:
                    cfile.write_bytes(raw)
            if cfile.exists():
                data = json.loads(cfile.read_text(encoding="utf-8")).get("data", {})
                cinfo = data.get(champ_id) or next(iter(data.values()), {})
                spells = cinfo.get("spells") or []
                if len(spells) >= 4:
                    cds = [float(x) for x in (spells[3].get("cooldown") or [100])]
                    uname = spells[3].get("name") or ""
                    with self._lock:
                        self.ult_cd_cache[champ_id] = cds
                        if uname:
                            self.ult_name_cache[champ_id] = uname
        except (json.JSONDecodeError, OSError, ValueError):
            pass
        finally:
            with self._lock:
                self._in_flight.discard(f"ult:{champ_id}")

    def request_icon(self, kind: str, key: str) -> None:
        if not key or key == "Unknown":
            return
        cache_key = f"{kind}:{key}"
        with self._lock:
            if cache_key in self._in_flight:
                return
            self._in_flight.add(cache_key)
        threading.Thread(target=self._fetch_icon_worker, args=(kind, key, cache_key), daemon=True).start()

    def _fetch_icon_worker(self, kind: str, key: str, cache_key: str) -> None:
        try:
            local_path = self.icons_dir / f"{kind}_{key}.png"
            if local_path.exists():
                raw = local_path.read_bytes()
            else:
                subdir = "champion" if kind == "champ" else "spell"
                url = f"{DDRAGON_CDN}/{self.version}/img/{subdir}/{key}.png"
                raw = self._http_get(url)
                if raw:
                    local_path.write_bytes(raw)
            if not raw:
                return

            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            w, h = img.size
            crop = int(min(w, h) * 0.06)
            if crop > 0:
                img = img.crop((crop, crop, w - crop, h - crop))
            self.ready_queue.put((cache_key, img))
        except Exception:
            pass
        finally:
            with self._lock:
                self._in_flight.discard(cache_key)


class SpectatorRuneResolver:
    """
    Optional exact Cosmic Insight (perk ID 8347) lookup via Riot's Spectator-v5 API.
    Requires `riot_api_key` and `platform` (e.g. 'kr', 'na1', 'euw1') in config or env vars.
    """

    def __init__(self, dd: DataDragonCache, api_key: str, platform: str):
        self.dd = dd
        self.api_key = (api_key or "").strip()
        self.platform = (platform or "").strip().lower()
        self.routing = PLATFORM_ROUTING.get(self.platform, "")

        self._lock = threading.Lock()
        self._puuid_cache: dict[str, str] = {}
        self._by_riot_id: dict[str, bool] = {}
        self._by_team_champ: dict[tuple[str, str], bool] = {}
        self._in_flight = False
        self._done = False
        self._attempts = 0
        self._next_try_at = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.platform and self.routing)

    def reset(self) -> None:
        with self._lock:
            self._by_riot_id.clear()
            self._by_team_champ.clear()
            self._done = False
            self._attempts = 0
            self._next_try_at = 0.0

    def trigger(self, active_riot_id: str) -> None:
        if not self.enabled or not active_riot_id or "#" not in active_riot_id:
            return
        now = time.monotonic()
        with self._lock:
            if self._done or self._in_flight or self._attempts >= 2 or now < self._next_try_at:
                return
            self._in_flight = True
            self._attempts += 1
        threading.Thread(target=self._worker, args=(active_riot_id,), daemon=True).start()

    def lookup(self, enemy: dict) -> bool | None:
        with self._lock:
            rid = (enemy.get("riot_id") or "").lower()
            if rid and rid in self._by_riot_id:
                return self._by_riot_id[rid]
            key = (enemy.get("team") or "", enemy.get("champ_id") or "")
            if key in self._by_team_champ:
                return self._by_team_champ[key]
        return None

    def _riot_get(self, url: str) -> dict | None:
        req = urllib.request.Request(
            url,
            headers={"X-Riot-Token": self.api_key, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None

    def _worker(self, active_riot_id: str) -> None:
        success = False
        try:
            puuid = self._puuid_cache.get(active_riot_id)
            if not puuid:
                game_name, tag_line = active_riot_id.split("#", 1)
                gn = urllib.parse.quote(game_name, safe="")
                tl = urllib.parse.quote(tag_line, safe="")
                acct = self._riot_get(
                    f"https://{self.routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{gn}/{tl}"
                )
                if acct and acct.get("puuid"):
                    puuid = acct["puuid"]
                    self._puuid_cache[active_riot_id] = puuid
            if not puuid:
                return

            game = self._riot_get(
                f"https://{self.platform}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{puuid}"
            )
            if not game:
                return

            by_rid: dict[str, bool] = {}
            by_tc: dict[tuple[str, str], bool] = {}
            for p in game.get("participants") or []:
                perk_ids = (p.get("perks") or {}).get("perkIds") or []
                has_ci = COSMIC_INSIGHT_RUNE_ID in perk_ids
                team = "ORDER" if p.get("teamId") == 100 else "CHAOS"
                rid = (p.get("riotId") or "").lower()
                if rid:
                    by_rid[rid] = has_ci
                cid = self.dd.champ_id_from_key(int(p.get("championId") or 0))
                if cid:
                    by_tc[(team, cid)] = has_ci

            with self._lock:
                self._by_riot_id = by_rid
                self._by_team_champ = by_tc
                self._done = True
            success = True
        finally:
            with self._lock:
                self._in_flight = False
                if not success:
                    self._next_try_at = time.monotonic() + 10.0


def fetch_live_data(ssl_ctx: ssl.SSLContext, dd: DataDragonCache) -> dict | None:
    req = urllib.request.Request(LIVE_API_URL, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=1.5, context=ssl_ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    all_players = data.get("allPlayers") or []
    if not all_players:
        return None

    active = data.get("activePlayer") or {}
    active_riot_id = active.get("riotId") or ""
    if not active_riot_id and active.get("riotIdGameName") and active.get("riotIdTagLine"):
        active_riot_id = f"{active['riotIdGameName']}#{active['riotIdTagLine']}"

    active_ids = {active_riot_id, active.get("riotIdGameName"), active.get("summonerName")}
    active_ids.discard(None)
    active_ids.discard("")

    my_team = None
    for p in all_players:
        p_ids = {p.get("riotId"), p.get("riotIdGameName"), p.get("summonerName")}
        if active_ids & p_ids:
            my_team = p.get("team")
            if not active_riot_id and p.get("riotId"):
                active_riot_id = p["riotId"]
            break
        for aid in active_ids:
            base_aid = aid.split("#")[0]
            if any(pid and pid.split("#")[0] == base_aid for pid in p_ids):
                my_team = p.get("team")
                if not active_riot_id and p.get("riotId"):
                    active_riot_id = p["riotId"]
                break
        if my_team:
            break

    if not my_team:
        my_team = "ORDER"

    game_data = data.get("gameData") or {}
    game_time = float(game_data.get("gameTime") or 0.0)
    is_aram = game_data.get("gameMode") == "ARAM" or game_data.get("mapNumber") == 12

    enemies_raw = [p for p in all_players if p.get("team") != my_team]
    enemies_raw.sort(key=lambda p: ROLE_ORDER.get((p.get("position") or "").upper(), 99))

    enemies = []
    for idx, p in enumerate(enemies_raw):
        pos = (p.get("position") or "").upper()
        role_lbl = ROLE_SHORT.get(pos, f"P{idx + 1}")
        level = int(p.get("level") or 1)

        items = p.get("items") or []
        item_ids = [int(it["itemID"]) for it in items if "itemID" in it]
        spell_item_haste = max((SPELL_HASTE_ITEMS.get(iid, 0) for iid in item_ids), default=0)
        ability_haste = dd.get_item_ability_haste(item_ids)

        runes = p.get("runes") or {}
        pri_id = (runes.get("primaryRuneTree") or {}).get("id")
        sec_id = (runes.get("secondaryRuneTree") or {}).get("id")
        is_insp_primary = pri_id == INSPIRATION_TREE_ID
        is_insp_secondary = sec_id == INSPIRATION_TREE_ID

        explicit_ci: bool | None = None
        general_runes = runes.get("generalRunes")
        if isinstance(general_runes, list) and general_runes:
            explicit_ci = any(r.get("id") == COSMIC_INSIGHT_RUNE_ID for r in general_runes)

        spells_obj = p.get("summonerSpells") or {}
        s1 = resolve_spell(spells_obj.get("summonerSpellOne") or {}, game_time, level, pos == "TOP")
        s2 = resolve_spell(spells_obj.get("summonerSpellTwo") or {}, game_time, level, pos == "TOP")

        observed_non_ci = {INSPIRATION_ITEM_RUNES[iid] for iid in item_ids if iid in INSPIRATION_ITEM_RUNES}
        if s1["is_hexflash"] or s2["is_hexflash"]:
            observed_non_ci.add("hexflash")

        champ_display = p.get("championName") or f"Enemy{idx + 1}"
        champ_id = dd.resolve_champ_id(p.get("rawChampionName") or "", champ_display)
        riot_id = p.get("riotId") or ""
        pid = riot_id or p.get("summonerName") or f"{champ_id}_{idx}"

        enemies.append(
            {
                "id": pid,
                "riot_id": riot_id,
                "team": p.get("team") or "",
                "role": role_lbl,
                "champ_id": champ_id,
                "champ_display": champ_display,
                "champ_short": champ_id[:3].upper(),
                "level": level,
                "spell_item_haste": spell_item_haste,
                "ability_haste": ability_haste,
                "is_insp_primary": is_insp_primary,
                "is_insp_secondary": is_insp_secondary,
                "explicit_ci": explicit_ci,
                "observed_non_ci": observed_non_ci,
                "spells": [s1, s2],
            }
        )

    return {
        "gameTime": game_time,
        "isAram": is_aram,
        "activeRiotId": active_riot_id,
        "enemies": enemies,
    }


def build_demo_data() -> dict:
    return {
        "gameTime": 102.0,
        "isAram": False,
        "activeRiotId": "",
        "enemies": [
            {
                "id": "demo_0",
                "riot_id": "",
                "team": "CHAOS",
                "role": "TOP",
                "champ_id": "Malphite",
                "champ_display": "Malphite",
                "champ_short": "MAL",
                "level": 6,
                "spell_item_haste": 0,
                "ability_haste": 0,
                "is_insp_primary": False,
                "is_insp_secondary": False,
                "explicit_ci": False,
                "observed_non_ci": set(),
                "spells": [
                    {"key": "SummonerTeleport", "en_name": "Teleport", "display_name": "Teleport", "short": "TP", "cd": 300, "color": "#7E22CE", "is_hexflash": False},
                    {"key": "SummonerFlash", "en_name": "Flash", "display_name": "Flash", "short": "F", "cd": 300, "color": "#CA8A04", "is_hexflash": False},
                ],
            },
            {
                "id": "demo_1",
                "riot_id": "",
                "team": "CHAOS",
                "role": "JGL",
                "champ_id": "Vi",
                "champ_display": "Vi",
                "champ_short": "VI",
                "level": 6,
                "spell_item_haste": 10,
                "ability_haste": 10,
                "is_insp_primary": False,
                "is_insp_secondary": True,
                "explicit_ci": True,
                "observed_non_ci": set(),
                "spells": [
                    {"key": "SummonerSmite", "en_name": "Smite", "display_name": "Smite", "short": "SM", "cd": 90, "color": "#B45309", "is_hexflash": False},
                    {"key": "SummonerFlash", "en_name": "Flash", "display_name": "Flash", "short": "F", "cd": 300, "color": "#CA8A04", "is_hexflash": False},
                ],
            },
            {
                "id": "demo_2",
                "riot_id": "",
                "team": "CHAOS",
                "role": "MID",
                "champ_id": "Gragas",
                "champ_display": "Gragas",
                "champ_short": "GRA",
                "level": 6,
                "spell_item_haste": 0,
                "ability_haste": 15,
                "is_insp_primary": True,
                "is_insp_secondary": False,
                "explicit_ci": True,
                "observed_non_ci": set(),
                "spells": [
                    {"key": "SummonerDot", "en_name": "Ignite", "display_name": "Ignite", "short": "IG", "cd": 180, "color": "#DC2626", "is_hexflash": False},
                    {"key": "SummonerFlash", "en_name": "Flash", "display_name": "Flash", "short": "F", "cd": 300, "color": "#CA8A04", "is_hexflash": False},
                ],
            },
            {
                "id": "demo_3",
                "riot_id": "",
                "team": "CHAOS",
                "role": "BOT",
                "champ_id": "Ziggs",
                "champ_display": "Ziggs",
                "champ_short": "ZIG",
                "level": 6,
                "spell_item_haste": 0,
                "ability_haste": 0,
                "is_insp_primary": False,
                "is_insp_secondary": False,
                "explicit_ci": False,
                "observed_non_ci": set(),
                "spells": [
                    {"key": "SummonerTeleport", "en_name": "Teleport", "display_name": "Teleport", "short": "TP", "cd": 300, "color": "#7E22CE", "is_hexflash": False},
                    {"key": "SummonerFlash", "en_name": "Flash", "display_name": "Flash", "short": "F", "cd": 300, "color": "#CA8A04", "is_hexflash": False},
                ],
            },
            {
                "id": "demo_4",
                "riot_id": "",
                "team": "CHAOS",
                "role": "SUP",
                "champ_id": "Renata",
                "champ_display": "Renata Glasc",
                "champ_short": "REN",
                "level": 6,
                "spell_item_haste": 10,
                "ability_haste": 20,
                "is_insp_primary": False,
                "is_insp_secondary": True,
                "explicit_ci": True,
                "observed_non_ci": set(),
                "spells": [
                    {"key": "SummonerHeal", "en_name": "Heal", "display_name": "Heal", "short": "HL", "cd": 240, "color": "#16A34A", "is_hexflash": False},
                    {"key": "SummonerFlash", "en_name": "Flash", "display_name": "Flash", "short": "F", "cd": 300, "color": "#CA8A04", "is_hexflash": False},
                ],
            },
        ],
    }


class PortraitSpellOverlay:
    def __init__(self, demo: bool = False, ocr_debug: bool = False):
        self.demo = demo
        self.ocr_debug = ocr_debug
        self.dd = DataDragonCache()
        self.config = self._load_config()

        api_key = os.environ.get("RIOT_API_KEY") or self.config.get("riot_api_key", "")
        platform = os.environ.get("RIOT_PLATFORM") or self.config.get("platform", "")
        self.spectator = SpectatorRuneResolver(self.dd, api_key, platform)

        self.alpha = max(0.35, min(1.0, float(self.config.get("alpha", 0.92))))
        self.tile_size = max(
            MIN_TILE_SIZE,
            min(MAX_TILE_SIZE, int(self.config.get("tile_size", DEFAULT_TILE_SIZE))),
        )

        self.lock = threading.Lock()
        self.latest_state: dict | None = build_demo_data() if demo else None
        self.running = True

        # Timers keyed by (enemy_id, col_idx): col 0=spell1, col 1=spell2, col 2=ult
        self.timers: dict[tuple[str, int], float] = {}
        self.seen_non_ci_runes: dict[str, set[str]] = {}

        # OCR deduplication state
        self.ocr_queue: queue.Queue[tuple[str, int, int | None]] = queue.Queue()
        self.seen_ocr_ts: set[tuple[str, int, int]] = set()
        self.ocr_last_trigger: dict[tuple[str, int], float] = {}

        # Raw cropped PIL images + scaled Tkinter PhotoImage cache
        self.raw_icons: dict[str, Image.Image] = {}
        self.tk_icons: dict[str, tuple[ImageTk.PhotoImage, ImageTk.PhotoImage]] = {}
        self.requested_icons: set[str] = set()

        self._row_count = 5
        self.grid_w = self._calc_grid_w(self.tile_size)
        self.grid_h = self._calc_grid_h(self.tile_size, self._row_count)

        # Interaction state
        self._drag_mode: str | None = None
        self._drag_origin = (0, 0)
        self._resize_start_mouse = (0, 0)
        self._resize_start_tile = self.tile_size
        self._resize_anchor_br = (0, 0)

        self._hover_dot: str | None = None
        self._hover_cell: tuple[int, int] | None = None
        self._visible = False
        self._cell_items: list[list[dict]] = []

        self._win_rect: tuple[int, int, int, int] | None = None
        self.input_queue: queue.Queue = queue.Queue()

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        if sys.platform == "win32":
            try:
                if getattr(sys, "frozen", False):
                    self.root.iconbitmap(default=sys.executable)
                else:
                    local_ico = _find_local_icon()
                    if local_ico:
                        self.root.iconbitmap(default=str(local_ico))
            except Exception:
                pass
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.alpha)
        self.root.configure(bg=BG_FRAME)

        default_x, default_y = self._default_position()
        x = int(self.config.get("x", default_x))
        y = int(self.config.get("y", default_y))
        total_h = TOP_BAR_H + self.grid_h
        self.root.geometry(f"{self.grid_w}x{total_h}+{x}+{y}")

        self._build_ui()

        self.interceptor = LeftClickInterceptor(lambda: self._win_rect, self.input_queue)
        self.interceptor.start()

        ocr_enabled = bool(self.config.get("ocr_enabled", True))
        self.ocr_watcher = ChatOcrWatcher(
            get_state_fn=self._get_state_snapshot,
            get_ult_names_fn=self.dd.get_ult_names_snapshot,
            trigger_queue=self.ocr_queue,
            chat_box_cfg=self.config.get("chat_box"),
            ocr_lang=self.config.get("ocr_lang", ""),
            demo=self.demo,
            debug=self.ocr_debug,
        )
        if ocr_enabled:
            self.ocr_watcher.start()

        ocr_label = "OCR On" if (ocr_enabled and self.ocr_watcher.available) else "OCR Off"
        self.tray = WindowsTrayIcon(self.input_queue, ocr_label=ocr_label)
        self.tray.start()

        if self.demo:
            now = time.monotonic()
            self.timers[("demo_0", 0)] = now + 97
            self.timers[("demo_0", 1)] = now + 218
            self.timers[("demo_0", 2)] = now + 109
            self.timers[("demo_1", 0)] = now + 9
            self.timers[("demo_2", 1)] = now + 220
            self.timers[("demo_2", 2)] = now + 63
            self.timers[("demo_3", 1)] = now + 227
            self._show_overlay()
        else:
            self.root.withdraw()
            self.tray.set_status("Waiting for game")
            threading.Thread(target=self._poll_loop, daemon=True).start()

        self.root.after(16, self._poll_input)
        self.root.after(150, self._tick)

    def _default_position(self) -> tuple[int, int]:
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        total_h = TOP_BAR_H + self.grid_h
        return max(16, sw - 405), max(16, sh - (total_h + 14))

    def _reset_layout(self) -> None:
        self.tile_size = DEFAULT_TILE_SIZE
        self.alpha = 0.92
        self.root.attributes("-alpha", self.alpha)
        self.grid_w = self._calc_grid_w(self.tile_size)
        self.grid_h = self._calc_grid_h(self.tile_size, self._row_count)
        total_h = TOP_BAR_H + self.grid_h
        x, y = self._default_position()
        self.root.geometry(f"{self.grid_w}x{total_h}+{x}+{y}")
        self._draw_top_bar()
        self._build_grid_cells(self._row_count)
        self._rebuild_scaled_icons(high_quality=True)
        self._render_grid_state()
        self._sync_win_rect()
        self._save_config()

    def _get_state_snapshot(self) -> dict | None:
        with self.lock:
            return self.latest_state

    @staticmethod
    def _calc_grid_w(tile: int) -> int:
        return GRID_PAD * 2 + 3 * tile + 2 * TILE_GAP

    @staticmethod
    def _calc_grid_h(tile: int, rows: int) -> int:
        rows = max(1, rows)
        return GRID_PAD * 2 + rows * tile + (rows - 1) * TILE_GAP

    def _load_config(self) -> dict:
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_config(self) -> None:
        data = dict(self.config)
        data.update(
            {
                "x": self.root.winfo_x(),
                "y": self.root.winfo_y(),
                "alpha": round(self.alpha, 3),
                "tile_size": self.tile_size,
            }
        )
        self.config = data
        try:
            CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _get_hwnd(self) -> int:
        user32 = ctypes.windll.user32
        wid = self.root.winfo_id()
        return user32.GetParent(wid) or wid

    def _apply_win32_styles(self) -> None:
        if sys.platform != "win32":
            return
        self.root.update_idletasks()
        user32 = ctypes.windll.user32
        hwnd = self._get_hwnd()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        new_style = (
            style
            | WS_EX_LAYERED
            | WS_EX_TRANSPARENT
            | WS_EX_NOACTIVATE
            | WS_EX_TOOLWINDOW
            | WS_EX_TOPMOST
        )
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
        user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )
        self._sync_win_rect()

    def _sync_win_rect(self) -> None:
        if not self._visible:
            self._win_rect = None
            return
        if sys.platform == "win32":
            rc = wintypes.RECT()
            if ctypes.windll.user32.GetWindowRect(self._get_hwnd(), ctypes.byref(rc)):
                self._win_rect = (rc.left, rc.top, rc.right, rc.bottom)
                return
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self._win_rect = (x, y, x + self.grid_w, y + TOP_BAR_H + self.grid_h)

    def _build_ui(self) -> None:
        self.bar = tk.Canvas(
            self.root, width=self.grid_w, height=TOP_BAR_H,
            bg=BG_FRAME, highlightthickness=0, bd=0,
        )
        self.bar.pack(fill="x")

        self.grid = tk.Canvas(
            self.root, width=self.grid_w, height=self.grid_h,
            bg=BG_FRAME, highlightthickness=0, bd=0,
        )
        self.grid.pack()

        if sys.platform != "win32":
            for canvas in (self.bar, self.grid):
                canvas.bind("<Button-1>", self._fallback_left_down)
                canvas.bind("<B1-Motion>", self._fallback_left_move)
                canvas.bind("<ButtonRelease-1>", self._fallback_left_up)

        self._draw_top_bar()
        self._build_grid_cells(self._row_count)

    # --- Top Bar Geometry & Drawing ---

    def _resize_dot_center(self) -> tuple[int, int]:
        return 11, TOP_BAR_H // 2

    def _move_dot_center(self) -> tuple[int, int]:
        return 29, TOP_BAR_H // 2

    def _slider_bounds(self) -> tuple[int, int]:
        return 44, max(52, self.grid_w - 8)

    def _hit_top_bar(self, lx: int, ly: int) -> str | None:
        if not (0 <= ly < TOP_BAR_H):
            return None
        if lx <= 20:
            return "resize"
        if lx <= 39:
            return "move"
        return "slider"

    def _draw_top_bar(self) -> None:
        self.bar.config(width=self.grid_w)
        self.bar.delete("all")
        cy = TOP_BAR_H // 2
        dot_r = DOT_RADIUS

        rx, ry = self._resize_dot_center()
        r_color = DOT_RESIZE_HOVER if (self._drag_mode == "resize" or self._hover_dot == "resize") else DOT_RESIZE
        self.bar.create_oval(rx - dot_r, ry - dot_r, rx + dot_r, ry + dot_r, fill=r_color, outline="")

        mx, my = self._move_dot_center()
        m_color = DOT_MOVE_HOVER if (self._drag_mode == "move" or self._hover_dot == "move") else DOT_MOVE
        self.bar.create_oval(mx - dot_r, my - dot_r, mx + dot_r, my + dot_r, fill=m_color, outline="")

        sx1, sx2 = self._slider_bounds()
        self.bar.create_line(sx1, cy, sx2, cy, fill=TRACK_COLOR, width=2)
        t = (self.alpha - 0.35) / 0.65
        kx = sx1 + t * (sx2 - sx1)
        kr = 3.5
        self.bar.create_oval(kx - kr, cy - kr, kx + kr, cy + kr, fill=KNOB_GREEN, outline="")

    def _set_alpha_from_x(self, local_x: int) -> None:
        sx1, sx2 = self._slider_bounds()
        t = max(0.0, min(1.0, (local_x - sx1) / max(1, sx2 - sx1)))
        self.alpha = 0.35 + t * 0.65
        self.root.attributes("-alpha", self.alpha)
        self._draw_top_bar()

    # --- Resizing & Icon Scaling ---

    def _make_tk_icon_pair(self, raw_pil: Image.Image, high_quality: bool = True) -> tuple[ImageTk.PhotoImage, ImageTk.PhotoImage]:
        filt = LANCZOS if high_quality else BILINEAR
        ready = raw_pil.resize((self.tile_size, self.tile_size), filt)
        scrim = Image.new("RGBA", (self.tile_size, self.tile_size), (6, 8, 12, 185))
        dimmed = Image.alpha_composite(ready, scrim)
        return ImageTk.PhotoImage(ready), ImageTk.PhotoImage(dimmed)

    def _rebuild_scaled_icons(self, high_quality: bool = True) -> None:
        self.tk_icons = {
            k: self._make_tk_icon_pair(img, high_quality=high_quality)
            for k, img in self.raw_icons.items()
        }

    def _apply_tile_size(self, new_tile: int, anchor_br: tuple[int, int], high_quality: bool = False) -> None:
        new_tile = max(MIN_TILE_SIZE, min(MAX_TILE_SIZE, new_tile))
        if new_tile == self.tile_size:
            return
        self.tile_size = new_tile
        self.grid_w = self._calc_grid_w(self.tile_size)
        self.grid_h = self._calc_grid_h(self.tile_size, self._row_count)
        total_h = TOP_BAR_H + self.grid_h

        ax, ay = anchor_br
        nx = ax - self.grid_w
        ny = ay - total_h

        self.root.geometry(f"{self.grid_w}x{total_h}+{nx}+{ny}")
        self._win_rect = (nx, ny, ax, ay)

        self._draw_top_bar()
        self._build_grid_cells(self._row_count)
        self._rebuild_scaled_icons(high_quality=high_quality)
        self._render_grid_state()

    # --- Unified Left-Click & Tray Input Handling ---

    def _fallback_left_down(self, event) -> None:
        shift = bool(event.state & 0x0001)
        ctrl = bool(event.state & 0x0004)
        self._handle_left_down(event.x_root, event.y_root, shift, ctrl)

    def _fallback_left_move(self, event) -> None:
        self._handle_left_move(event.x_root, event.y_root)

    def _fallback_left_up(self, event) -> None:
        self._handle_left_up(event.x_root, event.y_root)

    def _compute_slot_cd(self, enemy: dict, col: int, is_aram: bool) -> int:
        if col in (0, 1):
            base_cd = enemy["spells"][col]["cd"]
            haste, _ = self._enemy_spell_haste(enemy, is_aram)
            return effective_cooldown(base_cd, haste)
        base_cd = self.dd.get_ult_base_cd(enemy["champ_id"], enemy["level"])
        return effective_cooldown(base_cd, enemy["ability_haste"])

    def _handle_left_down(self, sx: int, sy: int, shift: bool, ctrl: bool) -> None:
        if shift:
            return

        rect = self._win_rect
        if not rect:
            return
        x0, y0, x1, y1 = rect
        lx = sx - x0
        ly = sy - y0

        if ly < TOP_BAR_H:
            hit_bar = self._hit_top_bar(lx, ly)
            if hit_bar == "resize":
                self._drag_mode = "resize"
                self._resize_start_mouse = (sx, sy)
                self._resize_start_tile = self.tile_size
                self._resize_anchor_br = (x1, y1)
                self._draw_top_bar()
                return

            if hit_bar == "move":
                if ctrl:
                    self._quit()
                    return
                self._drag_mode = "move"
                self._drag_origin = (lx, ly)
                self._draw_top_bar()
                return

            if hit_bar == "slider":
                self._drag_mode = "slider"
                self._set_alpha_from_x(lx)
                return
            return

        hit = self._hit_test(lx, ly - TOP_BAR_H)
        if not hit:
            return
        row, col = hit
        enemy, is_aram = self._enemy_at(row)
        if not enemy:
            return

        eid = enemy["id"]
        key = (eid, col)
        now = time.monotonic()

        if ctrl:
            self.timers.pop(key, None)
            self.ocr_last_trigger[key] = now
            self._render_grid_state()
            return

        if key in self.timers and self.timers[key] > now:
            self.timers[key] -= 10.0
            if self.timers[key] <= now:
                del self.timers[key]
            self._render_grid_state()
            return

        full_cd = self._compute_slot_cd(enemy, col, is_aram)
        self.timers[key] = now + max(1, full_cd - REACTION_OFFSET_SEC)
        self._render_grid_state()

    def _handle_left_move(self, sx: int, sy: int) -> None:
        if self._drag_mode == "move":
            nx = sx - self._drag_origin[0]
            ny = sy - self._drag_origin[1]
            total_h = TOP_BAR_H + self.grid_h
            self.root.geometry(f"{self.grid_w}x{total_h}+{nx}+{ny}")
            self._win_rect = (nx, ny, nx + self.grid_w, ny + total_h)
        elif self._drag_mode == "resize":
            dx = (self._resize_start_mouse[0] - sx) / 3.0
            dy = (self._resize_start_mouse[1] - sy) / max(1, self._row_count)
            delta = dx if abs(dx) >= abs(dy) else dy
            target_tile = int(round(self._resize_start_tile + delta))
            self._apply_tile_size(target_tile, self._resize_anchor_br, high_quality=False)
        elif self._drag_mode == "slider" and self._win_rect:
            self._set_alpha_from_x(sx - self._win_rect[0])

    def _handle_left_up(self, _sx: int, _sy: int) -> None:
        if self._drag_mode == "resize":
            self._rebuild_scaled_icons(high_quality=True)
            self._render_grid_state()
        if self._drag_mode in ("move", "resize", "slider"):
            self._save_config()
            self._drag_mode = None
            self._sync_win_rect()
            self._draw_top_bar()

    def _update_hover(self) -> None:
        if sys.platform != "win32" or not self._visible or not self._win_rect:
            return
        pt = wintypes.POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            return

        x0, y0, x1, y1 = self._win_rect
        inside = x0 <= pt.x < x1 and y0 <= pt.y < y1
        lx = pt.x - x0
        ly = pt.y - y0

        hit_bar = self._hit_top_bar(lx, ly) if inside else None
        dot_hover = hit_bar if hit_bar in ("resize", "move") else None
        if dot_hover != self._hover_dot:
            self._hover_dot = dot_hover
            self._draw_top_bar()

        cell = self._hit_test(lx, ly - TOP_BAR_H) if (inside and ly >= TOP_BAR_H) else None
        if cell != self._hover_cell:
            if self._hover_cell is not None:
                pr, pc = self._hover_cell
                if pr < len(self._cell_items):
                    self.grid.itemconfig(self._cell_items[pr][pc]["border"], outline=BORDER_TILE)
            self._hover_cell = cell
            if cell is not None:
                r, c = cell
                self.grid.itemconfig(self._cell_items[r][c]["border"], outline=BORDER_HOVER)

    def _poll_input(self) -> None:
        if not self.running:
            return

        latest_move = None
        while True:
            try:
                ev = self.input_queue.get_nowait()
            except queue.Empty:
                break
            kind = ev[0]
            if kind == "lmove":
                latest_move = ev
            elif kind == "tray_quit":
                self._quit()
                return
            elif kind == "tray_reset":
                self._reset_layout()
            else:
                if latest_move is not None:
                    self._handle_left_move(latest_move[1], latest_move[2])
                    latest_move = None
                if kind == "ldown":
                    self._handle_left_down(ev[1], ev[2], ev[3], ev[4])
                elif kind == "lup":
                    self._handle_left_up(ev[1], ev[2])

        if latest_move is not None:
            self._handle_left_move(latest_move[1], latest_move[2])

        if self._drag_mode is None:
            self._update_hover()

        if self.running:
            self.root.after(16, self._poll_input)

    # --- Portrait Grid Canvas ---

    def _build_grid_cells(self, num_rows: int) -> None:
        self._row_count = max(1, num_rows)
        self.grid_w = self._calc_grid_w(self.tile_size)
        self.grid_h = self._calc_grid_h(self.tile_size, self._row_count)
        self.grid.config(width=self.grid_w, height=self.grid_h)
        self.grid.delete("all")
        self._cell_items = []
        self._hover_cell = None

        timer_font_sz = max(7, int(round(self.tile_size * 0.27)))
        fallback_font_sz = max(6, int(round(self.tile_size * 0.23)))
        pip_sz = max(4, int(round(self.tile_size * 0.14)))

        for r in range(self._row_count):
            row_cells = []
            for c in range(3):
                x0 = GRID_PAD + c * (self.tile_size + TILE_GAP)
                y0 = GRID_PAD + r * (self.tile_size + TILE_GAP)
                x1 = x0 + self.tile_size
                y1 = y0 + self.tile_size
                cx = (x0 + x1) / 2
                cy = (y0 + y1) / 2

                bg_rect = self.grid.create_rectangle(x0, y0, x1, y1, fill=BG_TILE, outline="")
                img_item = self.grid.create_image(x0, y0, anchor="nw")
                fallback_txt = self.grid.create_text(
                    cx, cy, text="", fill=FG_WHITE, font=("Segoe UI", fallback_font_sz, "bold"),
                )
                shadow_txt = self.grid.create_text(
                    cx + 1, cy + 1, text="", fill="#000000", font=("Segoe UI", timer_font_sz, "bold"),
                )
                timer_txt = self.grid.create_text(
                    cx, cy, text="", fill=FG_WHITE, font=("Segoe UI", timer_font_sz, "bold"),
                )
                ci_pip = self.grid.create_rectangle(
                    x1 - pip_sz - 1, y1 - pip_sz - 1, x1 - 1, y1 - 1, fill="", outline="",
                )
                border_rect = self.grid.create_rectangle(
                    x0, y0, x1 - 1, y1 - 1, fill="", outline=BORDER_TILE, width=1,
                )

                row_cells.append(
                    {
                        "bg": bg_rect,
                        "img": img_item,
                        "fallback": fallback_txt,
                        "shadow": shadow_txt,
                        "timer": timer_txt,
                        "ci_pip": ci_pip,
                        "border": border_rect,
                    }
                )
            self._cell_items.append(row_cells)

    def _hit_test(self, x: int, y: int) -> tuple[int, int] | None:
        step = self.tile_size + TILE_GAP
        gx = x - GRID_PAD
        gy = y - GRID_PAD
        if gx < 0 or gy < 0:
            return None
        c = gx // step
        r = gy // step
        if (gx % step) >= self.tile_size or (gy % step) >= self.tile_size:
            return None
        if 0 <= r < self._row_count and 0 <= c < 3:
            return (r, c)
        return None

    def _enemy_at(self, row: int) -> tuple[dict | None, bool]:
        with self.lock:
            state = self.latest_state
        if not state or row >= len(state["enemies"]):
            return None, False
        return state["enemies"][row], state["isAram"]

    def _detect_cosmic_insight(self, enemy: dict) -> bool:
        spec_ci = self.spectator.lookup(enemy)
        if spec_ci is not None:
            return spec_ci
        if enemy.get("explicit_ci") is not None:
            return bool(enemy["explicit_ci"])
        if enemy["is_insp_primary"]:
            return True
        if enemy["is_insp_secondary"]:
            seen = self.seen_non_ci_runes.get(enemy["id"], set())
            return len(seen) < 2
        return False

    def _enemy_spell_haste(self, enemy: dict, is_aram: bool) -> tuple[int, bool]:
        has_ci = self._detect_cosmic_insight(enemy)
        haste = (
            enemy["spell_item_haste"]
            + (COSMIC_INSIGHT_HASTE if has_ci else 0)
            + (ARAM_SPELL_HASTE if is_aram else 0)
        )
        return haste, has_ci

    def _drain_ocr_triggers(self, state: dict) -> None:
        now = time.monotonic()
        enemies_by_id = {e["id"]: e for e in state["enemies"]}
        game_time = float(state.get("gameTime") or 0.0)
        is_aram = bool(state.get("isAram"))

        while True:
            try:
                eid, col, msg_ts = self.ocr_queue.get_nowait()
            except queue.Empty:
                break

            enemy = enemies_by_id.get(eid)
            if not enemy:
                continue

            key = (eid, col)
            full_cd = self._compute_slot_cd(enemy, col, is_aram)

            if msg_ts is not None and msg_ts > game_time + 5.0:
                msg_ts = None

            if msg_ts is not None:
                ts_key = (eid, col, msg_ts)
                if ts_key in self.seen_ocr_ts:
                    continue
                self.seen_ocr_ts.add(ts_key)

                elapsed = max(0.0, game_time - msg_ts)
                if elapsed > OCR_MAX_STALE_TS_SEC:
                    continue
                rem = max(1.0, full_cd - elapsed)
                self.timers[key] = now + rem
                self.ocr_last_trigger[key] = now
            else:
                existing_end = self.timers.get(key, 0.0)
                last_trig = self.ocr_last_trigger.get(key, 0.0)
                if existing_end > now or (now - last_trig) < OCR_NO_TS_LOCKOUT_SEC:
                    continue
                self.ocr_last_trigger[key] = now
                self.timers[key] = now + max(1, full_cd - REACTION_OFFSET_SEC)

    # --- Lifecycle & Main Tick ---

    def _show_overlay(self) -> None:
        if not self._visible:
            self.root.deiconify()
            self._visible = True
            self._apply_win32_styles()
            self.tray.set_status("Demo Mode" if self.demo else "In Game")

    def _hide_overlay(self) -> None:
        if self._visible:
            self._visible = False
            self._win_rect = None
            self.root.withdraw()
            self.timers.clear()
            self.seen_non_ci_runes.clear()
            self.seen_ocr_ts.clear()
            self.ocr_last_trigger.clear()
            self.spectator.reset()
            self.ocr_watcher.reset()
            self.tray.set_status("Waiting for game")

    def _poll_loop(self) -> None:
        ssl_ctx = ssl._create_unverified_context()
        while self.running:
            data = fetch_live_data(ssl_ctx, self.dd)
            with self.lock:
                self.latest_state = data
            if data and data.get("activeRiotId"):
                self.spectator.trigger(data["activeRiotId"])
            time.sleep(2.0 if data else 2.5)

    def _drain_icon_queue(self) -> None:
        while True:
            try:
                cache_key, raw_pil = self.dd.ready_queue.get_nowait()
            except queue.Empty:
                break
            self.raw_icons[cache_key] = raw_pil
            self.tk_icons[cache_key] = self._make_tk_icon_pair(raw_pil, high_quality=True)

    def _ensure_assets(self, enemies: list[dict]) -> None:
        for e in enemies:
            cid = e["champ_id"]
            ckey = f"champ:{cid}"
            if ckey not in self.requested_icons:
                self.requested_icons.add(ckey)
                self.dd.request_icon("champ", cid)
                self.dd.request_champ_ult(cid)
            for sp in e["spells"]:
                skey = sp["key"]
                if skey and f"spell:{skey}" not in self.requested_icons:
                    self.requested_icons.add(f"spell:{skey}")
                    self.dd.request_icon("spell", skey)

    def _render_grid_state(self) -> None:
        with self.lock:
            state = self.latest_state
        if not state:
            return
        enemies = state["enemies"]
        if not enemies or len(enemies) != len(self._cell_items):
            return

        now = time.monotonic()
        for r, enemy in enumerate(enemies):
            eid = enemy["id"]
            if enemy.get("observed_non_ci"):
                self.seen_non_ci_runes.setdefault(eid, set()).update(enemy["observed_non_ci"])

            _, has_ci = self._enemy_spell_haste(enemy, state["isAram"])

            for c in (0, 1, 2):
                cell = self._cell_items[r][c]
                end = self.timers.get((eid, c))
                active = bool(end and end > now)
                if end is not None and not active:
                    del self.timers[(eid, c)]

                if c < 2:
                    sp = enemy["spells"][c]
                    icon_key = f"spell:{sp['key']}"
                    fallback_lbl = sp["short"]
                    fallback_bg = sp["color"]
                else:
                    icon_key = f"champ:{enemy['champ_id']}"
                    fallback_lbl = enemy["champ_short"]
                    fallback_bg = BG_TILE

                imgs = self.tk_icons.get(icon_key)
                if imgs:
                    tk_img = imgs[1] if active else imgs[0]
                    self.grid.itemconfig(cell["img"], image=tk_img)
                    self.grid.itemconfig(cell["bg"], fill=BG_TILE)
                    self.grid.itemconfig(cell["fallback"], text="")
                else:
                    self.grid.itemconfig(cell["img"], image="")
                    self.grid.itemconfig(cell["bg"], fill="#1E232B" if active else fallback_bg)
                    self.grid.itemconfig(cell["fallback"], text="" if active else fallback_lbl)

                if active:
                    rem = end - now
                    txt = format_timer(rem)
                    color = FG_WARN if rem <= 10.0 else FG_WHITE
                    self.grid.itemconfig(cell["shadow"], text=txt)
                    self.grid.itemconfig(cell["timer"], text=txt, fill=color)
                else:
                    self.grid.itemconfig(cell["shadow"], text="")
                    self.grid.itemconfig(cell["timer"], text="")

                if c == 2:
                    self.grid.itemconfig(cell["ci_pip"], fill=CI_PIP_COLOR if has_ci else "")
                else:
                    self.grid.itemconfig(cell["ci_pip"], fill="")

    def _tick(self) -> None:
        if not self.running:
            return
        self._drain_icon_queue()

        with self.lock:
            state = self.latest_state

        if state is None:
            self._hide_overlay()
            self.root.after(500, self._tick)
            return

        self._show_overlay()

        if self.demo:
            state["gameTime"] += 0.2

        enemies = state["enemies"]
        if not enemies:
            self.root.after(250, self._tick)
            return

        self._ensure_assets(enemies)
        self._drain_ocr_triggers(state)

        if len(enemies) != self._row_count:
            self._build_grid_cells(len(enemies))
            total_h = TOP_BAR_H + self.grid_h
            self.root.geometry(f"{self.grid_w}x{total_h}+{self.root.winfo_x()}+{self.root.winfo_y()}")
            self._draw_top_bar()
            self._apply_win32_styles()

        self._render_grid_state()
        self.root.after(200, self._tick)

    def _quit(self) -> None:
        if not self.running:
            return
        self.running = False
        self._win_rect = None
        self.ocr_watcher.stop()
        self.interceptor.stop()
        self.tray.stop()
        self._save_config()
        self.root.destroy()

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            self.ocr_watcher.stop()
            self.interceptor.stop()
            self.tray.stop()


if __name__ == "__main__":
    PortraitSpellOverlay(
        demo="--demo" in sys.argv,
        ocr_debug="--ocr-debug" in sys.argv,
    ).run()

import ctypes
import platform
from ctypes import wintypes
from typing import List, Optional, Tuple

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    user32 = ctypes.windll.user32

    _EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL

    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int

    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL

    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND

    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL

    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL

    user32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL

    user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ScreenToClient.restype = wintypes.BOOL

    SW_RESTORE = 9

    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_MOUSEMOVE = 0x0200
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    WM_RBUTTONDOWN = 0x0204
    WM_RBUTTONUP = 0x0205
    WM_MBUTTONDOWN = 0x0207
    WM_MBUTTONUP = 0x0208
    WM_MOUSEWHEEL = 0x020A

    MK_LBUTTON = 0x0001
    MK_RBUTTON = 0x0002
    MK_MBUTTON = 0x0010

    _MOUSE_DOWN_MSG = {"left": WM_LBUTTONDOWN, "right": WM_RBUTTONDOWN, "middle": WM_MBUTTONDOWN}
    _MOUSE_UP_MSG = {"left": WM_LBUTTONUP, "right": WM_RBUTTONUP, "middle": WM_MBUTTONUP}
    _MOUSE_FLAG = {"left": MK_LBUTTON, "right": MK_RBUTTON, "middle": MK_MBUTTON}

    def screen_to_client(hwnd, x: int, y: int) -> Tuple[int, int]:
        pt = wintypes.POINT(x, y)
        user32.ScreenToClient(hwnd, ctypes.byref(pt))
        return pt.x, pt.y

    def post_key(hwnd, vk: int, scan: int, extended: bool, up: bool):
        lparam = 1 | (scan << 16)
        if extended:
            lparam |= (1 << 24)
        if up:
            lparam |= (1 << 30) | (1 << 31)
        user32.PostMessageW(hwnd, WM_KEYUP if up else WM_KEYDOWN, vk, lparam)

    def post_mouse_move(hwnd, x_screen: int, y_screen: int):
        cx, cy = screen_to_client(hwnd, x_screen, y_screen)
        lparam = ((cy & 0xFFFF) << 16) | (cx & 0xFFFF)
        user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)

    def post_mouse_button(hwnd, button: str, x_screen: int, y_screen: int, up: bool):
        msg = (_MOUSE_UP_MSG if up else _MOUSE_DOWN_MSG).get(button)
        if msg is None:
            return
        cx, cy = screen_to_client(hwnd, x_screen, y_screen)
        lparam = ((cy & 0xFFFF) << 16) | (cx & 0xFFFF)
        wparam = 0 if up else _MOUSE_FLAG.get(button, 0)
        user32.PostMessageW(hwnd, msg, wparam, lparam)

    def post_mouse_wheel(hwnd, x_screen: int, y_screen: int, delta: int):
        # WM_MOUSEWHEEL je jedna z mála zpráv, kde jsou souřadnice v lParam
        # vztažené k obrazovce, ne ke klientské oblasti okna (MSDN).
        lparam = ((y_screen & 0xFFFF) << 16) | (x_screen & 0xFFFF)
        wheel_word = delta if delta >= 0 else delta + 0x10000
        wparam = (wheel_word & 0xFFFF) << 16
        user32.PostMessageW(hwnd, WM_MOUSEWHEEL, wparam, lparam)

    # --- Enumerace procesů a cílení podle procesu (stabilnější než titulek
    # okna, který se u her běžně mění podle stavu -- jméno postavy, mapa...) ---

    kernel32 = ctypes.windll.kernel32

    TH32CS_SNAPPROCESS = 0x00000002
    MAX_PATH = 260

    class _PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * MAX_PATH),
        ]

    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    def list_processes() -> List[Tuple[int, str]]:
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == -1:
            return []
        processes: List[Tuple[int, str]] = []
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        try:
            if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                while True:
                    processes.append((entry.th32ProcessID, entry.szExeFile))
                    if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                        break
        finally:
            kernel32.CloseHandle(snapshot)
        return processes

    def list_process_names() -> List[str]:
        seen = set()
        names = []
        for _pid, name in list_processes():
            if name and name.lower() not in seen:
                seen.add(name.lower())
                names.append(name)
        return sorted(names, key=str.lower)

    def get_window_pid(hwnd) -> int:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def is_process_running(process_name: str) -> bool:
        if not process_name:
            return False
        name_lower = process_name.lower()
        return any(name.lower() == name_lower for _pid, name in list_processes())

    def find_window_by_pid(pid: int) -> Optional[int]:
        for hwnd, _title in list_windows():
            if get_window_pid(hwnd) == pid:
                return hwnd
        return None

    def find_window_by_process(process_name: str) -> Optional[int]:
        if not process_name:
            return None
        name_lower = process_name.lower()
        pids = [pid for pid, name in list_processes() if name.lower() == name_lower]
        for pid in pids:
            hwnd = find_window_by_pid(pid)
            if hwnd:
                return hwnd
        return None

    def get_foreground_pid() -> int:
        return get_window_pid(user32.GetForegroundWindow())

    def is_process_foreground(process_name: str) -> bool:
        if not process_name:
            return False
        fg_pid = get_foreground_pid()
        return any(pid == fg_pid and name.lower() == process_name.lower()
                   for pid, name in list_processes())

    def resolve_target_hwnd(title: str, process_name: str) -> Optional[int]:
        """Proces má přednost před titulkem, protože titulek okna se u her
        běžně mění (jméno postavy, mapa, stav) a proces ne."""
        if process_name:
            hwnd = find_window_by_process(process_name)
            if hwnd:
                return hwnd
        if title:
            return find_window_by_title(title)
        return None

    def is_target_running(title: str, process_name: str) -> bool:
        if process_name:
            return is_process_running(process_name)
        if title:
            return find_window_by_title(title) is not None
        return True

    def is_target_foreground(title: str, process_name: str) -> bool:
        if process_name:
            return is_process_foreground(process_name)
        if title:
            return is_target_active(title)
        return True

    def focus_target(title: str, process_name: str) -> bool:
        hwnd = resolve_target_hwnd(title, process_name)
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, SW_RESTORE)
        return bool(user32.SetForegroundWindow(hwnd))

    def _get_title(hwnd) -> str:
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.strip()

    def list_windows() -> List[Tuple[int, str]]:
        windows: List[Tuple[int, str]] = []

        def _callback(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                title = _get_title(hwnd)
                if title:
                    windows.append((hwnd, title))
            return True

        user32.EnumWindows(_EnumWindowsProc(_callback), 0)
        return windows

    def get_foreground_window_title() -> str:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        return _get_title(hwnd)

    def find_window_by_title(title: str) -> Optional[int]:
        if not title:
            return None
        title_lower = title.lower()
        candidates = list_windows()
        for hwnd, wtitle in candidates:
            if wtitle.lower() == title_lower:
                return hwnd
        for hwnd, wtitle in candidates:
            if title_lower in wtitle.lower():
                return hwnd
        return None

    def is_target_active(title: str) -> bool:
        if not title:
            return True
        fg = get_foreground_window_title().lower()
        title_lower = title.lower()
        return title_lower in fg or fg in title_lower

    def focus_window(title: str) -> bool:
        hwnd = find_window_by_title(title)
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, SW_RESTORE)
        return bool(user32.SetForegroundWindow(hwnd))

else:
    def list_windows() -> List[Tuple[int, str]]:
        return []

    def get_foreground_window_title() -> str:
        return ""

    def find_window_by_title(title: str) -> Optional[int]:
        return None

    def is_target_active(title: str) -> bool:
        return True

    def focus_window(title: str) -> bool:
        return False

    def list_processes() -> List[Tuple[int, str]]:
        return []

    def list_process_names() -> List[str]:
        return []

    def is_process_running(process_name: str) -> bool:
        return False

    def find_window_by_process(process_name: str) -> Optional[int]:
        return None

    def is_process_foreground(process_name: str) -> bool:
        return False

    def resolve_target_hwnd(title: str, process_name: str) -> Optional[int]:
        return None

    def is_target_running(title: str, process_name: str) -> bool:
        return True

    def is_target_foreground(title: str, process_name: str) -> bool:
        return True

    def focus_target(title: str, process_name: str) -> bool:
        return False

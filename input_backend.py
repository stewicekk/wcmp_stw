import ctypes
import platform
from abc import ABC, abstractmethod
from typing import Optional, Set, Tuple

from pynput import mouse as pynput_mouse, keyboard as pynput_keyboard

import window_utils

IS_WINDOWS = platform.system() == "Windows"

BACKEND_PYNPUT = "pynput"
BACKEND_WINSCAN = "winscan"
BACKEND_POSTMESSAGE = "postmessage"

BACKEND_LABELS = {
    BACKEND_PYNPUT: "pynput (univerzální, funguje všude)",
    BACKEND_WINSCAN: "Windows Scan Code (SendInput, lepší kompatibilita s hrami)",
    BACKEND_POSTMESSAGE: "PostMessage na pozadí (bez fokusu, jen klasické Win32 okna)",
}

SPECIAL_VK = {
    "alt": 0x12, "alt_l": 0x12, "alt_r": 0x12, "alt_gr": 0x12,
    "backspace": 0x08,
    "caps_lock": 0x14,
    "cmd": 0x5B, "cmd_l": 0x5B, "cmd_r": 0x5C,
    "ctrl": 0x11, "ctrl_l": 0x11, "ctrl_r": 0x11,
    "delete": 0x2E,
    "down": 0x28,
    "end": 0x23,
    "enter": 0x0D,
    "esc": 0x1B,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "f13": 0x7C, "f14": 0x7D, "f15": 0x7E, "f16": 0x7F, "f17": 0x80,
    "f18": 0x81, "f19": 0x82, "f20": 0x83,
    "home": 0x24,
    "insert": 0x2D,
    "left": 0x25,
    "media_next": 0xB0, "media_play_pause": 0xB3, "media_previous": 0xB1,
    "media_volume_down": 0xAE, "media_volume_mute": 0xAD, "media_volume_up": 0xAF,
    "menu": 0x5D,
    "num_lock": 0x90,
    "page_down": 0x22,
    "page_up": 0x21,
    "pause": 0x13,
    "print_screen": 0x2C,
    "right": 0x27,
    "scroll_lock": 0x91,
    "shift": 0x10, "shift_l": 0x10, "shift_r": 0x10,
    "space": 0x20,
    "tab": 0x09,
    "up": 0x26,
}

EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E,
                0x5B, 0x5C, 0x5D, 0x90, 0x6F, 0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB3}


def resolve_vk(key_str: str) -> Optional[Tuple[int, bool]]:
    if key_str.startswith("char:"):
        char = key_str[5:]
        if IS_WINDOWS and char:
            res = ctypes.windll.user32.VkKeyScanW(ord(char[0]))
            if res != -1:
                vk = res & 0xFF
                return vk, vk in EXTENDED_VKS
        return None
    if key_str.startswith("vk:"):
        vk = int(key_str[3:])
        return vk, vk in EXTENDED_VKS
    if key_str.startswith("special:"):
        name = key_str.split("special:")[1]
        vk = SPECIAL_VK.get(name)
        if vk is not None:
            return vk, vk in EXTENDED_VKS
    return None


class InputBackend(ABC):
    @abstractmethod
    def move(self, x: int, y: int): ...

    @abstractmethod
    def mouse_down(self, button: str, x: int, y: int): ...

    @abstractmethod
    def mouse_up(self, button: str, x: int, y: int): ...

    @abstractmethod
    def scroll(self, x: int, y: int, dx: int, dy: int): ...

    @abstractmethod
    def key_down(self, key_str: str): ...

    @abstractmethod
    def key_up(self, key_str: str): ...

    def release_all(self):
        pass


class PynputBackend(InputBackend):
    def __init__(self):
        self._mouse = pynput_mouse.Controller()
        self._keyboard = pynput_keyboard.Controller()
        self._pressed_keys: Set[str] = set()
        self._pressed_buttons: Set[str] = set()

    def _str_to_key(self, s: str):
        if s.startswith("char:"):
            return pynput_keyboard.KeyCode.from_char(s[5:])
        if s.startswith("vk:"):
            return pynput_keyboard.KeyCode.from_vk(int(s[3:]))
        name = s.split("special:")[1]
        return getattr(pynput_keyboard.Key, name)

    def move(self, x, y):
        self._mouse.position = (x, y)

    def mouse_down(self, button, x, y):
        self._mouse.position = (x, y)
        btn = getattr(pynput_mouse.Button, button)
        self._mouse.press(btn)
        self._pressed_buttons.add(button)

    def mouse_up(self, button, x, y):
        self._mouse.position = (x, y)
        btn = getattr(pynput_mouse.Button, button)
        self._mouse.release(btn)
        self._pressed_buttons.discard(button)

    def scroll(self, x, y, dx, dy):
        self._mouse.position = (x, y)
        self._mouse.scroll(dx, dy)

    def key_down(self, key_str):
        self._keyboard.press(self._str_to_key(key_str))
        self._pressed_keys.add(key_str)

    def key_up(self, key_str):
        self._keyboard.release(self._str_to_key(key_str))
        self._pressed_keys.discard(key_str)

    def release_all(self):
        for k in list(self._pressed_keys):
            try:
                self._keyboard.release(self._str_to_key(k))
            except Exception:
                pass
        self._pressed_keys.clear()
        for b in list(self._pressed_buttons):
            try:
                self._mouse.release(getattr(pynput_mouse.Button, b))
            except Exception:
                pass
        self._pressed_buttons.clear()


if IS_WINDOWS:
    PUL = ctypes.POINTER(ctypes.c_ulong)

    class _KeyBdInput(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                    ("dwExtraInfo", PUL)]

    class _MouseInput(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                    ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]

    class _HardwareInput(ctypes.Structure):
        _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_short),
                    ("wParamH", ctypes.c_ushort)]

    class _InputUnion(ctypes.Union):
        _fields_ = [("ki", _KeyBdInput), ("mi", _MouseInput), ("hi", _HardwareInput)]

    class _Input(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("ii", _InputUnion)]

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_HWHEEL = 0x1000
    MOUSEEVENTF_ABSOLUTE = 0x8000

    _BUTTON_DOWN = {
        "left": MOUSEEVENTF_LEFTDOWN, "right": MOUSEEVENTF_RIGHTDOWN,
        "middle": MOUSEEVENTF_MIDDLEDOWN,
    }
    _BUTTON_UP = {
        "left": MOUSEEVENTF_LEFTUP, "right": MOUSEEVENTF_RIGHTUP,
        "middle": MOUSEEVENTF_MIDDLEUP,
    }

    class WindowsScanCodeBackend(InputBackend):
        """Vstup přes SendInput se scan-code injekcí. Lepší kompatibilita
        s hrami postavenými na DirectInput/RawInput než čistý pynput VK vstup.
        Souřadnice myši se počítají vůči primárnímu monitoru (SM_CXSCREEN/
        SM_CYSCREEN). Vícemonitorové absolutní souřadnice nejsou podporovány."""

        def __init__(self):
            self._user32 = ctypes.windll.user32
            self._screen_w = self._user32.GetSystemMetrics(0) or 1920
            self._screen_h = self._user32.GetSystemMetrics(1) or 1080
            self._pressed_vks: Set[int] = set()
            self._pressed_buttons: Set[str] = set()

        def _send(self, inp: _Input):
            self._user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))

        def _to_abs(self, x, y):
            return (
                int(x * 65535 / max(self._screen_w - 1, 1)),
                int(y * 65535 / max(self._screen_h - 1, 1)),
            )

        def move(self, x, y):
            ax, ay = self._to_abs(x, y)
            mi = _MouseInput(ax, ay, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, None)
            self._send(_Input(INPUT_MOUSE, _InputUnion(mi=mi)))

        def _mouse_flag(self, table, button):
            flag = table.get(button)
            if flag is None:
                raise ValueError(f"Nepodporované tlačítko myši: {button}")
            return flag

        def mouse_down(self, button, x, y):
            self.move(x, y)
            flag = self._mouse_flag(_BUTTON_DOWN, button)
            mi = _MouseInput(0, 0, 0, flag, 0, None)
            self._send(_Input(INPUT_MOUSE, _InputUnion(mi=mi)))
            self._pressed_buttons.add(button)

        def mouse_up(self, button, x, y):
            self.move(x, y)
            flag = self._mouse_flag(_BUTTON_UP, button)
            mi = _MouseInput(0, 0, 0, flag, 0, None)
            self._send(_Input(INPUT_MOUSE, _InputUnion(mi=mi)))
            self._pressed_buttons.discard(button)

        def scroll(self, x, y, dx, dy):
            self.move(x, y)
            if dy:
                mi = _MouseInput(0, 0, int(dy * 120), MOUSEEVENTF_WHEEL, 0, None)
                self._send(_Input(INPUT_MOUSE, _InputUnion(mi=mi)))
            if dx:
                mi = _MouseInput(0, 0, int(dx * 120), MOUSEEVENTF_HWHEEL, 0, None)
                self._send(_Input(INPUT_MOUSE, _InputUnion(mi=mi)))

        def _send_key(self, vk: int, extended: bool, up: bool):
            scan = self._user32.MapVirtualKeyW(vk, 0)
            flags = KEYEVENTF_SCANCODE
            if extended:
                flags |= KEYEVENTF_EXTENDEDKEY
            if up:
                flags |= KEYEVENTF_KEYUP
            ki = _KeyBdInput(0, scan, flags, 0, None)
            self._send(_Input(INPUT_KEYBOARD, _InputUnion(ki=ki)))

        def key_down(self, key_str):
            resolved = resolve_vk(key_str)
            if resolved is None:
                return
            vk, extended = resolved
            self._send_key(vk, extended, up=False)
            self._pressed_vks.add((vk, extended))

        def key_up(self, key_str):
            resolved = resolve_vk(key_str)
            if resolved is None:
                return
            vk, extended = resolved
            self._send_key(vk, extended, up=True)
            self._pressed_vks.discard((vk, extended))

        def release_all(self):
            for vk, extended in list(self._pressed_vks):
                try:
                    self._send_key(vk, extended, up=True)
                except Exception:
                    pass
            self._pressed_vks.clear()
            for b in list(self._pressed_buttons):
                try:
                    flag = _BUTTON_UP.get(b)
                    if flag:
                        mi = _MouseInput(0, 0, 0, flag, 0, None)
                        self._send(_Input(INPUT_MOUSE, _InputUnion(mi=mi)))
                except Exception:
                    pass
            self._pressed_buttons.clear()
else:
    WindowsScanCodeBackend = None


class PostMessageBackend(InputBackend):
    """Posílá vstup přímo na konkrétní HWND přes PostMessage, bez potřeby aby
    okno bylo aktivní/v popředí. Funguje jen pro klasické Win32 aplikace, které
    vstup zpracovávají přes zprávy okna (WM_KEYDOWN/WM_LBUTTONDOWN...). Naprostá
    většina her (DirectInput/RawInput, čtení stavu klávesnice přímo z hardwaru)
    tyto zprávy ignoruje úplně -- tohle NENÍ obchvat takových her, je to
    samostatná technika pro jiný typ cíle."""

    def __init__(self, target_window_title: str, target_process_name: str = ""):
        if not window_utils.IS_WINDOWS:
            raise RuntimeError("PostMessage backend je dostupný jen na Windows.")
        title = (target_window_title or "").strip()
        process = (target_process_name or "").strip()
        if not title and not process:
            raise RuntimeError("PostMessage backend potřebuje vyplněné cílové okno nebo proces.")
        hwnd = window_utils.resolve_target_hwnd(title, process)
        if not hwnd:
            target_desc = process or title
            raise RuntimeError(f"Cíl '{target_desc}' nebyl nalezen (musí běžet).")
        self._hwnd = hwnd
        self._pressed_vks: Set[Tuple[int, int, bool]] = set()
        self._pressed_buttons: Set[str] = set()

    def move(self, x, y):
        window_utils.post_mouse_move(self._hwnd, x, y)

    def mouse_down(self, button, x, y):
        window_utils.post_mouse_button(self._hwnd, button, x, y, up=False)
        self._pressed_buttons.add(button)

    def mouse_up(self, button, x, y):
        window_utils.post_mouse_button(self._hwnd, button, x, y, up=True)
        self._pressed_buttons.discard(button)

    def scroll(self, x, y, dx, dy):
        if dy:
            window_utils.post_mouse_wheel(self._hwnd, x, y, int(dy * 120))

    def key_down(self, key_str):
        resolved = resolve_vk(key_str)
        if resolved is None:
            return
        vk, extended = resolved
        scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        window_utils.post_key(self._hwnd, vk, scan, extended, up=False)
        self._pressed_vks.add((vk, scan, extended))

    def key_up(self, key_str):
        resolved = resolve_vk(key_str)
        if resolved is None:
            return
        vk, extended = resolved
        scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        window_utils.post_key(self._hwnd, vk, scan, extended, up=True)
        self._pressed_vks.discard((vk, scan, extended))

    def release_all(self):
        for vk, scan, extended in list(self._pressed_vks):
            try:
                window_utils.post_key(self._hwnd, vk, scan, extended, up=True)
            except Exception:
                pass
        self._pressed_vks.clear()
        for b in list(self._pressed_buttons):
            try:
                window_utils.post_mouse_button(self._hwnd, b, 0, 0, up=True)
            except Exception:
                pass
        self._pressed_buttons.clear()


def available_backends():
    backends = [BACKEND_PYNPUT]
    if IS_WINDOWS:
        backends.append(BACKEND_WINSCAN)
        backends.append(BACKEND_POSTMESSAGE)
    return backends


def create_backend(backend_id: str, target_window_title: str = "", target_process_name: str = "") -> InputBackend:
    if backend_id == BACKEND_WINSCAN and IS_WINDOWS:
        return WindowsScanCodeBackend()
    if backend_id == BACKEND_POSTMESSAGE and IS_WINDOWS:
        return PostMessageBackend(target_window_title, target_process_name)
    return PynputBackend()

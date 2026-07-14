import json
import time
import random
import threading
import uuid
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Callable
from pynput import mouse, keyboard

from input_backend import InputBackend, PynputBackend, create_backend

VALID_KINDS = {"move", "click", "scroll", "key_down", "key_up", "wait"}


@dataclass
class MacroEvent:
    t: float
    kind: str
    data: dict
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


def _key_to_str(key) -> str:
    if isinstance(key, keyboard.KeyCode):
        return f"char:{key.char}" if key.char is not None else f"vk:{key.vk}"
    return f"special:{key.name}"


def resequence_from_gaps(events: List[MacroEvent]) -> List[MacroEvent]:
    """Přepočítá časy událostí v novém pořadí, ale zachová relativní mezery
    z původního nahrání každé jednotlivé události (gap = její vlastní t
    minus t předchozí položky v novém pořadí, ohraničeno na >= 0)."""
    if not events:
        return events
    out = []
    t = 0.0
    prev_original_t = 0.0
    for i, ev in enumerate(events):
        if i == 0:
            gap = 0.0
        else:
            gap = max(ev.t - prev_original_t, 0.01)
        prev_original_t = ev.t
        t += gap
        out.append(MacroEvent(t=round(t, 4), kind=ev.kind, data=ev.data, uid=ev.uid))
    return out


class MacroRecorder:
    def __init__(self):
        self.events: List[MacroEvent] = []
        self._start_time = 0.0
        self._recording = False
        self._mouse_listener: Optional[mouse.Listener] = None
        self._key_listener: Optional[keyboard.Listener] = None
        self.record_mouse_move = True
        self.record_scroll = True
        self.move_sample_interval = 0.02
        self._last_move_t = 0.0
        self.on_event: Optional[Callable[[MacroEvent], None]] = None
        self.ignored_keys = {keyboard.Key.f9, keyboard.Key.f12}
        self._held_keys = set()

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self):
        self.events = []
        self._last_move_t = 0.0
        self._held_keys = set()
        self._start_time = time.perf_counter()
        self._recording = True
        self._mouse_listener = mouse.Listener(
            on_move=self._on_move, on_click=self._on_click, on_scroll=self._on_scroll
        )
        self._key_listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        self._mouse_listener.start()
        self._key_listener.start()

    def stop(self) -> List[MacroEvent]:
        self._recording = False
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None
        if self._key_listener:
            self._key_listener.stop()
            self._key_listener = None
        return self.events

    def _now(self) -> float:
        return time.perf_counter() - self._start_time

    def _push(self, ev: MacroEvent):
        self.events.append(ev)
        if self.on_event:
            self.on_event(ev)

    def _on_move(self, x, y):
        if not self._recording or not self.record_mouse_move:
            return
        t = self._now()
        if t - self._last_move_t < self.move_sample_interval:
            return
        self._last_move_t = t
        self._push(MacroEvent(t, "move", {"x": x, "y": y}))

    def _on_click(self, x, y, button, pressed):
        if not self._recording:
            return
        self._push(MacroEvent(self._now(), "click", {
            "x": x, "y": y, "button": button.name, "pressed": pressed
        }))

    def _on_scroll(self, x, y, dx, dy):
        if not self._recording or not self.record_scroll:
            return
        self._push(MacroEvent(self._now(), "scroll", {"x": x, "y": y, "dx": dx, "dy": dy}))

    def _on_press(self, key):
        if not self._recording or key in self.ignored_keys:
            return
        key_str = _key_to_str(key)
        if key_str in self._held_keys:
            return
        self._held_keys.add(key_str)
        self._push(MacroEvent(self._now(), "key_down", {"key": key_str}))

    def _on_release(self, key):
        if not self._recording or key in self.ignored_keys:
            return
        key_str = _key_to_str(key)
        self._held_keys.discard(key_str)
        self._push(MacroEvent(self._now(), "key_up", {"key": key_str}))


class MacroPlayer:
    def __init__(self, on_finished: Optional[Callable] = None,
                 on_progress: Optional[Callable[[int, int], None]] = None,
                 on_loop: Optional[Callable[[int, int], None]] = None,
                 on_error: Optional[Callable[[str], None]] = None):
        self._stop_flag = threading.Event()
        self._paused = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.on_finished = on_finished
        self.on_progress = on_progress
        self.on_loop = on_loop
        self.on_error = on_error
        self.backend_id = "pynput"
        self.target_window_title = ""
        self.target_process_name = ""

    def is_playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def is_paused(self) -> bool:
        return self._paused.is_set()

    def play(self, events: List[MacroEvent], loops: int = 1, speed: float = 1.0,
             jitter_ms: int = 0, start_delay: float = 0.0):
        if self.is_playing() or not events:
            return
        self._stop_flag.clear()
        self._paused.clear()
        self._thread = threading.Thread(
            target=self._run, args=(events, loops, speed, jitter_ms, start_delay), daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop_flag.set()
        self._paused.clear()

    def toggle_pause(self):
        if self._paused.is_set():
            self._paused.clear()
        else:
            self._paused.set()

    def _interruptible_wait(self, seconds: float) -> bool:
        remaining = seconds
        step = 0.05
        while remaining > 0:
            if self._stop_flag.is_set():
                return True
            while self._paused.is_set():
                if self._stop_flag.wait(step):
                    return True
            w = min(step, remaining)
            if self._stop_flag.wait(w):
                return True
            remaining -= w
        return False

    def _run(self, events, loops, speed, jitter_ms, start_delay):
        try:
            backend = create_backend(self.backend_id, self.target_window_title, self.target_process_name)
        except Exception as e:
            if self.on_error:
                self.on_error(str(e))
            if self.on_finished:
                self.on_finished()
            return
        infinite = loops <= 0
        count = 0
        try:
            if start_delay > 0 and self._interruptible_wait(start_delay):
                return
            while (infinite or count < loops) and not self._stop_flag.is_set():
                last_t = 0.0
                total = len(events)
                for i, ev in enumerate(events):
                    if self._stop_flag.is_set():
                        return
                    delay = (ev.t - last_t) / max(speed, 0.01)
                    if jitter_ms > 0:
                        delay += random.uniform(-jitter_ms, jitter_ms) / 1000.0
                    if delay > 0 and self._interruptible_wait(delay):
                        return
                    last_t = ev.t
                    self._exec(ev, backend)
                    if self.on_progress:
                        self.on_progress(i + 1, total)
                count += 1
                if self.on_loop:
                    self.on_loop(count, loops)
        finally:
            backend.release_all()
            if self.on_finished:
                self.on_finished()

    def _exec(self, ev: MacroEvent, backend: InputBackend):
        try:
            if ev.kind == "move":
                backend.move(ev.data["x"], ev.data["y"])
            elif ev.kind == "click":
                if ev.data["pressed"]:
                    backend.mouse_down(ev.data["button"], ev.data["x"], ev.data["y"])
                else:
                    backend.mouse_up(ev.data["button"], ev.data["x"], ev.data["y"])
            elif ev.kind == "scroll":
                backend.scroll(ev.data["x"], ev.data["y"], ev.data["dx"], ev.data["dy"])
            elif ev.kind == "key_down":
                backend.key_down(ev.data["key"])
            elif ev.kind == "key_up":
                backend.key_up(ev.data["key"])
            elif ev.kind == "wait":
                pass
        except Exception:
            pass


def describe_event(ev: MacroEvent) -> str:
    d = ev.data
    if ev.kind == "move":
        return f"x={d['x']} y={d['y']}"
    if ev.kind == "click":
        state = "stisk" if d["pressed"] else "puštění"
        return f"{d['button']} {state} @ {d['x']},{d['y']}"
    if ev.kind == "scroll":
        return f"dx={d['dx']} dy={d['dy']} @ {d['x']},{d['y']}"
    if ev.kind in ("key_down", "key_up"):
        return d["key"]
    if ev.kind == "wait":
        return "čekání"
    return str(d)


KIND_LABEL = {
    "move": "Pohyb myši",
    "click": "Klik",
    "scroll": "Kolečko",
    "key_down": "Klávesa dolů",
    "key_up": "Klávesa nahoru",
    "wait": "Čekání",
}


def events_to_dicts(events: List[MacroEvent]) -> list:
    return [asdict(e) for e in events]


def dicts_to_events(raw: list) -> List[MacroEvent]:
    out = []
    for r in raw:
        r = dict(r)
        r.setdefault("uid", uuid.uuid4().hex[:8])
        out.append(MacroEvent(**r))
    return out


def events_to_json(events: List[MacroEvent]) -> str:
    return json.dumps(events_to_dicts(events), indent=2, ensure_ascii=False)


def events_from_json(s: str) -> List[MacroEvent]:
    return dicts_to_events(json.loads(s))


def estimate_duration(events: List[MacroEvent]) -> float:
    return events[-1].t if events else 0.0

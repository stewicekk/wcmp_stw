import json
import os
import time
from typing import Dict, Any

DATA_DIR = os.path.join(os.path.expanduser("~"), ".stw_woofmc")
MACROS_FILE = os.path.join(DATA_DIR, "macros.json")
PLAYLISTS_FILE = os.path.join(DATA_DIR, "playlists.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

DEFAULT_CONFIG = {
    "hotkey_record": "<f9>",
    "hotkey_play": "<f10>",
    "hotkey_pause": "<f11>",
    "hotkey_panic": "<f8>",
    "start_minimized": False,
    "close_to_tray": True,
    "show_notifications": True,
    "input_backend": "pynput",
    "record_countdown": 0.0,
    "target_window_title": "",
    "target_process_name": "",
    "target_window_enabled": False,
    "target_window_autofocus": False,
    "target_window_mode": "foreground",
}

DEFAULT_MACRO = {
    "events": [],
    "loops": 1,
    "speed": 1.0,
    "jitter": 0,
    "start_delay": 2.0,
    "created": 0.0,
    "modified": 0.0,
    "run_count": 0,
    "hotkey": "",
    "target_window_title": "",
    "target_process_name": "",
    "input_backend_override": "",
}


def ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(path: str, default):
    ensure_dir()
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path: str, data):
    ensure_dir()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_macros() -> Dict[str, Any]:
    macros = _load_json(MACROS_FILE, {})
    for name, macro in macros.items():
        for key, val in DEFAULT_MACRO.items():
            macro.setdefault(key, val)
    return macros


def save_macros(macros: Dict[str, Any]):
    _save_json(MACROS_FILE, macros)


def new_macro_dict() -> dict:
    now = time.time()
    m = dict(DEFAULT_MACRO)
    m["created"] = now
    m["modified"] = now
    return m


def touch_macro(macro: dict):
    macro["modified"] = time.time()


def load_playlists() -> Dict[str, Any]:
    return _load_json(PLAYLISTS_FILE, {})


def save_playlists(playlists: Dict[str, Any]):
    _save_json(PLAYLISTS_FILE, playlists)


def load_config() -> Dict[str, Any]:
    cfg = _load_json(CONFIG_FILE, dict(DEFAULT_CONFIG))
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    return merged


def save_config(cfg: Dict[str, Any]):
    _save_json(CONFIG_FILE, cfg)


def export_macro(path: str, macro: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(macro, f, indent=2, ensure_ascii=False)


def import_macro(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key, val in DEFAULT_MACRO.items():
        data.setdefault(key, val)
    return data


def export_backup(path: str, macros: dict, playlists: dict, config: dict):
    payload = {
        "app": "STW WoofMC",
        "backup_version": 1,
        "exported_at": time.time(),
        "macros": macros,
        "playlists": playlists,
        "config": config,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def import_backup(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "macros" not in data:
        raise ValueError("Soubor neobsahuje platnou zálohu STW WoofMC.")
    return data

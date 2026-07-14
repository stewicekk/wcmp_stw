from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QLabel,
    QPushButton, QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox, QDialogButtonBox,
    QMessageBox, QWidget
)

import storage
import window_utils
from input_backend import available_backends, BACKEND_LABELS
from macro_engine import MacroEvent, VALID_KINDS

_QT_KEY_NAMES = {
    Qt.Key_F1: "f1", Qt.Key_F2: "f2", Qt.Key_F3: "f3", Qt.Key_F4: "f4",
    Qt.Key_F5: "f5", Qt.Key_F6: "f6", Qt.Key_F7: "f7", Qt.Key_F8: "f8",
    Qt.Key_F9: "f9", Qt.Key_F10: "f10", Qt.Key_F11: "f11", Qt.Key_F12: "f12",
    Qt.Key_F13: "f13", Qt.Key_F14: "f14", Qt.Key_F15: "f15", Qt.Key_F16: "f16",
    Qt.Key_Insert: "insert", Qt.Key_Delete: "delete", Qt.Key_Home: "home",
    Qt.Key_End: "end", Qt.Key_PageUp: "page_up", Qt.Key_PageDown: "page_down",
    Qt.Key_Pause: "pause", Qt.Key_ScrollLock: "scroll_lock",
    Qt.Key_CapsLock: "caps_lock", Qt.Key_NumLock: "num_lock",
    Qt.Key_Escape: "esc", Qt.Key_Tab: "tab", Qt.Key_Space: "space",
}


def qt_key_to_hotkey_str(key: int, text: str, modifiers=None) -> Optional[str]:
    parts = []
    if modifiers is not None:
        if modifiers & Qt.ControlModifier:
            parts.append("<ctrl>")
        if modifiers & Qt.AltModifier:
            parts.append("<alt>")
        if modifiers & Qt.ShiftModifier:
            parts.append("<shift>")
        if modifiers & Qt.MetaModifier:
            parts.append("<cmd>")
    if key in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta):
        return None
    if key in _QT_KEY_NAMES:
        parts.append(f"<{_QT_KEY_NAMES[key]}>")
    elif text and text.isprintable() and len(text) == 1:
        parts.append(text.lower())
    else:
        return None
    return "+".join(parts)


def pretty_hotkey(hotkey: str) -> str:
    if not hotkey:
        return ""
    pieces = [p.strip("<>").upper() for p in hotkey.split("+")]
    return " + ".join(pieces)


class HotkeyCaptureEdit(QLineEdit):
    def __init__(self, initial: str, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Klikni a stiskni klávesu (i s Ctrl/Alt/Shift)...")
        self.hotkey = initial
        self._display(initial)

    def _display(self, hk: str):
        self.setText(pretty_hotkey(hk))

    def keyPressEvent(self, event):
        resolved = qt_key_to_hotkey_str(event.key(), event.text(), event.modifiers())
        if resolved:
            self.hotkey = resolved
            self._display(resolved)
        event.accept()

    def mousePressEvent(self, event):
        self.setText("...")
        super().mousePressEvent(event)


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nastavení")
        self.setMinimumWidth(380)
        self.config = dict(config)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.edit_hotkey_record = HotkeyCaptureEdit(self.config.get("hotkey_record", "<f9>"))
        form.addRow("Hotkey nahrávání:", self.edit_hotkey_record)

        self.edit_hotkey_play = HotkeyCaptureEdit(self.config.get("hotkey_play", "<f10>"))
        form.addRow("Hotkey přehrávání:", self.edit_hotkey_play)

        self.edit_hotkey_pause = HotkeyCaptureEdit(self.config.get("hotkey_pause", "<f11>"))
        form.addRow("Hotkey pauza:", self.edit_hotkey_pause)

        self.edit_hotkey_panic = HotkeyCaptureEdit(self.config.get("hotkey_panic", "<f8>"))
        form.addRow("Hotkey PANIC STOP (zastaví vše):", self.edit_hotkey_panic)

        self.combo_backend = QComboBox()
        for b in available_backends():
            self.combo_backend.addItem(BACKEND_LABELS.get(b, b), b)
        idx = self.combo_backend.findData(self.config.get("input_backend", "pynput"))
        if idx >= 0:
            self.combo_backend.setCurrentIndex(idx)
        form.addRow("Vstupní backend:", self.combo_backend)

        self.spin_countdown = QDoubleSpinBox()
        self.spin_countdown.setRange(0.0, 10.0)
        self.spin_countdown.setSingleStep(0.5)
        self.spin_countdown.setValue(self.config.get("record_countdown", 0.0))
        form.addRow("Odpočet před nahráváním (s):", self.spin_countdown)

        layout.addLayout(form)

        self.chk_minimized = QCheckBox("Spustit minimalizované")
        self.chk_minimized.setChecked(self.config.get("start_minimized", False))
        layout.addWidget(self.chk_minimized)

        self.chk_tray = QCheckBox("Zavřít okno do trayu místo ukončení")
        self.chk_tray.setChecked(self.config.get("close_to_tray", True))
        layout.addWidget(self.chk_tray)

        self.chk_notify = QCheckBox("Zobrazovat systémová upozornění")
        self.chk_notify.setChecked(self.config.get("show_notifications", True))
        layout.addWidget(self.chk_notify)

        hint = QLabel(
            "Windows Scan Code backend používá SendInput se scan-code injekcí,\n"
            "což je kompatibilnější s hrami na DirectInput/RawInput. Souřadnice\n"
            "myši se počítají vůči primárnímu monitoru.\n\n"
            "PostMessage backend posílá vstup přímo do konkrétního okna (viz\n"
            "Cílové okno níže) bez potřeby fokusu. Funguje jen u klasických Win32\n"
            "aplikací zpracovávajících zprávy okna — u naprosté většiny her je\n"
            "k ničemu, protože ty čtou vstup přímo z hardwaru/DirectInputu a\n"
            "posílané zprávy okna úplně ignorují."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        section = QLabel("Cílové okno")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)

        window_row = QHBoxLayout()
        self.combo_window = QComboBox()
        self.combo_window.setEditable(True)
        self.combo_window.setInsertPolicy(QComboBox.NoInsert)
        window_row.addWidget(self.combo_window, 1)
        btn_refresh = QPushButton("Obnovit seznam")
        btn_refresh.clicked.connect(self._refresh_window_list)
        window_row.addWidget(btn_refresh)
        layout.addLayout(window_row)
        self._refresh_window_list()
        current_title = self.config.get("target_window_title", "")
        if current_title:
            idx = self.combo_window.findText(current_title)
            if idx >= 0:
                self.combo_window.setCurrentIndex(idx)
            else:
                self.combo_window.setEditText(current_title)

        process_row = QHBoxLayout()
        process_row.addWidget(QLabel("Proces:"))
        self.combo_process = QComboBox()
        self.combo_process.setEditable(True)
        self.combo_process.setInsertPolicy(QComboBox.NoInsert)
        process_row.addWidget(self.combo_process, 1)
        btn_refresh_process = QPushButton("Obnovit")
        btn_refresh_process.clicked.connect(self._refresh_process_list)
        process_row.addWidget(btn_refresh_process)
        layout.addLayout(process_row)
        self._refresh_process_list()
        current_process = self.config.get("target_process_name", "")
        if current_process:
            idx = self.combo_process.findText(current_process)
            if idx >= 0:
                self.combo_process.setCurrentIndex(idx)
            else:
                self.combo_process.setEditText(current_process)

        process_hint = QLabel(
            "Proces (např. metin2client.exe) je stabilnější cíl než titulek okna —\n"
            "ten se u her běžně mění (jméno postavy, mapa...). Když je vyplněný\n"
            "proces i okno, proces má přednost."
        )
        process_hint.setObjectName("hintLabel")
        process_hint.setWordWrap(True)
        layout.addWidget(process_hint)

        self.chk_window_enabled = QCheckBox("Omezit hotkeys jen na toto okno")
        self.chk_window_enabled.setChecked(self.config.get("target_window_enabled", False))
        layout.addWidget(self.chk_window_enabled)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Podmínka:"))
        self.combo_window_mode = QComboBox()
        self.combo_window_mode.addItem("Musí být aktivní (v popředí)", "foreground")
        self.combo_window_mode.addItem("Stačí, že běží (klidně na pozadí/minimalizované)", "running")
        idx = self.combo_window_mode.findData(self.config.get("target_window_mode", "foreground"))
        if idx >= 0:
            self.combo_window_mode.setCurrentIndex(idx)
        mode_row.addWidget(self.combo_window_mode, 1)
        layout.addLayout(mode_row)

        self.chk_window_autofocus = QCheckBox("Před přehráním makra aktivovat cílové okno")
        self.chk_window_autofocus.setChecked(self.config.get("target_window_autofocus", False))
        layout.addWidget(self.chk_window_autofocus)

        window_hint = QLabel(
            "Výběr okna funguje jen na Windows. Netýká se ovládání tlačítky přímo\n"
            "v aplikaci (klik vždy přebere fokus na WoofMC).\n\n"
            "\"Musí být aktivní\" — hotkey zafunguje jen když je okno přímo v popředí.\n"
            "\"Stačí, že běží\" — hotkey zafunguje i když je okno na pozadí/minimalizované;\n"
            "dává smysl hlavně s PostMessage backendem výše, protože ten posílá vstup\n"
            "přímo do okna bez potřeby fokusu — takže makro můžeš spustit hotkey,\n"
            "zatímco děláš cokoliv jiného, a ono doletí do cíle na pozadí.\n\n"
            "Auto-aktivace okna dává smysl jen s pynput/Scan Code backendem — s\n"
            "PostMessage backendem je zbytečná, protože ten fokus vůbec nepotřebuje."
        )
        window_hint.setObjectName("hintLabel")
        window_hint.setWordWrap(True)
        layout.addWidget(window_hint)

        if not window_utils.IS_WINDOWS:
            self.combo_window.setEnabled(False)
            btn_refresh.setEnabled(False)
            self.combo_process.setEnabled(False)
            btn_refresh_process.setEnabled(False)
            self.chk_window_enabled.setEnabled(False)
            self.combo_window_mode.setEnabled(False)
            self.chk_window_autofocus.setEnabled(False)
            self.combo_window.setToolTip("Dostupné jen na Windows")
            self.combo_process.setToolTip("Dostupné jen na Windows")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_window_list(self):
        current = self.combo_window.currentText()
        self.combo_window.clear()
        titles = [t for _hwnd, t in window_utils.list_windows()]
        self.combo_window.addItems(titles)
        if current:
            self.combo_window.setEditText(current)

    def _refresh_process_list(self):
        current = self.combo_process.currentText()
        self.combo_process.clear()
        self.combo_process.addItems(window_utils.list_process_names())
        if current:
            self.combo_process.setEditText(current)

    def _on_accept(self):
        hotkeys = {
            self.edit_hotkey_record.hotkey,
            self.edit_hotkey_play.hotkey,
            self.edit_hotkey_pause.hotkey,
            self.edit_hotkey_panic.hotkey,
        }
        if len(hotkeys) < 4:
            QMessageBox.warning(self, "Nastavení", "Hotkeys se nesmí opakovat.")
            return
        window_title = self.combo_window.currentText().strip()
        process_name = self.combo_process.currentText().strip()
        if self.chk_window_enabled.isChecked() and not window_title and not process_name:
            QMessageBox.warning(self, "Nastavení", "Vyplň cílové okno nebo proces.")
            return
        if self.combo_backend.currentData() == "postmessage" and not window_title and not process_name:
            QMessageBox.warning(
                self, "Nastavení",
                "PostMessage backend potřebuje vyplněné cílové okno nebo proces níže,"
                " i když zrovna nechceš omezovat hotkeys."
            )
            return
        self.accept()

    def result_config(self) -> dict:
        cfg = dict(self.config)
        cfg["hotkey_record"] = self.edit_hotkey_record.hotkey
        cfg["hotkey_play"] = self.edit_hotkey_play.hotkey
        cfg["hotkey_pause"] = self.edit_hotkey_pause.hotkey
        cfg["hotkey_panic"] = self.edit_hotkey_panic.hotkey
        cfg["input_backend"] = self.combo_backend.currentData()
        cfg["record_countdown"] = self.spin_countdown.value()
        cfg["start_minimized"] = self.chk_minimized.isChecked()
        cfg["close_to_tray"] = self.chk_tray.isChecked()
        cfg["show_notifications"] = self.chk_notify.isChecked()
        cfg["target_window_title"] = self.combo_window.currentText().strip()
        cfg["target_process_name"] = self.combo_process.currentText().strip()
        cfg["target_window_enabled"] = self.chk_window_enabled.isChecked()
        cfg["target_window_autofocus"] = self.chk_window_autofocus.isChecked()
        cfg["target_window_mode"] = self.combo_window_mode.currentData()
        return cfg


class EventEditDialog(QDialog):
    def __init__(self, event: MacroEvent, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Upravit událost")
        self.event = event

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_kind = QComboBox()
        self.combo_kind.addItems(sorted(VALID_KINDS))
        self.combo_kind.setCurrentText(event.kind)
        self.combo_kind.currentTextChanged.connect(self._on_kind_changed)
        form.addRow("Typ:", self.combo_kind)

        self.spin_t = QDoubleSpinBox()
        self.spin_t.setRange(0.0, 999999.0)
        self.spin_t.setDecimals(3)
        self.spin_t.setValue(event.t)
        form.addRow("Čas (s):", self.spin_t)

        self.spin_x = QSpinBox()
        self.spin_x.setRange(-10000, 10000)
        self.spin_x.setValue(event.data.get("x", 0))
        form.addRow("X:", self.spin_x)

        self.spin_y = QSpinBox()
        self.spin_y.setRange(-10000, 10000)
        self.spin_y.setValue(event.data.get("y", 0))
        form.addRow("Y:", self.spin_y)

        self.spin_dx = QSpinBox()
        self.spin_dx.setRange(-100, 100)
        self.spin_dx.setValue(event.data.get("dx", 0))
        form.addRow("Scroll dX:", self.spin_dx)

        self.spin_dy = QSpinBox()
        self.spin_dy.setRange(-100, 100)
        self.spin_dy.setValue(event.data.get("dy", 0))
        form.addRow("Scroll dY:", self.spin_dy)

        self.combo_button = QComboBox()
        self.combo_button.addItems(["left", "right", "middle"])
        self.combo_button.setCurrentText(event.data.get("button", "left"))
        form.addRow("Tlačítko myši:", self.combo_button)

        self.chk_pressed = QCheckBox("Stisk (jinak puštění)")
        self.chk_pressed.setChecked(bool(event.data.get("pressed", True)))
        form.addRow("", self.chk_pressed)

        self.edit_key = QLineEdit(event.data.get("key", "char:a").split(":", 1)[-1])
        form.addRow("Klávesa (znak):", self.edit_key)

        layout.addLayout(form)
        self._on_kind_changed(event.kind)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_kind_changed(self, kind: str):
        for w in (self.spin_x, self.spin_y):
            w.setEnabled(kind in ("move", "click", "scroll"))
        for w in (self.spin_dx, self.spin_dy):
            w.setEnabled(kind == "scroll")
        self.combo_button.setEnabled(kind == "click")
        self.chk_pressed.setEnabled(kind == "click")
        self.edit_key.setEnabled(kind in ("key_down", "key_up"))

    def result_event(self) -> MacroEvent:
        kind = self.combo_kind.currentText()
        if kind in ("move", "click", "scroll"):
            data = {"x": self.spin_x.value(), "y": self.spin_y.value()}
            if kind == "click":
                data["button"] = self.combo_button.currentText()
                data["pressed"] = self.chk_pressed.isChecked()
            if kind == "scroll":
                data["dx"] = self.spin_dx.value()
                data["dy"] = self.spin_dy.value()
        elif kind in ("key_down", "key_up"):
            char = self.edit_key.text().strip() or "a"
            data = {"key": f"char:{char}"}
        else:
            data = {}
        return MacroEvent(t=self.spin_t.value(), kind=kind, data=data, uid=self.event.uid)

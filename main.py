import os
import sys
import time
import traceback
from typing import Optional, Dict, Any, List

from PyQt5.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap, QPainter, QColor, QIcon, QBrush, QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QSpinBox, QDoubleSpinBox, QMessageBox, QInputDialog,
    QFileDialog, QMenu, QAction, QSystemTrayIcon, QStatusBar, QAbstractItemView,
    QHeaderView, QCheckBox, QTabWidget, QProgressBar, QComboBox, QLineEdit,
    QShortcut, QFrame
)
from pynput import keyboard as pynput_keyboard

import storage
import theme
import window_utils
import fx
from macro_engine import (
    MacroRecorder, MacroPlayer, MacroEvent, describe_event, KIND_LABEL,
    events_to_dicts, dicts_to_events, resequence_from_gaps, estimate_duration,
)
from dialogs import SettingsDialog, EventEditDialog, pretty_hotkey, HotkeyCaptureEdit
from input_backend import available_backends, BACKEND_LABELS

APP_NAME = "STW WoofMC"
VERSION = "2.0.0"

STATE_IDLE = "#6b3fa0"
STATE_RECORDING = "#e74c3c"
STATE_PLAYING = "#2ecc71"
STATE_PAUSED = "#e8b923"


def make_app_icon(color: str = STATE_IDLE) -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(4, 4, 56, 56)
    p.setBrush(QBrush(QColor("#e6e1f0")))
    p.drawEllipse(22, 22, 20, 20)
    p.end()
    return QIcon(pix)


class HotkeyBridge(QObject):
    toggle_record = pyqtSignal()
    toggle_play = pyqtSignal()
    toggle_pause = pyqtSignal()
    play_macro_requested = pyqtSignal(str)
    panic = pyqtSignal()


def _install_exception_hook(app: QApplication):
    def hook(exctype, value, tb):
        storage.ensure_dir()
        log_path = os.path.join(storage.DATA_DIR, "crash.log")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("".join(traceback.format_exception(exctype, value, tb)))
                f.write("\n---\n")
        except OSError:
            pass
        QMessageBox.critical(
            None, APP_NAME,
            f"Nastala neočekávaná chyba:\n{value}\n\nZáznam uložen do:\n{log_path}"
        )
    sys.excepthook = hook


class MainWindow(QMainWindow):
    event_recorded = pyqtSignal(object)
    playback_progress = pyqtSignal(int, int)
    playback_finished = pyqtSignal()
    playback_loop = pyqtSignal(int, int)
    playback_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(1180, 680)
        self.setWindowIcon(make_app_icon())

        self.config = storage.load_config()
        self.macros: Dict[str, Any] = storage.load_macros()
        self.playlists: Dict[str, Any] = storage.load_playlists()
        self.current_name: Optional[str] = None
        self.current_events: List[MacroEvent] = []

        self._playlist_entries: List[dict] = []
        self._playlist_pos = 0
        self._playlist_running = False

        self._undo_stack: List[List[MacroEvent]] = []
        self._live_events: List[MacroEvent] = []
        self._last_timeline_update = 0.0

        self.recorder = MacroRecorder()
        self.recorder.on_event = lambda ev: self.event_recorded.emit(ev)
        self.player = MacroPlayer(
            on_finished=lambda: self.playback_finished.emit(),
            on_progress=lambda i, n: self.playback_progress.emit(i, n),
            on_loop=lambda c, n: self.playback_loop.emit(c, n),
            on_error=lambda msg: self.playback_error.emit(msg),
        )
        self.player.backend_id = self.config.get("input_backend", "pynput")
        self.player.target_window_title = self.config.get("target_window_title", "")
        self.player.target_process_name = self.config.get("target_process_name", "")

        self.event_recorded.connect(self._on_event_recorded)
        self.playback_progress.connect(self._on_playback_progress)
        self.playback_finished.connect(self._on_playback_finished)
        self.playback_loop.connect(self._on_playback_loop)
        self.playback_error.connect(self._on_playback_error)

        self._build_ui()
        self._build_menu()
        self._build_tray()
        self._reload_macro_list()
        self._reload_playlist_combo()
        self._refresh_macro_window_combo()
        self._refresh_macro_process_combo()

        self.bridge = HotkeyBridge()
        self.bridge.toggle_record.connect(self._toggle_record_hotkey)
        self.bridge.toggle_play.connect(self._toggle_play_hotkey)
        self.bridge.toggle_pause.connect(self._toggle_pause_hotkey)
        self.bridge.play_macro_requested.connect(self._play_macro_by_name)
        self.bridge.panic.connect(self._panic_stop)
        self._hotkeys = None
        self._register_hotkeys()

        self._undo_shortcut = QShortcut(QKeySequence.Undo, self)
        self._undo_shortcut.activated.connect(self._undo)

        self._save_shortcut = QShortcut(QKeySequence.Save, self)
        self._save_shortcut.activated.connect(self._save_current_macro)

        if self.config.get("start_minimized", False):
            QTimer.singleShot(0, self.hide)

    # ---------- hotkeys ----------

    def _register_hotkeys(self):
        if self._hotkeys:
            try:
                self._hotkeys.stop()
            except Exception:
                pass
            self._hotkeys = None

        mapping = {}
        used = {}
        conflicts = []

        def _add(hk: str, callback, label: str):
            if not hk:
                return
            if hk in used:
                conflicts.append(f"{label} vs {used[hk]}")
                return
            mapping[hk] = callback
            used[hk] = label

        _add(self.config.get("hotkey_record", ""), lambda: self.bridge.toggle_record.emit(), "Nahrávání")
        _add(self.config.get("hotkey_play", ""), lambda: self.bridge.toggle_play.emit(), "Přehrávání")
        _add(self.config.get("hotkey_pause", ""), lambda: self.bridge.toggle_pause.emit(), "Pauza")
        _add(self.config.get("hotkey_panic", ""), lambda: self.bridge.panic.emit(), "PANIC STOP")
        for name in sorted(self.macros.keys()):
            hk = self.macros[name].get("hotkey", "")
            _add(hk, (lambda n=name: self.bridge.play_macro_requested.emit(n)), f"Makro '{name}'")

        try:
            self._hotkeys = pynput_keyboard.GlobalHotKeys(mapping)
            self._hotkeys.start()
            msg = (
                f"Hotkeys: nahrávání {pretty_hotkey(self.config.get('hotkey_record', ''))}  "
                f"přehrávání {pretty_hotkey(self.config.get('hotkey_play', ''))}  "
                f"pauza {pretty_hotkey(self.config.get('hotkey_pause', ''))}"
            )
            if self.config.get("hotkey_panic"):
                msg += f"  panic {pretty_hotkey(self.config['hotkey_panic'])}"
            target_desc = self.config.get("target_process_name") or self.config.get("target_window_title")
            if self.config.get("target_window_enabled") and target_desc:
                mode_label = "na pozadí" if self.config.get("target_window_mode") == "running" else "v popředí"
                msg += f"  |  omezeno na cíl ({mode_label}): {target_desc}"
            if conflicts:
                msg += f"  |  KOLIZE (ignorováno): {'; '.join(conflicts)}"
            self.status_bar.showMessage(msg)
        except Exception as e:
            self.status_bar.showMessage(
                f"Globální hotkeys se nepodařilo zaregistrovat ({e}). Ovládej tlačítky v okně."
            )

    # ---------- UI construction ----------

    def _build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_tabs())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 880])
        self.setCentralWidget(central)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _build_left_panel(self) -> QWidget:
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setSpacing(theme.SPACING["sm"])
        left_l.setContentsMargins(0, 0, 0, 0)

        left_l.addWidget(QLabel("Uložené makra"))

        card = QFrame()
        card.setObjectName("card")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(
            theme.SPACING["sm"], theme.SPACING["sm"], theme.SPACING["sm"], theme.SPACING["sm"]
        )
        card_l.setSpacing(theme.SPACING["xs"])

        self.search_box = QLineEdit()
        self.search_box.setObjectName("searchBox")
        self.search_box.setPlaceholderText("Hledat makro...")
        self.search_box.textChanged.connect(self._filter_macro_list)
        card_l.addWidget(self.search_box)

        self.macro_list = QListWidget()
        self.macro_list.currentItemChanged.connect(self._on_select_macro)
        card_l.addWidget(self.macro_list)

        shadow = fx.make_glow("#000000", blur=22)
        shadow.setColor(QColor(0, 0, 0, 130))
        card.setGraphicsEffect(shadow)
        left_l.addWidget(card, 1)

        row1 = QHBoxLayout()
        btn_new = QPushButton("Nové")
        btn_new.clicked.connect(self._new_macro)
        btn_dup = QPushButton("Duplikovat")
        btn_dup.clicked.connect(self._duplicate_macro)
        row1.addWidget(btn_new)
        row1.addWidget(btn_dup)
        left_l.addLayout(row1)

        row2 = QHBoxLayout()
        btn_rename = QPushButton("Přejmenovat")
        btn_rename.clicked.connect(self._rename_macro)
        btn_del = QPushButton("Smazat")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_macro)
        row2.addWidget(btn_rename)
        row2.addWidget(btn_del)
        left_l.addLayout(row2)

        row3 = QHBoxLayout()
        btn_imp = QPushButton("Import")
        btn_imp.clicked.connect(self._import_macro)
        btn_exp = QPushButton("Export")
        btn_exp.clicked.connect(self._export_macro)
        row3.addWidget(btn_imp)
        row3.addWidget(btn_exp)
        left_l.addLayout(row3)

        self.stats_chip = QLabel("Vyber makro")
        self.stats_chip.setObjectName("statsChip")
        self.stats_chip.setAlignment(Qt.AlignCenter)
        left_l.addWidget(self.stats_chip)

        self.macro_info_label = QLabel("")
        self.macro_info_label.setObjectName("hintLabel")
        self.macro_info_label.setWordWrap(True)
        left_l.addWidget(self.macro_info_label)

        left.setMaximumWidth(300)
        return left

    def _build_right_tabs(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(self._build_editor_tab(), "Editor makra")
        tabs.addTab(self._build_playlist_tab(), "Playlist")
        return tabs

    def _build_editor_tab(self) -> QWidget:
        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setSpacing(theme.SPACING["sm"])
        right_l.setContentsMargins(
            theme.SPACING["md"], theme.SPACING["md"], theme.SPACING["md"], theme.SPACING["md"]
        )

        toolbar = QHBoxLayout()
        toolbar.setSpacing(theme.SPACING["sm"])
        self.btn_record = QPushButton("● Nahrávat")
        self.btn_record.setObjectName("recordBtn")
        self.btn_record.setCheckable(True)
        self.btn_record.clicked.connect(self._on_record_clicked)
        toolbar.addWidget(self.btn_record)

        self.btn_play = QPushButton("▶ Přehrát")
        self.btn_play.setObjectName("playBtn")
        self.btn_play.setCheckable(True)
        self.btn_play.clicked.connect(self._on_play_clicked)
        toolbar.addWidget(self.btn_play)

        self.btn_pause = QPushButton("❚❚ Pauza")
        self.btn_pause.setObjectName("pauseBtn")
        self.btn_pause.setCheckable(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._on_pause_clicked)
        toolbar.addWidget(self.btn_pause)

        self.btn_save = QPushButton("Uložit makro")
        self.btn_save.setObjectName("primaryBtn")
        self.btn_save.clicked.connect(self._save_current_macro)
        toolbar.addWidget(self.btn_save)

        self.btn_clear = QPushButton("Vymazat")
        self.btn_clear.clicked.connect(self._clear_events)
        toolbar.addWidget(self.btn_clear)

        self.btn_undo = QPushButton("↶ Zpět")
        self.btn_undo.clicked.connect(self._undo)
        toolbar.addWidget(self.btn_undo)
        toolbar.addStretch()
        right_l.addLayout(toolbar)

        opts = QHBoxLayout()
        opts.addWidget(QLabel("Opakování (0=nekonečno):"))
        self.spin_loops = QSpinBox()
        self.spin_loops.setRange(0, 100000)
        self.spin_loops.setValue(1)
        opts.addWidget(self.spin_loops)

        opts.addWidget(QLabel("Rychlost:"))
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.05, 20.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.setValue(1.0)
        opts.addWidget(self.spin_speed)

        opts.addWidget(QLabel("Jitter (ms):"))
        self.spin_jitter = QSpinBox()
        self.spin_jitter.setRange(0, 2000)
        self.spin_jitter.setValue(0)
        opts.addWidget(self.spin_jitter)

        opts.addWidget(QLabel("Start delay (s):"))
        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.0, 60.0)
        self.spin_delay.setSingleStep(0.5)
        self.spin_delay.setValue(2.0)
        opts.addWidget(self.spin_delay)
        opts.addStretch()
        right_l.addLayout(opts)

        opts2 = QHBoxLayout()
        self.chk_record_move = QCheckBox("Zaznamenávat pohyb myši")
        self.chk_record_move.setChecked(True)
        self.chk_record_move.stateChanged.connect(self._on_move_toggle)
        opts2.addWidget(self.chk_record_move)

        self.chk_record_scroll = QCheckBox("Zaznamenávat kolečko")
        self.chk_record_scroll.setChecked(True)
        self.chk_record_scroll.stateChanged.connect(self._on_scroll_toggle)
        opts2.addWidget(self.chk_record_scroll)
        opts2.addStretch()
        right_l.addLayout(opts2)

        target_card = QFrame()
        target_card.setObjectName("card")
        target_l = QVBoxLayout(target_card)
        target_l.setContentsMargins(
            theme.SPACING["sm"], theme.SPACING["sm"], theme.SPACING["sm"], theme.SPACING["sm"]
        )
        target_l.setSpacing(theme.SPACING["xs"])

        target_label = QLabel("Cíl makra (prázdné = použije se globální nastavení)")
        target_label.setObjectName("sectionLabel")
        target_l.addWidget(target_label)

        target_row1 = QHBoxLayout()
        target_row1.addWidget(QLabel("Backend:"))
        self.combo_macro_backend = QComboBox()
        self.combo_macro_backend.addItem("(globální)", "")
        for b in available_backends():
            self.combo_macro_backend.addItem(BACKEND_LABELS.get(b, b), b)
        target_row1.addWidget(self.combo_macro_backend, 1)
        target_l.addLayout(target_row1)

        target_row2 = QHBoxLayout()
        target_row2.addWidget(QLabel("Okno:"))
        self.combo_macro_window = QComboBox()
        self.combo_macro_window.setEditable(True)
        self.combo_macro_window.setInsertPolicy(QComboBox.NoInsert)
        target_row2.addWidget(self.combo_macro_window, 1)
        btn_refresh_macro_window = QPushButton("↻")
        btn_refresh_macro_window.setToolTip("Obnovit seznam oken")
        btn_refresh_macro_window.clicked.connect(self._refresh_macro_window_combo)
        target_row2.addWidget(btn_refresh_macro_window)
        target_l.addLayout(target_row2)

        target_row3 = QHBoxLayout()
        target_row3.addWidget(QLabel("Proces:"))
        self.combo_macro_process = QComboBox()
        self.combo_macro_process.setEditable(True)
        self.combo_macro_process.setInsertPolicy(QComboBox.NoInsert)
        target_row3.addWidget(self.combo_macro_process, 1)
        btn_refresh_macro_process = QPushButton("↻")
        btn_refresh_macro_process.setToolTip("Obnovit seznam procesů")
        btn_refresh_macro_process.clicked.connect(self._refresh_macro_process_combo)
        target_row3.addWidget(btn_refresh_macro_process)
        target_l.addLayout(target_row3)

        target_row4 = QHBoxLayout()
        target_row4.addWidget(QLabel("Hotkey makra:"))
        self.macro_hotkey_edit = HotkeyCaptureEdit("")
        target_row4.addWidget(self.macro_hotkey_edit, 1)
        btn_clear_macro_hotkey = QPushButton("Vymazat")
        btn_clear_macro_hotkey.clicked.connect(self._clear_macro_hotkey)
        target_row4.addWidget(btn_clear_macro_hotkey)
        target_l.addLayout(target_row4)

        target_hint = QLabel(
            "Hotkey makra spustí přímo TOHLE makro, i když je zrovna vybrané jiné,"
            " a funguje i s hlavním oknem schovaným na pozadí."
        )
        target_hint.setObjectName("hintLabel")
        target_hint.setWordWrap(True)
        target_l.addWidget(target_hint)

        if not window_utils.IS_WINDOWS:
            self.combo_macro_window.setEnabled(False)
            self.combo_macro_process.setEnabled(False)
            btn_refresh_macro_window.setEnabled(False)
            btn_refresh_macro_process.setEnabled(False)

        right_l.addWidget(target_card)

        table_card = QFrame()
        table_card.setObjectName("card")
        table_card_l = QVBoxLayout(table_card)
        table_card_l.setContentsMargins(
            theme.SPACING["sm"], theme.SPACING["sm"], theme.SPACING["sm"], theme.SPACING["sm"]
        )
        table_card_l.setSpacing(theme.SPACING["xs"])

        self.timeline = fx.TimelineWidget()
        table_card_l.addWidget(self.timeline)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Typ", "Čas (s)", "Detail"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_context_menu)
        self.table.setDragDropMode(QAbstractItemView.InternalMove)
        self.table.setDragDropOverwriteMode(False)
        self.table.model().rowsMoved.connect(self._on_rows_moved)
        self.table.doubleClicked.connect(self._on_table_double_click)
        table_card_l.addWidget(self.table)

        shadow = fx.make_glow("#000000", blur=22)
        shadow.setColor(QColor(0, 0, 0, 130))
        table_card.setGraphicsEffect(shadow)
        right_l.addWidget(table_card, 1)

        self._delete_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self.table)
        self._delete_shortcut.setContext(Qt.WidgetShortcut)
        self._delete_shortcut.activated.connect(self._shortcut_delete_rows)

        self._dup_shortcut = QShortcut(QKeySequence("Ctrl+D"), self.table)
        self._dup_shortcut.setContext(Qt.WidgetShortcut)
        self._dup_shortcut.activated.connect(self._shortcut_duplicate_rows)

        bottom = QHBoxLayout()
        self.status_orb = fx.StatusOrb()
        bottom.addWidget(self.status_orb)
        self.status_label = QLabel("Připraveno")
        self.status_label.setObjectName("statusLabel")
        bottom.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(220)
        bottom.addStretch()
        bottom.addWidget(self.progress_bar)
        right_l.addLayout(bottom)

        fx.attach_pulsing_glow(self.btn_record, "#e74c3c")
        fx.attach_pulsing_glow(self.btn_play, "#2ecc71")
        fx.attach_pulsing_glow(self.btn_pause, "#e8b923")
        fx.attach_static_glow(self.btn_save, "#8a5cd0", blur=14)

        return right

    def _build_playlist_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        row = QHBoxLayout()
        row.addWidget(QLabel("Playlist:"))
        self.combo_playlist = QComboBox()
        self.combo_playlist.currentTextChanged.connect(self._on_playlist_selected)
        row.addWidget(self.combo_playlist, 1)
        btn_new_pl = QPushButton("Nový")
        btn_new_pl.clicked.connect(self._new_playlist)
        row.addWidget(btn_new_pl)
        btn_del_pl = QPushButton("Smazat")
        btn_del_pl.setObjectName("dangerBtn")
        btn_del_pl.clicked.connect(self._delete_playlist)
        row.addWidget(btn_del_pl)
        layout.addLayout(row)

        self.playlist_list = QListWidget()
        layout.addWidget(self.playlist_list)

        controls = QHBoxLayout()
        btn_add = QPushButton("+ Přidat vybrané makro")
        btn_add.clicked.connect(self._playlist_add_selected_macro)
        controls.addWidget(btn_add)
        btn_up = QPushButton("↑")
        btn_up.clicked.connect(lambda: self._playlist_move(-1))
        controls.addWidget(btn_up)
        btn_down = QPushButton("↓")
        btn_down.clicked.connect(lambda: self._playlist_move(1))
        controls.addWidget(btn_down)
        btn_remove = QPushButton("Odebrat")
        btn_remove.clicked.connect(self._playlist_remove_selected)
        controls.addWidget(btn_remove)
        controls.addStretch()
        layout.addLayout(controls)

        opts = QHBoxLayout()
        opts.addWidget(QLabel("Opakování vybraného kroku:"))
        self.spin_playlist_repeat = QSpinBox()
        self.spin_playlist_repeat.setRange(1, 100000)
        self.spin_playlist_repeat.setValue(1)
        self.spin_playlist_repeat.valueChanged.connect(self._playlist_update_repeat)
        opts.addWidget(self.spin_playlist_repeat)

        opts.addWidget(QLabel("Prodleva mezi kroky (s):"))
        self.spin_playlist_delay = QDoubleSpinBox()
        self.spin_playlist_delay.setRange(0.0, 60.0)
        self.spin_playlist_delay.setSingleStep(0.5)
        self.spin_playlist_delay.setValue(1.0)
        opts.addWidget(self.spin_playlist_delay)
        opts.addStretch()
        layout.addLayout(opts)

        run_row = QHBoxLayout()
        self.btn_playlist_run = QPushButton("▶ Spustit playlist")
        self.btn_playlist_run.setObjectName("primaryBtn")
        self.btn_playlist_run.clicked.connect(self._start_playlist)
        run_row.addWidget(self.btn_playlist_run)
        fx.attach_static_glow(self.btn_playlist_run, "#8a5cd0", blur=14)
        self.btn_playlist_stop = QPushButton("■ Zastavit")
        self.btn_playlist_stop.setEnabled(False)
        self.btn_playlist_stop.clicked.connect(self._stop_playlist)
        run_row.addWidget(self.btn_playlist_stop)
        btn_save_pl = QPushButton("Uložit playlist")
        btn_save_pl.clicked.connect(self._save_playlist)
        run_row.addWidget(btn_save_pl)
        run_row.addStretch()
        layout.addLayout(run_row)

        self.playlist_status = QLabel("Playlist připraven")
        self.playlist_status.setObjectName("statusLabel")
        layout.addWidget(self.playlist_status)

        return widget

    def _build_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("Soubor")

        act_new = QAction("Nové makro", self)
        act_new.triggered.connect(self._new_macro)
        file_menu.addAction(act_new)

        act_import = QAction("Import makra...", self)
        act_import.triggered.connect(self._import_macro)
        file_menu.addAction(act_import)

        act_export = QAction("Export makra...", self)
        act_export.triggered.connect(self._export_macro)
        file_menu.addAction(act_export)

        file_menu.addSeparator()

        act_backup = QAction("Zálohovat vše...", self)
        act_backup.triggered.connect(self._backup_all)
        file_menu.addAction(act_backup)

        act_restore = QAction("Obnovit ze zálohy...", self)
        act_restore.triggered.connect(self._restore_all)
        file_menu.addAction(act_restore)

        file_menu.addSeparator()
        act_quit = QAction("Konec", self)
        act_quit.triggered.connect(self._force_quit)
        file_menu.addAction(act_quit)

        settings_menu = menu.addMenu("Nastavení")
        act_settings = QAction("Otevřít nastavení...", self)
        act_settings.triggered.connect(self._open_settings)
        settings_menu.addAction(act_settings)

        help_menu = menu.addMenu("Nápověda")
        act_about = QAction("O aplikaci", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_app_icon(), self)
        tray_menu = QMenu()
        act_show = tray_menu.addAction("Zobrazit")
        act_show.triggered.connect(self.showNormal)
        act_quit = tray_menu.addAction("Konec")
        act_quit.triggered.connect(self._force_quit)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(
            lambda reason: self.showNormal() if reason == QSystemTrayIcon.DoubleClick else None
        )
        self.tray.show()

    def _notify(self, message: str):
        if self.config.get("show_notifications", True):
            self.tray.showMessage(APP_NAME, message, QSystemTrayIcon.Information, 2000)

    def _set_tray_state(self, color: str):
        self.tray.setIcon(make_app_icon(color))

    # ---------- settings ----------

    def _resolve_target(self, macro: Optional[dict]) -> tuple:
        """Vrátí (backend_id, titulek okna, proces) — přednost mají hodnoty
        uložené přímo v makru, jinak se použije globální nastavení."""
        macro = macro or {}
        backend_id = macro.get("input_backend_override") or self.config.get("input_backend", "pynput")
        title = macro.get("target_window_title") or self.config.get("target_window_title", "")
        process = macro.get("target_process_name") or self.config.get("target_process_name", "")
        return backend_id, title, process

    def _hotkey_target_ok(self, macro: Optional[dict] = None) -> bool:
        if not self.config.get("target_window_enabled", False):
            return True
        if macro is None:
            macro = self.macros.get(self.current_name) if self.current_name else None
        _backend, title, process = self._resolve_target(macro)
        if not title and not process:
            return True
        if not window_utils.IS_WINDOWS:
            return True
        mode = self.config.get("target_window_mode", "foreground")
        if mode == "running":
            ok = window_utils.is_target_running(title, process)
            reason = "neběží"
        else:
            ok = window_utils.is_target_foreground(title, process)
            reason = "není aktivní"
        if not ok:
            desc = process or title
            self.status_bar.showMessage(f"Cíl '{desc}' {reason}, hotkey ignorován.", 3000)
        return ok

    def _maybe_autofocus_target(self, title: str = "", process: str = ""):
        if not self.config.get("target_window_autofocus", False):
            return
        if not window_utils.IS_WINDOWS:
            return
        if title or process:
            window_utils.focus_target(title, process)

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec_():
            self.config = dlg.result_config()
            storage.save_config(self.config)
            self.player.backend_id = self.config.get("input_backend", "pynput")
            self.player.target_window_title = self.config.get("target_window_title", "")
            self.player.target_process_name = self.config.get("target_process_name", "")
            self._register_hotkeys()

    # ---------- macro list management ----------

    def _reload_macro_list(self):
        self.macro_list.blockSignals(True)
        self.macro_list.clear()
        for name in sorted(self.macros.keys()):
            macro = self.macros[name]
            n_events = len(macro.get("events", []))
            label = f"{name}   ·  {n_events} ev."
            hotkey = macro.get("hotkey", "")
            if hotkey:
                label += f"   ·  {pretty_hotkey(hotkey)}"
            target = macro.get("target_process_name") or macro.get("target_window_title")
            if target:
                label += f"   ·  → {target}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, name)
            self.macro_list.addItem(item)
        self.macro_list.blockSignals(False)
        self._filter_macro_list(self.search_box.text() if hasattr(self, "search_box") else "")

    def _filter_macro_list(self, text: str):
        text = text.lower().strip()
        for i in range(self.macro_list.count()):
            item = self.macro_list.item(i)
            name = item.data(Qt.UserRole) or item.text()
            item.setHidden(bool(text) and text not in name.lower())

    def _on_select_macro(self, current: QListWidgetItem, previous: QListWidgetItem):
        if self.recorder.is_recording or self.player.is_playing():
            return
        if current is None:
            return
        name = current.data(Qt.UserRole)
        if name:
            self._load_macro(name)

    def _refresh_macro_window_combo(self):
        current = self.combo_macro_window.currentText()
        self.combo_macro_window.clear()
        self.combo_macro_window.addItem("(globální)", "")
        titles = [t for _hwnd, t in window_utils.list_windows()]
        self.combo_macro_window.addItems(titles)
        self.combo_macro_window.setEditText(current)

    def _refresh_macro_process_combo(self):
        current = self.combo_macro_process.currentText()
        self.combo_macro_process.clear()
        self.combo_macro_process.addItem("(globální)", "")
        self.combo_macro_process.addItems(window_utils.list_process_names())
        self.combo_macro_process.setEditText(current)

    def _clear_macro_hotkey(self):
        self.macro_hotkey_edit.hotkey = ""
        self.macro_hotkey_edit.setText("")

    def _load_macro(self, name: str):
        macro = self.macros.get(name)
        if macro is None:
            return
        self.current_name = name
        self.current_events = dicts_to_events(macro.get("events", []))
        self._undo_stack = []
        self.spin_loops.setValue(macro.get("loops", 1))
        self.spin_speed.setValue(macro.get("speed", 1.0))
        self.spin_jitter.setValue(macro.get("jitter", 0))
        self.spin_delay.setValue(macro.get("start_delay", 2.0))

        backend_override = macro.get("input_backend_override", "")
        idx = self.combo_macro_backend.findData(backend_override)
        self.combo_macro_backend.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_macro_window.setEditText(macro.get("target_window_title", ""))
        self.combo_macro_process.setEditText(macro.get("target_process_name", ""))
        macro_hotkey = macro.get("hotkey", "")
        self.macro_hotkey_edit.hotkey = macro_hotkey
        self.macro_hotkey_edit.setText(pretty_hotkey(macro_hotkey))

        self._refresh_table()
        self._update_stats()
        self.status_label.setText(f"Načteno: {name} ({len(self.current_events)} událostí)")
        created = time.strftime("%d.%m.%Y %H:%M", time.localtime(macro.get("created", 0))) if macro.get("created") else "?"
        modified = time.strftime("%d.%m.%Y %H:%M", time.localtime(macro.get("modified", 0))) if macro.get("modified") else "?"
        run_count = macro.get("run_count", 0)
        self.macro_info_label.setText(
            f"Vytvořeno: {created}   ·   Upraveno: {modified}   ·   Spuštěno: {run_count}×"
        )

    def _new_macro(self):
        name, ok = QInputDialog.getText(self, "Nové makro", "Název makra:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.macros:
            QMessageBox.warning(self, APP_NAME, "Makro s tímto názvem už existuje.")
            return
        self.macros[name] = storage.new_macro_dict()
        storage.save_macros(self.macros)
        self._reload_macro_list()
        self._select_macro_by_name(name)

    def _duplicate_macro(self):
        if self.current_name is None:
            QMessageBox.information(self, APP_NAME, "Nejprve vyber makro.")
            return
        base = self.current_name
        new_name, i = f"{base}_copy", 1
        while new_name in self.macros:
            i += 1
            new_name = f"{base}_copy{i}"
        self.macros[new_name] = self._current_macro_dict()
        storage.save_macros(self.macros)
        self._reload_macro_list()
        self._select_macro_by_name(new_name)

    def _select_macro_by_name(self, name: str):
        for i in range(self.macro_list.count()):
            item = self.macro_list.item(i)
            if item.data(Qt.UserRole) == name:
                self.macro_list.setCurrentItem(item)
                return

    def _rename_macro(self):
        if self.current_name is None:
            return
        new_name, ok = QInputDialog.getText(self, "Přejmenovat makro", "Nový název:", text=self.current_name)
        if not ok or not new_name.strip() or new_name == self.current_name:
            return
        new_name = new_name.strip()
        if new_name in self.macros:
            QMessageBox.warning(self, APP_NAME, "Makro s tímto názvem už existuje.")
            return
        self.macros[new_name] = self.macros.pop(self.current_name)
        self.current_name = new_name
        storage.save_macros(self.macros)
        self._reload_macro_list()
        self._select_macro_by_name(new_name)

    def _delete_macro(self):
        if self.current_name is None:
            return
        reply = QMessageBox.question(self, APP_NAME, f"Smazat makro '{self.current_name}'?")
        if reply != QMessageBox.Yes:
            return
        self.macros.pop(self.current_name, None)
        storage.save_macros(self.macros)
        self.current_name = None
        self.current_events = []
        self._refresh_table()
        self._update_stats()
        self.macro_info_label.setText("")
        self._reload_macro_list()
        self._register_hotkeys()

    def _import_macro(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import makra", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = storage.import_macro(path)
            name = os.path.splitext(os.path.basename(path))[0]
            base_name, i = name, 1
            while name in self.macros:
                name = f"{base_name}_{i}"
                i += 1
            conflict = self._macro_hotkey_conflict(data.get("hotkey", ""), exclude_name=None)
            if conflict:
                data["hotkey"] = ""
            self.macros[name] = data
            storage.save_macros(self.macros)
            self._reload_macro_list()
            self._register_hotkeys()
            if conflict:
                QMessageBox.information(
                    self, APP_NAME,
                    f"Makro bylo importováno, ale jeho hotkey kolidoval s {conflict} — hotkey byl vymazán."
                )
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Import selhal: {e}")

    def _export_macro(self):
        if self.current_name is None:
            QMessageBox.warning(self, APP_NAME, "Nejprve vyber makro.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export makra", f"{self.current_name}.json", "JSON (*.json)")
        if not path:
            return
        try:
            storage.export_macro(path, self._current_macro_dict())
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Export selhal: {e}")

    def _backup_all(self):
        path, _ = QFileDialog.getSaveFileName(self, "Zálohovat vše", "woofmc_backup.json", "JSON (*.json)")
        if not path:
            return
        try:
            storage.export_backup(path, self.macros, self.playlists, self.config)
            QMessageBox.information(self, APP_NAME, "Záloha vytvořena.")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Záloha selhala: {e}")

    def _restore_all(self):
        path, _ = QFileDialog.getOpenFileName(self, "Obnovit ze zálohy", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = storage.import_backup(path)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Obnovení selhalo: {e}")
            return
        reply = QMessageBox.question(
            self, APP_NAME,
            "Obnovení přepíše aktuální makra, playlisty a nastavení. Pokračovat?"
        )
        if reply != QMessageBox.Yes:
            return
        self.macros = data.get("macros", {})
        self.playlists = data.get("playlists", {})
        self.config = {**storage.DEFAULT_CONFIG, **data.get("config", {})}
        storage.save_macros(self.macros)
        storage.save_playlists(self.playlists)
        storage.save_config(self.config)
        self.player.backend_id = self.config.get("input_backend", "pynput")
        self.player.target_window_title = self.config.get("target_window_title", "")
        self.player.target_process_name = self.config.get("target_process_name", "")
        self._register_hotkeys()
        self._reload_macro_list()
        self._reload_playlist_combo()
        QMessageBox.information(self, APP_NAME, "Záloha obnovena.")

    # ---------- recording ----------

    def _on_move_toggle(self, state):
        self.recorder.record_mouse_move = state == Qt.Checked

    def _on_scroll_toggle(self, state):
        self.recorder.record_scroll = state == Qt.Checked

    def _on_record_clicked(self, checked: bool):
        if checked:
            if self.player.is_playing():
                self.btn_record.setChecked(False)
                return
            countdown = self.config.get("record_countdown", 0.0)
            self.btn_record.setEnabled(False)
            self.status_label.setText(f"Nahrávání začne za {countdown:.1f}s..." if countdown else "Nahrávání...")
            QTimer.singleShot(int(countdown * 1000), self._begin_recording)
        else:
            events = self.recorder.stop()
            self.current_events = events
            self.btn_record.setText("● Nahrávat")
            self.btn_play.setEnabled(True)
            fx.stop_glow_pulse(self.btn_record)
            self.status_orb.set_state_color(STATE_IDLE)
            self._set_tray_state(STATE_IDLE)
            self.status_label.setText(f"Nahráno {len(events)} událostí")
            self._refresh_table()
            self._update_stats()

    def _begin_recording(self):
        self.current_events = []
        self._live_events = []
        self._undo_stack = []
        self._last_timeline_update = 0.0
        self._refresh_table()
        self.timeline.set_events([])
        self.recorder.start()
        self.btn_record.setEnabled(True)
        self.btn_record.setText("■ Zastavit")
        self.btn_play.setEnabled(False)
        fx.start_glow_pulse(self.btn_record)
        self.status_orb.set_state_color(STATE_RECORDING)
        self._set_tray_state(STATE_RECORDING)
        self.status_label.setText("Nahrávání...")

    def _toggle_record_hotkey(self):
        if self.player.is_playing():
            return
        if not self._hotkey_target_ok():
            return
        self.btn_record.setChecked(not self.btn_record.isChecked())
        self._on_record_clicked(self.btn_record.isChecked())

    def _on_event_recorded(self, ev: MacroEvent):
        self._append_table_row(ev)
        self._live_events.append(ev)
        now = time.monotonic()
        if now - self._last_timeline_update >= 0.1:
            self._last_timeline_update = now
            self.timeline.set_events(self._live_events)
        self.status_label.setText(f"Nahrávání... {self.table.rowCount()} událostí")

    # ---------- playback ----------

    def _on_play_clicked(self, checked: bool):
        if checked:
            if self.recorder.is_recording or not self.current_events:
                self.btn_play.setChecked(False)
                if not self.current_events:
                    QMessageBox.information(self, APP_NAME, "Žádné události k přehrání.")
                return
            self.btn_record.setEnabled(False)
            self.btn_play.setText("■ Zastavit")
            self.btn_pause.setEnabled(True)
            self.progress_bar.setValue(0)
            fx.start_glow_pulse(self.btn_play)
            self.status_orb.set_state_color(STATE_PLAYING)
            self._set_tray_state(STATE_PLAYING)
            self.status_label.setText("Přehrávání...")
            macro = self.macros.get(self.current_name) if self.current_name else None
            if self.current_name and macro is not None:
                macro["run_count"] = macro.get("run_count", 0) + 1
                storage.save_macros(self.macros)
            backend_id, title, process = self._resolve_target(macro)
            self.player.backend_id = backend_id
            self.player.target_window_title = title
            self.player.target_process_name = process
            self._maybe_autofocus_target(title, process)
            self.player.play(
                self.current_events,
                loops=self.spin_loops.value(),
                speed=self.spin_speed.value(),
                jitter_ms=self.spin_jitter.value(),
                start_delay=self.spin_delay.value(),
            )
        else:
            self.player.stop()

    def _toggle_play_hotkey(self):
        if self.recorder.is_recording:
            return
        if not self._hotkey_target_ok():
            return
        self.btn_play.setChecked(not self.btn_play.isChecked())
        self._on_play_clicked(self.btn_play.isChecked())

    def _on_pause_clicked(self, checked: bool):
        if not self.player.is_playing():
            self.btn_pause.setChecked(False)
            return
        self.player.toggle_pause()
        paused = self.player.is_paused()
        if paused:
            fx.start_glow_pulse(self.btn_pause)
            self.status_orb.set_state_color(STATE_PAUSED)
        else:
            fx.stop_glow_pulse(self.btn_pause)
            self.status_orb.set_state_color(STATE_PLAYING)
        self._set_tray_state(STATE_PAUSED if paused else STATE_PLAYING)
        self.status_label.setText("Pozastaveno" if paused else "Přehrávání...")

    def _toggle_pause_hotkey(self):
        if not self.player.is_playing():
            return
        if not self._hotkey_target_ok():
            return
        self.btn_pause.setChecked(not self.player.is_paused())
        self._on_pause_clicked(self.btn_pause.isChecked())

    def _play_macro_by_name(self, name: str):
        """Spustí konkrétní makro podle jména, bez ohledu na to, co je zrovna
        vybrané v seznamu -- volané z per-makro hotkey, funguje i když je
        hlavní okno WoofMC schované/na pozadí."""
        if self.recorder.is_recording:
            self.status_bar.showMessage("Nahrávání běží, hotkey makra ignorován.", 3000)
            return
        macro = self.macros.get(name)
        if macro is None:
            return
        if self.player.is_playing():
            if self.current_name == name:
                self.btn_play.setChecked(False)
                self._on_play_clicked(False)
            else:
                self.status_bar.showMessage(
                    f"Jiné makro už běží, '{name}' ignorováno.", 3000
                )
            return
        if not self._hotkey_target_ok(macro):
            return
        self._load_macro(name)
        self._select_macro_by_name(name)
        self.btn_play.setChecked(True)
        self._on_play_clicked(True)

    def _panic_stop(self):
        did_something = False
        if self.recorder.is_recording:
            self.btn_record.setChecked(False)
            self._on_record_clicked(False)
            did_something = True
        if self.player.is_playing():
            self._playlist_running = False
            self.btn_play.setChecked(False)
            self._on_play_clicked(False)
            did_something = True
        if did_something:
            self.status_bar.showMessage("PANIC STOP — nahrávání i přehrávání zastaveno.", 4000)
            self._notify("PANIC STOP aktivován.")

    def _on_playback_progress(self, i: int, n: int):
        self.status_label.setText(f"Přehrávání... {i}/{n}")
        fraction = i / max(n, 1)
        self.progress_bar.setValue(int(fraction * 100))
        self.timeline.set_progress(fraction, playing=True)

    def _on_playback_loop(self, count: int, total: int):
        if total > 0:
            self.status_label.setText(f"Kolo {count}/{total} dokončeno")

    def _on_playback_error(self, message: str):
        QMessageBox.warning(self, APP_NAME, f"Přehrávání se nespustilo:\n{message}")
        self.status_label.setText("Přehrávání selhalo")
        self._playlist_running = False
        self.btn_playlist_run.setEnabled(True)
        self.btn_playlist_stop.setEnabled(False)

    def _on_playback_finished(self):
        self.btn_play.setChecked(False)
        self.btn_play.setText("▶ Přehrát")
        self.btn_pause.setEnabled(False)
        self.btn_pause.setChecked(False)
        self.btn_record.setEnabled(True)
        self.progress_bar.setValue(100)
        fx.stop_glow_pulse(self.btn_play)
        fx.stop_glow_pulse(self.btn_pause)
        self.timeline.reset_progress()
        if not self._playlist_running:
            self.status_orb.set_state_color(STATE_IDLE)
        self._set_tray_state(STATE_IDLE)
        self.status_label.setText("Přehrávání dokončeno")
        if self._playlist_running:
            self._playlist_pos += 1
            QTimer.singleShot(50, self._run_next_playlist_entry)

    # ---------- table / events ----------

    def _append_table_row(self, ev: MacroEvent):
        row = self.table.rowCount()
        self.table.insertRow(row)
        item_kind = QTableWidgetItem(KIND_LABEL.get(ev.kind, ev.kind))
        item_kind.setData(Qt.UserRole, ev)
        self.table.setItem(row, 0, item_kind)
        self.table.setItem(row, 1, QTableWidgetItem(f"{ev.t:.3f}"))
        self.table.setItem(row, 2, QTableWidgetItem(describe_event(ev)))
        self.table.scrollToBottom()

    def _refresh_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for ev in self.current_events:
            self._append_table_row(ev)
        self.table.blockSignals(False)
        self.timeline.set_events(self.current_events)

    def _on_rows_moved(self, *_args):
        new_events = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            ev = item.data(Qt.UserRole) if item else None
            if ev is not None:
                new_events.append(ev)
        if len(new_events) == len(self.current_events) and new_events != self.current_events:
            self._push_undo()
            self.current_events = resequence_from_gaps(new_events)
            self._update_stats()
        # Vždy přerenderovat tabulku ze self.current_events, i když se pořadí
        # nepodařilo bezpečně přebrat (např. glitch Qt InternalMove při multi-select
        # dragu) -- jinak by tabulka a current_events mohly zůstat nesynchronizované
        # a další editace (dvojklik) by upravovala jiný event, než který je vidět.
        self._refresh_table()

    def _selected_rows(self) -> List[int]:
        return sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)

    def _push_undo(self):
        snapshot = [MacroEvent(e.t, e.kind, dict(e.data), e.uid) for e in self.current_events]
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > 25:
            self._undo_stack.pop(0)

    def _undo(self):
        if not self._undo_stack:
            self.status_label.setText("Není co vracet zpět")
            return
        self.current_events = self._undo_stack.pop()
        self._refresh_table()
        self._update_stats()
        self.status_label.setText("Vráceno zpět")

    def _on_table_double_click(self, index):
        row = index.row()
        if not (0 <= row < len(self.current_events)):
            return
        dlg = EventEditDialog(self.current_events[row], self)
        if dlg.exec_():
            self._push_undo()
            self.current_events[row] = dlg.result_event()
            self._refresh_table()
            self._update_stats()

    def _table_context_menu(self, pos):
        menu = QMenu()
        act_edit = menu.addAction("Upravit")
        act_dup = menu.addAction("Duplikovat vybrané  (Ctrl+D)")
        act_wait = menu.addAction("Vložit čekání 0.5s za vybrané")
        menu.addSeparator()
        act_del = menu.addAction("Smazat vybrané řádky  (Del)")
        menu.addSeparator()
        act_undo = menu.addAction("Zpět (Ctrl+Z)")
        act_undo.setEnabled(bool(self._undo_stack))
        action = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if action == act_undo:
            self._undo()
            return
        rows = self._selected_rows()
        if not rows:
            return
        if action == act_edit and len(rows) == 1:
            self._on_table_double_click(self.table.model().index(rows[0], 0))
        elif action == act_dup:
            self._duplicate_selected_events(rows)
        elif action == act_wait:
            self._insert_wait_after_selected(rows)
        elif action == act_del:
            self._delete_selected_events(rows)

    def _duplicate_selected_events(self, rows: List[int]):
        if not rows:
            return
        self._push_undo()
        for r in sorted(rows):
            if 0 <= r < len(self.current_events):
                ev = self.current_events[r]
                self.current_events.insert(r + 1, MacroEvent(ev.t, ev.kind, dict(ev.data)))
        self._refresh_table()
        self._update_stats()

    def _insert_wait_after_selected(self, rows: List[int]):
        if not rows:
            return
        self._push_undo()
        for r in rows:
            if 0 <= r < len(self.current_events):
                base_t = self.current_events[r].t
                self.current_events.insert(r + 1, MacroEvent(base_t + 0.5, "wait", {}))
        self._refresh_table()
        self._update_stats()

    def _delete_selected_events(self, rows: List[int]):
        if not rows:
            return
        self._push_undo()
        for r in rows:
            if 0 <= r < len(self.current_events):
                del self.current_events[r]
        self._refresh_table()
        self._update_stats()

    def _shortcut_delete_rows(self):
        self._delete_selected_events(self._selected_rows())

    def _shortcut_duplicate_rows(self):
        self._duplicate_selected_events(self._selected_rows())

    def _clear_events(self):
        if not self.current_events:
            return
        reply = QMessageBox.question(self, APP_NAME, "Vymazat všechny nahrané události?")
        if reply != QMessageBox.Yes:
            return
        self._push_undo()
        self.current_events = []
        self._refresh_table()
        self._update_stats()

    def _update_stats(self):
        n = len(self.current_events)
        duration = estimate_duration(self.current_events)
        self.stats_chip.setText(f"{n} událostí · {duration:.1f}s")

    def _current_macro_dict(self) -> dict:
        existing = self.macros.get(self.current_name, storage.new_macro_dict()) if self.current_name else storage.new_macro_dict()
        data = dict(existing)
        data["events"] = events_to_dicts(self.current_events)
        data["loops"] = self.spin_loops.value()
        data["speed"] = self.spin_speed.value()
        data["jitter"] = self.spin_jitter.value()
        data["start_delay"] = self.spin_delay.value()
        data["input_backend_override"] = self.combo_macro_backend.currentData() or ""
        data["target_window_title"] = self.combo_macro_window.currentText().strip()
        if data["target_window_title"] == "(globální)":
            data["target_window_title"] = ""
        data["target_process_name"] = self.combo_macro_process.currentText().strip()
        if data["target_process_name"] == "(globální)":
            data["target_process_name"] = ""
        data["hotkey"] = self.macro_hotkey_edit.hotkey
        storage.touch_macro(data)
        return data

    def _macro_hotkey_conflict(self, hotkey: str, exclude_name: Optional[str]) -> str:
        """Vrátí popis kolize, nebo prázdný string pokud je hotkey volný."""
        if not hotkey:
            return ""
        reserved = {
            self.config.get("hotkey_record"): "Nahrávání",
            self.config.get("hotkey_play"): "Přehrávání",
            self.config.get("hotkey_pause"): "Pauza",
            self.config.get("hotkey_panic"): "PANIC STOP",
        }
        if hotkey in reserved:
            return reserved[hotkey]
        for other_name, other_macro in self.macros.items():
            if other_name != exclude_name and other_macro.get("hotkey") == hotkey:
                return f"makro '{other_name}'"
        return ""

    def _save_current_macro(self):
        if self.current_name is None:
            name, ok = QInputDialog.getText(self, "Uložit makro", "Název makra:")
            if not ok or not name.strip():
                return
            self.current_name = name.strip()
        hotkey = self.macro_hotkey_edit.hotkey
        conflict = self._macro_hotkey_conflict(hotkey, exclude_name=self.current_name)
        if conflict:
            QMessageBox.warning(
                self, APP_NAME,
                f"Hotkey {pretty_hotkey(hotkey)} už používá: {conflict}. Zvol jiný nebo ho vymaž."
            )
            return
        self.macros[self.current_name] = self._current_macro_dict()
        storage.save_macros(self.macros)
        self._reload_macro_list()
        self._select_macro_by_name(self.current_name)
        self._register_hotkeys()
        self.status_label.setText(f"Uloženo: {self.current_name}")
        self._notify(f"Makro '{self.current_name}' uloženo.")

    # ---------- playlist ----------

    def _reload_playlist_combo(self):
        self.combo_playlist.blockSignals(True)
        self.combo_playlist.clear()
        self.combo_playlist.addItems(sorted(self.playlists.keys()))
        self.combo_playlist.blockSignals(False)
        if self.playlists:
            self._on_playlist_selected(self.combo_playlist.currentText())

    def _current_playlist_entries(self) -> List[dict]:
        entries = []
        for i in range(self.playlist_list.count()):
            entries.append(self.playlist_list.item(i).data(Qt.UserRole))
        return entries

    def _refresh_playlist_widget(self, entries: List[dict]):
        self.playlist_list.clear()
        for entry in entries:
            item = QListWidgetItem(f"{entry['macro']}  ×{entry['repeat']}")
            item.setData(Qt.UserRole, entry)
            self.playlist_list.addItem(item)

    def _on_playlist_selected(self, name: str):
        entries = self.playlists.get(name, [])
        self._refresh_playlist_widget(entries)

    def _new_playlist(self):
        name, ok = QInputDialog.getText(self, "Nový playlist", "Název playlistu:")
        if not ok or not name.strip():
            return
        name = name.strip()
        self.playlists[name] = []
        storage.save_playlists(self.playlists)
        self._reload_playlist_combo()
        self.combo_playlist.setCurrentText(name)

    def _delete_playlist(self):
        name = self.combo_playlist.currentText()
        if not name:
            return
        reply = QMessageBox.question(self, APP_NAME, f"Smazat playlist '{name}'?")
        if reply != QMessageBox.Yes:
            return
        self.playlists.pop(name, None)
        storage.save_playlists(self.playlists)
        self._reload_playlist_combo()

    def _save_playlist(self):
        name = self.combo_playlist.currentText()
        if not name:
            name, ok = QInputDialog.getText(self, "Uložit playlist", "Název playlistu:")
            if not ok or not name.strip():
                return
            name = name.strip()
        self.playlists[name] = self._current_playlist_entries()
        storage.save_playlists(self.playlists)
        self._reload_playlist_combo()
        self.combo_playlist.setCurrentText(name)
        self.playlist_status.setText(f"Playlist '{name}' uložen")

    def _playlist_add_selected_macro(self):
        item = self.macro_list.currentItem()
        if item is None:
            QMessageBox.information(self, APP_NAME, "Nejprve vyber makro v levém panelu.")
            return
        name = item.data(Qt.UserRole)
        if not name:
            return
        entries = self._current_playlist_entries()
        entries.append({"macro": name, "repeat": 1})
        self._refresh_playlist_widget(entries)

    def _playlist_remove_selected(self):
        row = self.playlist_list.currentRow()
        if row < 0:
            return
        entries = self._current_playlist_entries()
        del entries[row]
        self._refresh_playlist_widget(entries)

    def _playlist_move(self, direction: int):
        row = self.playlist_list.currentRow()
        if row < 0:
            return
        entries = self._current_playlist_entries()
        new_row = row + direction
        if not (0 <= new_row < len(entries)):
            return
        entries[row], entries[new_row] = entries[new_row], entries[row]
        self._refresh_playlist_widget(entries)
        self.playlist_list.setCurrentRow(new_row)

    def _playlist_update_repeat(self, value: int):
        row = self.playlist_list.currentRow()
        if row < 0:
            return
        entries = self._current_playlist_entries()
        entries[row]["repeat"] = value
        self._refresh_playlist_widget(entries)
        self.playlist_list.setCurrentRow(row)

    def _start_playlist(self):
        if self.recorder.is_recording or self.player.is_playing():
            QMessageBox.information(self, APP_NAME, "Nejprve zastav aktuální nahrávání nebo přehrávání.")
            return
        entries = self._current_playlist_entries()
        if not entries:
            QMessageBox.information(self, APP_NAME, "Playlist je prázdný.")
            return
        self._playlist_entries = entries
        self._playlist_pos = 0
        self._playlist_running = True
        self.btn_playlist_run.setEnabled(False)
        self.btn_playlist_stop.setEnabled(True)
        self._run_next_playlist_entry()

    def _run_next_playlist_entry(self):
        if not self._playlist_running or self._playlist_pos >= len(self._playlist_entries):
            self._finish_playlist()
            return
        entry = self._playlist_entries[self._playlist_pos]
        macro = self.macros.get(entry["macro"])
        if not macro:
            self._playlist_pos += 1
            self._run_next_playlist_entry()
            return
        events = dicts_to_events(macro.get("events", []))
        if not events:
            self._playlist_pos += 1
            self._run_next_playlist_entry()
            return
        delay = 0.0 if self._playlist_pos == 0 else self.spin_playlist_delay.value()
        self.playlist_status.setText(
            f"Přehrávám '{entry['macro']}' ({self._playlist_pos + 1}/{len(self._playlist_entries)})"
        )
        self._set_tray_state(STATE_PLAYING)
        backend_id, title, process = self._resolve_target(macro)
        self.player.backend_id = backend_id
        self.player.target_window_title = title
        self.player.target_process_name = process
        self._maybe_autofocus_target(title, process)
        self.player.play(
            events,
            loops=entry.get("repeat", 1),
            speed=macro.get("speed", 1.0),
            jitter_ms=macro.get("jitter", 0),
            start_delay=delay,
        )

    def _stop_playlist(self):
        self._playlist_running = False
        self.player.stop()
        self._finish_playlist()

    def _finish_playlist(self):
        self._playlist_running = False
        self.btn_playlist_run.setEnabled(True)
        self.btn_playlist_stop.setEnabled(False)
        self.playlist_status.setText("Playlist dokončen")
        self._set_tray_state(STATE_IDLE)

    # ---------- misc ----------

    def _show_about(self):
        QMessageBox.information(
            self, APP_NAME,
            f"{APP_NAME} v{VERSION}\n\n"
            "Externí nástroj pro záznam a přehrávání klávesnice a myši.\n"
            f"Hotkeys: {pretty_hotkey(self.config.get('hotkey_record'))} nahrávání, "
            f"{pretty_hotkey(self.config.get('hotkey_play'))} přehrávání, "
            f"{pretty_hotkey(self.config.get('hotkey_pause'))} pauza.\n\n"
            "Poznámka: hry s kernel-level anticheatem (EAC, BattlEye, Vanguard) "
            "mohou blokovat globální hooky nebo detekovat syntetické vstupy bez ohledu "
            "na zvolený vstupní backend."
        )

    def closeEvent(self, event):
        if self.config.get("close_to_tray", True):
            event.ignore()
            self.hide()
            self._notify("Aplikace běží na pozadí.")
        else:
            self._force_quit()

    def _force_quit(self):
        try:
            if self._hotkeys:
                self._hotkeys.stop()
        except Exception:
            pass
        if self.recorder.is_recording:
            self.recorder.stop()
        if self.player.is_playing():
            self.player.stop()
        self.tray.hide()
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    _install_exception_hook(app)
    app.setStyleSheet(theme.DARK_PURPLE_QSS)
    app.setQuitOnLastWindowClosed(False)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

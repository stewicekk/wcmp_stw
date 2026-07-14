SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
RADIUS = {"sm": 6, "md": 8, "lg": 12}

DARK_PURPLE_QSS = """
QWidget {
    background-color: #08070c;
    color: #e6e1f0;
    font-family: "Segoe UI", Arial;
    font-size: 10pt;
}
QMainWindow {
    background-color: #050408;
}
QFrame#card {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #15111d, stop:1 #0c0a12);
    border: 1px solid #2a2236;
    border-radius: 12px;
}
QListWidget, QTableWidget {
    background-color: #0d0b13;
    border: 1px solid #241d30;
    border-radius: 8px;
    gridline-color: #1c1725;
}
QListWidget::item, QTableWidget::item {
    padding: 5px;
}
QListWidget::item:selected, QTableWidget::item:selected {
    background-color: #6b3fa0;
    color: #ffffff;
}
QListWidget::item:hover:!selected {
    background-color: #2a2436;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4c4066, stop:1 #362c48);
    border-top: 1px solid #7d5cc0;
    border-left: 1px solid #6b3fa0;
    border-right: 1px solid #4a3566;
    border-bottom: 1px solid #241c33;
    border-radius: 8px;
    padding: 7px 16px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5f4f80, stop:1 #453a5c);
}
QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6b3fa0, stop:1 #8a5cd0);
    border-top: 1px solid #241c33;
    border-left: 1px solid #4a3566;
    border-right: 1px solid #6b3fa0;
    border-bottom: 1px solid #9a7ae0;
}
QPushButton:disabled {
    background-color: #241f30;
    border-color: #392e4a;
    color: #5e5670;
}
QPushButton#recordBtn:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e74c3c, stop:1 #a8362a);
    border-top: 1px solid #ff8a7a;
    border-left: 1px solid #ff6b5b;
    border-right: 1px solid #a8362a;
    border-bottom: 1px solid #6e2018;
}
QPushButton#playBtn:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2ecc71, stop:1 #1f8a4c);
    border-top: 1px solid #7ce0a8;
    border-left: 1px solid #58e08c;
    border-right: 1px solid #1f8a4c;
    border-bottom: 1px solid #135530;
}
QPushButton#pauseBtn:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e8b923, stop:1 #b7860b);
    border-top: 1px solid #ffe28a;
    border-left: 1px solid #ffd35c;
    border-right: 1px solid #b7860b;
    border-bottom: 1px solid #7a5806;
}
QPushButton#primaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8a5cd0, stop:1 #6b3fa0);
    border-top: 1px solid #c3a5f0;
    border-left: 1px solid #a97ae8;
    border-right: 1px solid #6b3fa0;
    border-bottom: 1px solid #432a66;
    font-weight: 600;
}
QPushButton#primaryBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #9a6ce0, stop:1 #7d4bb8);
}
QPushButton#dangerBtn {
    border-color: #e74c3c;
}
QPushButton#dangerBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7a382f, stop:1 #632a24);
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #120f1a;
    border: 1px solid #2a2236;
    border-radius: 4px;
    padding: 5px;
    selection-background-color: #6b3fa0;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #8a5cd0;
}
QLineEdit#searchBox {
    background-color: #0f0c16;
    border-radius: 12px;
    padding: 5px 10px;
}
QComboBox QAbstractItemView {
    background-color: #120f1a;
    selection-background-color: #6b3fa0;
    border: 1px solid #2a2236;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 3px;
    border: 1px solid #6b3fa0;
    background: #120f1a;
}
QCheckBox::indicator:checked {
    background: #8a5cd0;
}
QLabel#statusLabel {
    color: #a98fd1;
    font-weight: bold;
}
QLabel#hintLabel {
    color: #6a6280;
    font-size: 9pt;
}
QLabel#sectionLabel {
    color: #cbb8e6;
    font-weight: 600;
    font-size: 9pt;
    padding-top: 4px;
}
QLabel#statsChip {
    background-color: #170f22;
    border: 1px solid #2a2236;
    border-radius: 10px;
    padding: 3px 10px;
    color: #cbb8e6;
    font-size: 9pt;
}
QHeaderView::section {
    background-color: #150f1e;
    border: none;
    border-right: 1px solid #08070c;
    padding: 5px;
    color: #cbb8e6;
}
QStatusBar {
    background-color: #050408;
    border-top: 1px solid #2a2236;
}
QMenuBar, QMenu {
    background-color: #08070c;
    color: #e6e1f0;
}
QMenu {
    border: 1px solid #2a2236;
}
QMenuBar::item:selected, QMenu::item:selected {
    background-color: #6b3fa0;
}
QTabWidget::pane {
    border: 1px solid #2a2236;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background-color: #120f1a;
    padding: 7px 16px;
    border: 1px solid #2a2236;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8a5cd0, stop:1 #6b3fa0);
}
QTabBar::tab:hover:!selected {
    background-color: #1c1725;
}
QScrollBar:vertical {
    background: #08070c;
    width: 10px;
}
QScrollBar::handle:vertical {
    background: #2a2236;
    border-radius: 5px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #5a3f80;
}
QScrollBar:horizontal {
    background: #08070c;
    height: 10px;
}
QScrollBar::handle:horizontal {
    background: #2a2236;
    border-radius: 5px;
    min-width: 24px;
}
QSplitter::handle {
    background-color: #2a2236;
}
QProgressBar {
    background-color: #120f1a;
    border: 1px solid #2a2236;
    border-radius: 4px;
    text-align: center;
    color: #e6e1f0;
}
QProgressBar::chunk {
    background-color: #6b3fa0;
    border-radius: 4px;
}
QToolTip {
    background-color: #17121f;
    color: #e6e1f0;
    border: 1px solid #6b3fa0;
    padding: 4px;
}
QDialog {
    background-color: #08070c;
}
"""

ACCENT_COLORS = {
    "fialová": "#6b3fa0",
    "modrá": "#3f7fa0",
    "zelená": "#3fa070",
    "červená": "#a03f4f",
}

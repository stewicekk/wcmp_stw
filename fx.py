from typing import List, Optional

from PyQt5.QtCore import Qt, QVariantAnimation, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen
from PyQt5.QtWidgets import QWidget, QGraphicsDropShadowEffect


def make_glow(color: str, blur: int = 18, x_offset: int = 0, y_offset: int = 0) -> QGraphicsDropShadowEffect:
    effect = QGraphicsDropShadowEffect()
    effect.setColor(QColor(color))
    effect.setBlurRadius(blur)
    effect.setOffset(x_offset, y_offset)
    return effect


def attach_static_glow(widget, color: str, blur: int = 16):
    effect = make_glow(color, blur)
    widget.setGraphicsEffect(effect)
    return effect


def attach_pulsing_glow(widget, color: str, low: int = 0, high: int = 26,
                         duration: int = 1400) -> QPropertyAnimation:
    """Efekt se nastaví na widget JEDNOU a už nikdy se neodpojuje setGraphicsEffect(None)
    -- Qt při odpojení efekt rovnou maže (delete), takže opakované odpojování/připojování
    stejné instance by vedlo k pádu na dangling pointeru. Místo toho se v klidu drží
    blurRadius na 0 (neviditelné) a pulzování se jen spouští/zastavuje."""
    effect = make_glow(color, low)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"blurRadius", widget)
    anim.setDuration(duration)
    anim.setKeyValueAt(0.0, low)
    anim.setKeyValueAt(0.5, high)
    anim.setKeyValueAt(1.0, low)
    anim.setEasingCurve(QEasingCurve.InOutSine)
    anim.setLoopCount(-1)
    widget._glow_effect = effect
    widget._glow_anim = anim
    return anim


def start_glow_pulse(widget):
    anim = getattr(widget, "_glow_anim", None)
    if anim and anim.state() != QPropertyAnimation.Running:
        anim.start()


def stop_glow_pulse(widget):
    anim = getattr(widget, "_glow_anim", None)
    effect = getattr(widget, "_glow_effect", None)
    if anim:
        anim.stop()
    if effect:
        effect.setBlurRadius(0)


class StatusOrb(QWidget):
    """Malá kolečková kontrolka stavu s plynulým přechodem barvy."""

    def __init__(self, parent=None, diameter: int = 14):
        super().__init__(parent)
        self._diameter = diameter
        self.setFixedSize(diameter, diameter)
        self._color = QColor("#6b3fa0")
        self._anim: Optional[QVariantAnimation] = None

    def set_state_color(self, color: str, animate: bool = True):
        target = QColor(color)
        if not animate:
            if self._anim:
                self._anim.stop()
            self._color = target
            self.update()
            return
        if self._anim:
            self._anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(self._color)
        anim.setEndValue(target)
        anim.setDuration(320)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.valueChanged.connect(self._on_anim_value)
        anim.start()
        self._anim = anim

    def _on_anim_value(self, value):
        self._color = QColor(value)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(self._color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(1, 1, self._diameter - 2, self._diameter - 2)
        glow = QColor(self._color)
        glow.setAlpha(70)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(-2, -2, self._diameter + 4, self._diameter + 4)


class TimelineWidget(QWidget):
    """Nezávislá vizualizace časové osy makra — tečky podle typu události
    a posuvná hlava přehrávání. Čistě informativní, bez interakce/scrubování,
    protože zásah doprostřed přehrávání by mohl nechat klávesy/tlačítka
    v nekonzistentním (podrženém) stavu."""

    KIND_COLORS = {
        "move": "#4a4560",
        "click": "#8a5cd0",
        "scroll": "#3f9fa8",
        "key_down": "#4a7fd6",
        "key_up": "#35608f",
        "wait": "#6b6478",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self._events: List = []
        self._duration = 0.0
        self._progress = 0.0
        self._playing = False

    def set_events(self, events: List):
        self._events = events
        self._duration = events[-1].t if events else 0.0
        self.update()

    def set_progress(self, fraction: float, playing: bool = True):
        self._progress = max(0.0, min(1.0, fraction))
        self._playing = playing
        self.update()

    def reset_progress(self):
        self._progress = 0.0
        self._playing = False
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mid = h // 2
        margin = 8

        painter.setPen(QPen(QColor("#332a44"), 2))
        painter.drawLine(margin, mid, w - margin, mid)

        if not self._events or self._duration <= 0:
            painter.setPen(QColor("#5e5670"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Žádné události")
            return

        usable = max(w - 2 * margin, 1)
        for ev in self._events:
            x = margin + int((ev.t / self._duration) * usable)
            color = QColor(self.KIND_COLORS.get(ev.kind, "#6b6478"))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(x - 2, mid - 7, 4, 14, 2, 2)

        if self._playing:
            x = margin + int(self._progress * usable)
            pen = QPen(QColor("#e6e1f0"), 2)
            painter.setPen(pen)
            painter.drawLine(x, 2, x, h - 2)
            glow = QColor("#e6e1f0")
            glow.setAlpha(90)
            painter.setPen(QPen(glow, 6))
            painter.drawLine(x, 2, x, h - 2)

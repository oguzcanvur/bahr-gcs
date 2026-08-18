"""BAHR-GCS — yeniden kullanilabilir arayuz bilesenleri.

Tum bilesenler gcs.theme icindeki token'lari kullanir; hicbiri kendi
icinde sabit renk/olcu tanimlamaz. Boylece tema tek noktadan degistirilebilir.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gcs.theme import COLORS, Radius, Space, Type, mono_font_family, qcolor, ui_font_family


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------

def set_variant(widget: QWidget, variant: str) -> QWidget:
    """QSS property selector'lari icin varyant atar."""
    widget.setProperty("variant", variant)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    return widget


def h_divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    line.setFrameShape(QFrame.Shape.NoFrame)
    line.setFixedHeight(1)
    return line


def v_divider(height: int = 22) -> QFrame:
    line = QFrame()
    line.setObjectName("vDivider")
    line.setFrameShape(QFrame.Shape.NoFrame)
    line.setFixedWidth(1)
    line.setFixedHeight(height)
    return line


def button(text: str, variant: str = "default", on_click: Callable | None = None) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    set_variant(btn, variant)
    if on_click is not None:
        btn.clicked.connect(on_click)
    return btn


def toggle(text: str, checked: bool = False) -> QCheckBox:
    box = QCheckBox(text)
    box.setChecked(checked)
    box.setCursor(Qt.CursorShape.PointingHandCursor)
    box.setProperty("toggle", "true")
    return box


def section_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("sectionLabel")
    return label


def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("fieldLabel")
    return label


# ---------------------------------------------------------------------------
# Kart
# ---------------------------------------------------------------------------

class Card(QFrame):
    """Baslik + istege bagli aksiyon alani + govde iceren temel yuzey."""

    def __init__(
        self,
        title: str = "",
        parent: QWidget | None = None,
        flat: bool = False,
        spacing: int = Space.md,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cardFlat" if flat else "card")

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(Space.lg, Space.md, Space.lg, Space.lg)
        self._outer.setSpacing(Space.md)

        self.header = QWidget()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(Space.sm)
        self.title_label = QLabel(title.upper())
        self.title_label.setObjectName("cardTitle")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        self._header_layout = header_layout
        if not title:
            self.header.hide()
        self._outer.addWidget(self.header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(spacing)
        self._outer.addWidget(self.body)

    def add_header_widget(self, widget: QWidget) -> None:
        self.header.show()
        self._header_layout.addWidget(widget)

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body_layout.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout) -> None:
        self.body_layout.addLayout(layout)

    def add_divider(self) -> None:
        self.body_layout.addWidget(h_divider())


# ---------------------------------------------------------------------------
# Durum rozeti
# ---------------------------------------------------------------------------

class StatusPill(QLabel):
    """Renk kodlu, yuvarlak kenarli durum gostergesi."""

    TONES = {
        "neutral": (COLORS.neutral_soft, COLORS.text_secondary),
        "accent": (COLORS.accent_soft, COLORS.accent),
        "info": (COLORS.info_soft, COLORS.info),
        "success": (COLORS.success_soft, COLORS.success),
        "warning": (COLORS.warning_soft, COLORS.warning),
        "danger": (COLORS.danger_soft, COLORS.danger),
    }

    def __init__(self, text: str = "", tone: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        pill_font = QFont(ui_font_family(), Type.micro)
        pill_font.setWeight(QFont.Weight.Bold)
        pill_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        self.setFont(pill_font)
        self._tone: str | None = None
        self.set_state(text, tone)

    def set_state(self, text: str, tone: str = "neutral") -> None:
        self.setText(text)
        if tone != self._tone:
            self._tone = tone
            background, foreground = self.TONES.get(tone, self.TONES["neutral"])
            self.setStyleSheet(
                f"background: {background};"
                f"color: {foreground};"
                f"border-radius: {Radius.pill}px;"
                f"padding: {Space.xs}px {Space.md}px;"
            )
        # Stylesheet padding'i sizeHint'e her zaman yansimadigi icin genisligi
        # metin genisligine gore acikca sabitliyoruz — metin kirpilmasin.
        self.setMinimumWidth(self.fontMetrics().horizontalAdvance(text) + 2 * Space.md + Space.sm)
        self.setFixedHeight(self.fontMetrics().height() + 2 * Space.xs + Space.xs)


class LiveDot(QWidget):
    """Baglanti durumunu gosteren kucuk isikli nokta."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._tone = COLORS.text_tertiary

    def set_tone(self, color: str) -> None:
        self._tone = color
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        halo = qcolor(self._tone, 60)
        painter.setBrush(halo)
        painter.drawEllipse(0, 0, 12, 12)
        painter.setBrush(qcolor(self._tone))
        painter.drawEllipse(3, 3, 6, 6)


# ---------------------------------------------------------------------------
# Metrik gostergeleri
# ---------------------------------------------------------------------------

class MetricTile(QFrame):
    """Buyuk sayi + kucuk etiket. Telemetri icin birincil okuma birimi."""

    def __init__(
        self,
        caption: str,
        value: str = "—",
        unit: str = "",
        large: bool = False,
        parent: QWidget | None = None,
        bare: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("metricTileBare" if bare else "cardFlat")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(Space.md, Space.sm, Space.md, Space.sm)
        layout.setSpacing(Space.xxs)

        self.caption_label = QLabel(caption.upper())
        self.caption_label.setObjectName("metricCaption")

        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.setSpacing(Space.xs)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValueLarge" if large else "metricValue")
        self.unit_label = QLabel(unit)
        self.unit_label.setObjectName("metricUnit")
        value_row.addWidget(self.value_label)
        value_row.addWidget(self.unit_label, 0, Qt.AlignmentFlag.AlignBottom)
        value_row.addStretch(1)

        layout.addWidget(self.caption_label)
        layout.addLayout(value_row)

        # Sayilarin kirpilmamasi icin taban genislik: en uzun caption + deger.
        self.setMinimumWidth(108 if bare else 96)
        self.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
        self._last_color: str | None = None

    def set_value(self, value: str, tone: str | None = None) -> None:
        self.value_label.setText(value)
        color = tone or COLORS.text_primary
        if color != self._last_color:
            self._last_color = color
            size = Type.display if self.value_label.objectName() == "metricValueLarge" else Type.heading
            self.value_label.setStyleSheet(
                f'font-family: "{mono_font_family()}";'
                f"font-size: {size}px; font-weight: 700; color: {color};"
            )

    def set_unit(self, unit: str) -> None:
        self.unit_label.setText(unit)


class MetricGrid(QWidget):
    """Metrik tile'lari esit sutunlara yerlestiren duzenleyici."""

    def __init__(self, columns: int = 2, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._columns = columns
        self._count = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(Space.sm)
        self._grid.setVerticalSpacing(Space.sm)

    def add_tile(self, tile: MetricTile) -> MetricTile:
        row, column = divmod(self._count, self._columns)
        self._grid.addWidget(tile, row, column)
        self._count += 1
        return tile


class KeyValueRow(QWidget):
    """Etiket solda, mono degeri sagda — yogun veri listeleri icin."""

    def __init__(self, key: str, value: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, Space.xxs, 0, Space.xxs)
        layout.setSpacing(Space.sm)
        self.key_label = field_label(key)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")
        self.value_label.setStyleSheet(
            f'font-family: "{mono_font_family()}"; font-size: {Type.label}px;'
            f"font-weight: 600; color: {COLORS.text_primary};"
        )
        self._last_color: str | None = COLORS.text_primary
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.key_label)
        layout.addStretch(1)
        layout.addWidget(self.value_label)

    def set_value(self, value: str, tone: str | None = None) -> None:
        self.value_label.setText(value)
        color = tone or COLORS.text_primary
        if color != self._last_color:
            self._last_color = color
            self.value_label.setStyleSheet(
                f'font-family: "{mono_font_family()}"; font-size: {Type.label}px;'
                f"font-weight: 600; color: {color};"
            )


class FormRow(QWidget):
    """Ust satirda etiket, altta girdi — dar panellerde hizalama sorununu cozer."""

    def __init__(self, label: str, widget: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Space.xs)
        self.label = field_label(label)
        layout.addWidget(self.label)
        layout.addWidget(widget)
        self.widget = widget


# ---------------------------------------------------------------------------
# Segmented control
# ---------------------------------------------------------------------------

class SegmentedControl(QWidget):
    """Sekme yerine kullanilan kompakt secim bilesenleri (UDP / TCP / Serial)."""

    changed = pyqtSignal(str)

    def __init__(self, options: Iterable[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(Space.xs, Space.xs, Space.xs, Space.xs)
        layout.setSpacing(Space.xs)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for index, option in enumerate(options):
            btn = QPushButton(option)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("segment", "true")
            if index == 0:
                btn.setChecked(True)
            self._group.addButton(btn, index)
            layout.addWidget(btn)
        self._group.idClicked.connect(self._emit_changed)

    def _emit_changed(self, _index: int) -> None:
        self.changed.emit(self.current_text())

    def current_text(self) -> str:
        btn = self._group.checkedButton()
        return btn.text() if btn else ""

    def set_current(self, text: str) -> None:
        for btn in self._group.buttons():
            if btn.text() == text:
                btn.setChecked(True)
                self.changed.emit(text)
                return


# ---------------------------------------------------------------------------
# Gorsel gostergeler
# ---------------------------------------------------------------------------

class BatteryGauge(QWidget):
    """Yatay, kademe renkli batarya doluluk cubugu."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(34)
        self._percent: float | None = None
        self._voltage: float | None = None

    def set_state(self, percent: float | None, voltage: float | None) -> None:
        self._percent = percent
        self._voltage = voltage
        self.update()

    def _tone(self) -> str:
        if self._percent is None:
            return COLORS.text_tertiary
        if self._percent < 20:
            return COLORS.danger
        if self._percent < 40:
            return COLORS.warning
        return COLORS.success

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0, 8, -0.0, -8)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(COLORS.surface_3))
        painter.drawRoundedRect(rect, 9, 9)

        ratio = 0.0 if self._percent is None else max(0.0, min(1.0, self._percent / 100.0))
        if ratio > 0:
            fill = QRectF(rect)
            fill.setWidth(max(18.0, rect.width() * ratio))
            painter.setBrush(qcolor(self._tone()))
            painter.drawRoundedRect(fill, 9, 9)

        painter.setPen(QPen(qcolor(COLORS.text_primary if ratio > 0.35 else COLORS.text_secondary)))
        font = QFont(mono_font_family(), Type.caption)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        text = "—" if self._percent is None else f"{self._percent:.0f}%"
        if self._voltage is not None:
            text += f"   {self._voltage:.2f} V"
        painter.drawText(rect.adjusted(Space.md, 0, -Space.md, 0),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)


class MissionProgressBar(QWidget):
    """Gorev ilerlemesini nokta + cizgi olarak gosteren ince gosterge."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(26)
        self._active = 0
        self._total = 0

    def set_progress(self, active: int, total: int) -> None:
        self._active = active
        self._total = total
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = self.height() / 2
        painter.setPen(QPen(qcolor(COLORS.surface_3), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(6, y), QPointF(self.width() - 6, y))

        if self._total <= 0:
            return
        ratio = max(0.0, min(1.0, self._active / self._total))
        end_x = 6 + (self.width() - 12) * ratio
        painter.setPen(QPen(qcolor(COLORS.accent), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(6, y), QPointF(max(6.0, end_x), y))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(COLORS.accent))
        painter.drawEllipse(QPointF(max(6.0, end_x), y), 6, 6)
        painter.setBrush(qcolor(COLORS.bg_root))
        painter.drawEllipse(QPointF(max(6.0, end_x), y), 2.5, 2.5)


class Sparkline(QWidget):
    """Son N degeri gosteren minimal trend cizgisi (derinlik profili icin)."""

    def __init__(self, tone: str = COLORS.info, capacity: int = 120, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(56)
        self._values: list[float] = []
        self._capacity = capacity
        self._tone = tone

    def push(self, value: float) -> None:
        self._values.append(value)
        if len(self._values) > self._capacity:
            self._values = self._values[-self._capacity:]
        self.update()

    def clear(self) -> None:
        self._values.clear()
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 4, -1, -4)

        painter.setPen(QPen(qcolor(COLORS.border_subtle), 1, Qt.PenStyle.DotLine))
        for i in range(1, 3):
            y = rect.top() + rect.height() * i / 3
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        if len(self._values) < 2:
            painter.setPen(QPen(qcolor(COLORS.text_tertiary)))
            painter.setFont(QFont(ui_font_family(), Type.caption))
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "awaiting data")
            return

        low = min(self._values)
        high = max(self._values)
        span = max(0.4, high - low)
        step = rect.width() / (len(self._values) - 1)

        path = QPainterPath()
        fill = QPainterPath()
        for index, value in enumerate(self._values):
            x = rect.left() + index * step
            y = rect.bottom() - ((value - low) / span) * rect.height()
            if index == 0:
                path.moveTo(x, y)
                fill.moveTo(x, rect.bottom())
                fill.lineTo(x, y)
            else:
                path.lineTo(x, y)
                fill.lineTo(x, y)
        fill.lineTo(rect.right(), rect.bottom())
        fill.closeSubpath()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(self._tone, 40))
        painter.drawPath(fill)
        painter.setPen(QPen(qcolor(self._tone), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)


class CompassStrip(QWidget):
    """Yatay kayan pusula seridi — ust komuta cubugu icin."""

    CARDINALS = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(46)
        self.setMinimumWidth(240)
        self._heading = 0.0
        self._has_data = False

    def set_heading(self, heading_deg: float | None) -> None:
        self._has_data = heading_deg is not None
        self._heading = (heading_deg % 360.0) if heading_deg is not None else 0.0
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Without a heading the scale would read as a real "000" north bearing,
        # so it is dimmed right down and the value replaced by a dash.
        painter.setOpacity(1.0 if self._has_data else 0.22)
        width = self.width()
        center_x = width / 2
        span_deg = 80.0
        px_per_deg = width / span_deg
        baseline = 34.0

        painter.setPen(QPen(qcolor(COLORS.border_subtle), 1))
        painter.drawLine(QPointF(0, baseline), QPointF(width, baseline))

        painter.setFont(QFont(ui_font_family(), Type.micro, QFont.Weight.Bold))

        # Isaretler mutlak derece izgarasina hizalanmali (5'in katlari),
        # aksi halde 15/45 derecelik ana isaretler hicbir zaman denk gelmez.
        start = int(math.floor((self._heading - span_deg / 2) / 5.0)) * 5
        for degree in range(start, start + int(span_deg) + 11, 5):
            normalized = degree % 360
            x = center_x + (degree - self._heading) * px_per_deg
            if x < -2 or x > width + 2:
                continue
            fade = 1.0 - min(1.0, abs(x - center_x) / (width / 2.0)) * 0.55
            if normalized % 45 == 0:
                painter.setPen(QPen(qcolor(COLORS.text_secondary, int(255 * fade)), 1.4))
                painter.drawLine(QPointF(x, baseline - 11), QPointF(x, baseline))
                painter.setPen(QPen(qcolor(COLORS.text_primary, int(255 * fade))))
                painter.drawText(
                    QRectF(x - 20, 2, 40, 14),
                    int(Qt.AlignmentFlag.AlignCenter),
                    self.CARDINALS[normalized],
                )
            elif normalized % 15 == 0:
                painter.setPen(QPen(qcolor(COLORS.text_tertiary, int(220 * fade)), 1))
                painter.drawLine(QPointF(x, baseline - 7), QPointF(x, baseline))
                painter.drawText(
                    QRectF(x - 20, 4, 40, 12),
                    int(Qt.AlignmentFlag.AlignCenter),
                    f"{normalized:03d}",
                )
            else:
                painter.setPen(QPen(qcolor(COLORS.border_strong, int(200 * fade)), 1))
                painter.drawLine(QPointF(x, baseline - 4), QPointF(x, baseline))

        # Merkez gostergesi: ustte ok, altta mevcut yon degeri.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(COLORS.accent))
        marker = QPainterPath()
        marker.moveTo(center_x, baseline - 1)
        marker.lineTo(center_x - 6, baseline - 11)
        marker.lineTo(center_x + 6, baseline - 11)
        marker.closeSubpath()
        painter.drawPath(marker)

        painter.setOpacity(1.0)
        painter.setPen(QPen(qcolor(COLORS.accent if self._has_data else COLORS.text_tertiary)))
        painter.setFont(QFont(mono_font_family(), Type.caption, QFont.Weight.Bold))
        painter.drawText(
            QRectF(center_x - 30, baseline + 1, 60, 14),
            int(Qt.AlignmentFlag.AlignCenter),
            f"{self._heading:03.0f}°" if self._has_data else "—",
        )


class VirtualJoystick(QWidget):
    """Spring-centred stick pad for manual driving.

    Emits `moved(steering, throttle)` with both axes normalised to -1..+1:
    right and forward are positive. The knob springs back to centre when the
    pointer is released, so letting go always commands neutral rather than
    leaving the vehicle latched at the last deflection.
    """

    moved = pyqtSignal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(196, 196)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._steering = 0.0
        self._throttle = 0.0
        self._engaged = False

    # -- durum ------------------------------------------------------------

    def value(self) -> tuple[float, float]:
        return self._steering, self._throttle

    def is_engaged(self) -> bool:
        return self._engaged

    def center(self) -> None:
        if self._steering or self._throttle:
            self._steering = 0.0
            self._throttle = 0.0
            self.moved.emit(0.0, 0.0)
        self._engaged = False
        self.update()

    # -- fare -------------------------------------------------------------

    def _apply_pos(self, point) -> None:
        radius = self._travel_radius()
        dx = (point.x() - self.width() / 2) / radius
        dy = (point.y() - self.height() / 2) / radius
        magnitude = math.hypot(dx, dy)
        if magnitude > 1.0:
            dx /= magnitude
            dy /= magnitude
        self._steering = dx
        self._throttle = -dy  # screen y grows downwards; forward is up
        self.moved.emit(self._steering, self._throttle)
        self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self._engaged = True
        self._apply_pos(event.position())

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._engaged:
            self._apply_pos(event.position())

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        del event
        self.center()

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        del event
        if self._engaged:
            self.center()

    # -- cizim ------------------------------------------------------------

    def _travel_radius(self) -> float:
        return min(self.width(), self.height()) / 2 - 26

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = QPointF(self.width() / 2, self.height() / 2)
        radius = self._travel_radius()

        painter.setPen(QPen(qcolor(COLORS.border_subtle), 1))
        painter.setBrush(qcolor(COLORS.bg_canvas))
        painter.drawEllipse(center, radius + 20, radius + 20)

        painter.setPen(QPen(qcolor(COLORS.border_default), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, radius, radius)

        painter.setPen(QPen(qcolor(COLORS.border_subtle), 1))
        painter.drawLine(QPointF(center.x() - radius, center.y()),
                         QPointF(center.x() + radius, center.y()))
        painter.drawLine(QPointF(center.x(), center.y() - radius),
                         QPointF(center.x(), center.y() + radius))

        knob = QPointF(center.x() + self._steering * radius,
                       center.y() - self._throttle * radius)

        if self._steering or self._throttle:
            painter.setPen(QPen(qcolor(COLORS.accent, 90), 2))
            painter.drawLine(center, knob)

        tone = COLORS.accent if self._engaged else COLORS.text_tertiary
        painter.setPen(QPen(qcolor(COLORS.bg_root), 2))
        painter.setBrush(qcolor(tone))
        painter.drawEllipse(knob, 15, 15)

        painter.setPen(QPen(qcolor(COLORS.text_tertiary)))
        painter.setFont(QFont(ui_font_family(), Type.micro, QFont.Weight.Bold))
        for label, rect in (
            ("FWD", QRectF(center.x() - 30, 2, 60, 14)),
            ("REV", QRectF(center.x() - 30, self.height() - 16, 60, 14)),
        ):
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), label)


class DepthLegend(QWidget):
    """Derinlik renk skalasi icin yatay lejant."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(38)
        self._stops = [
            (COLORS.depth_0, "<1"),
            (COLORS.depth_1, "3"),
            (COLORS.depth_2, "6"),
            (COLORS.depth_3, "12"),
            (COLORS.depth_4, "25"),
            (COLORS.depth_5, "25+"),
        ]

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        segment = self.width() / len(self._stops)
        painter.setFont(QFont(mono_font_family(), Type.micro, QFont.Weight.DemiBold))
        for index, (color, label) in enumerate(self._stops):
            x = index * segment
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(color))
            radius = 4 if 0 < index < len(self._stops) - 1 else 4
            painter.drawRoundedRect(QRectF(x + 1, 2, segment - 2, 10), radius, radius)
            painter.setPen(QPen(qcolor(COLORS.text_tertiary)))
            painter.drawText(QRectF(x, 16, segment, 16),
                             int(Qt.AlignmentFlag.AlignCenter), label)


class AttitudeIndicator(QWidget):
    """Yenilenmis suni ufuk — daha yumusak renkler, net tipografi, cerceve halkasi."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(196, 196)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._roll = 0.0
        self._pitch = 0.0
        self._has_data = False

    def set_attitude(self, roll_deg: float | None, pitch_deg: float | None) -> None:
        self._has_data = roll_deg is not None and pitch_deg is not None
        self._roll = roll_deg or 0.0
        self._pitch = pitch_deg or 0.0
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # A level horizon is a claim about the vehicle; dim it when we have no
        # attitude data rather than showing a confident zero.
        painter.setOpacity(1.0 if self._has_data else 0.25)

        rect = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        size = min(rect.width(), rect.height())
        gauge = QRectF(rect.left(), rect.top(), size, size)
        center = gauge.center()
        radius = size / 2
        roll = max(-90.0, min(90.0, self._roll))
        pitch = max(-30.0, min(30.0, self._pitch))
        px_per_deg = radius / 20.0

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(COLORS.bg_root, 235))
        painter.drawEllipse(gauge)

        painter.save()
        clip = QPainterPath()
        clip.addEllipse(gauge.adjusted(4, 4, -4, -4))
        painter.setClipPath(clip)
        painter.translate(center)
        painter.rotate(-roll)
        painter.translate(0, pitch * px_per_deg)

        painter.setBrush(QColor(38, 96, 132))
        painter.drawRect(QRectF(-radius * 2, -radius * 2, radius * 4, radius * 2))
        painter.setBrush(QColor(104, 74, 48))
        painter.drawRect(QRectF(-radius * 2, 0, radius * 4, radius * 2))

        painter.setPen(QPen(qcolor(COLORS.text_primary, 230), 2))
        painter.drawLine(QPointF(-radius * 1.6, 0), QPointF(radius * 1.6, 0))

        painter.setFont(QFont(mono_font_family(), Type.micro, QFont.Weight.DemiBold))
        for degree in range(-30, 31, 10):
            if degree == 0:
                continue
            y = -degree * px_per_deg
            half = 26
            painter.setPen(QPen(qcolor(COLORS.text_primary, 170), 1))
            painter.drawLine(QPointF(-half, y), QPointF(half, y))
            painter.drawText(QRectF(-half - 30, y - 8, 24, 16),
                             int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                             str(abs(degree)))
        painter.restore()

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(qcolor(COLORS.border_strong), 2))
        painter.drawEllipse(gauge.adjusted(2, 2, -2, -2))

        painter.save()
        painter.translate(center)
        painter.setPen(QPen(qcolor(COLORS.text_secondary, 190), 1.5))
        for angle in range(-60, 61, 15):
            radians = math.radians(angle - 90)
            outer = QPointF(math.cos(radians) * (radius - 7), math.sin(radians) * (radius - 7))
            length = 12 if angle % 30 == 0 else 7
            inner = QPointF(math.cos(radians) * (radius - 7 - length),
                            math.sin(radians) * (radius - 7 - length))
            painter.drawLine(outer, inner)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(COLORS.accent))
        marker = QPainterPath()
        marker.moveTo(0, -radius + 9)
        marker.lineTo(-6, -radius + 21)
        marker.lineTo(6, -radius + 21)
        marker.closeSubpath()
        painter.drawPath(marker)

        painter.setPen(QPen(qcolor(COLORS.accent), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(-52, 0), QPointF(-16, 0))
        painter.drawLine(QPointF(16, 0), QPointF(52, 0))
        painter.setBrush(qcolor(COLORS.accent))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), 3, 3)
        painter.restore()

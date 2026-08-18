"""Kurulum ekranina ozgu cizilen bilesenler.

Buradaki her sey tek bir sey icin var: bir kalibrasyon adiminin *ne
istedigini* metinle anlatmak yerine gostermek. Operator teknenin hangi
tarafina yatirilacagini bir cizimden okur, pusula kapsamini bir halkadan
gorur, kumanda cubugunun nereye kadar gittigini bir cubuktan izler.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

from gcs.theme import COLORS, Radius, Space, Type, mono_font_family, qcolor


class InfoDot(QLabel):
    """Ustune gelince parametrenin Turkce aciklamasini gosteren kucuk isaret."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__("?", parent)
        self.setFixedSize(16, 16)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.setStyleSheet(
            f"border: 1px solid {COLORS.border_strong};"
            f"border-radius: 8px;"
            f"color: {COLORS.text_tertiary};"
            f"font-size: {Type.micro}px; font-weight: 700;"
        )
        # Qt only wraps tooltips it is told are rich text; long Turkish
        # explanations become an unreadable single line otherwise.
        self.setToolTip(f"<div style='max-width:420px'>{text}</div>")


class RcChannelBar(QWidget):
    """Tek bir kumanda kanali: canli deger + yakalanan min/max araligi."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.title = title
        self.value = 1500
        self.minimum = 1500
        self.maximum = 1500
        self.trim = 1500
        self.captured = False

    def set_value(self, value: int, capture: bool) -> None:
        self.value = value
        if capture:
            if not self.captured:
                self.minimum = self.maximum = value
                self.captured = True
            self.minimum = min(self.minimum, value)
            self.maximum = max(self.maximum, value)
        self.update()

    def reset(self, trim: int = 1500) -> None:
        self.captured = False
        self.minimum = self.maximum = self.value
        self.trim = trim
        self.update()

    # 800..2200 us -> 0..1
    @staticmethod
    def _fraction(value: int) -> float:
        return max(0.0, min(1.0, (value - 800) / 1400.0))

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        label_w = 34
        track = QRectF(label_w, 16, self.width() - label_w - 54, 10)

        painter.setPen(qcolor(COLORS.text_tertiary))
        painter.setFont(QFont(mono_font_family(), Type.micro, QFont.Weight.Bold))
        painter.drawText(
            QRectF(0, 12, label_w - 6, 18),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self.title,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(COLORS.bg_canvas))
        painter.drawRoundedRect(track, 5, 5)

        if self.captured and self.maximum > self.minimum:
            lo = track.left() + track.width() * self._fraction(self.minimum)
            hi = track.left() + track.width() * self._fraction(self.maximum)
            painter.setBrush(qcolor(COLORS.accent, 70))
            painter.drawRoundedRect(QRectF(lo, track.top(), hi - lo, track.height()), 5, 5)

        x = track.left() + track.width() * self._fraction(self.value)
        painter.setBrush(qcolor(COLORS.accent))
        painter.drawEllipse(QPointF(x, track.center().y()), 6, 6)

        painter.setPen(qcolor(COLORS.text_primary))
        painter.drawText(
            QRectF(track.right() + 8, 12, 46, 18),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            str(self.value),
        )

        if self.captured:
            painter.setPen(qcolor(COLORS.text_tertiary))
            painter.setFont(QFont(mono_font_family(), Type.micro))
            painter.drawText(
                QRectF(label_w, 0, track.width(), 14),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{self.minimum} – {self.maximum}",
            )
        painter.end()


class BoatPoseView(QWidget):
    """Ivmeolcer kalibrasyonunun istedigi durusu cizen sema.

    ArduPilot sirayla level / sol yan / sag yan / burun asagi / burun yukari /
    sirt uzeri ister (AP_AccelCal.cpp). Metin yerine cizim, hangi tarafin
    hangisi oldugunu tartismaya yer birakmadan gosterir.
    """

    POSE_NAMES = {
        0: "Hazır",
        1: "DÜZ — tekneyi normal duruşunda, yatay bırakın",
        2: "SOL YANI üzerine yatırın",
        3: "SAĞ YANI üzerine yatırın",
        4: "BURNU AŞAĞI bakacak şekilde dikin",
        5: "BURNU YUKARI bakacak şekilde dikin",
        6: "SIRT ÜSTÜ — tamamen ters çevirin",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.pose = 0
        self.done: set[int] = set()

    def set_pose(self, pose: int) -> None:
        if self.pose and self.pose != pose:
            self.done.add(self.pose)
        self.pose = pose
        self.update()

    def reset(self) -> None:
        self.pose = 0
        self.done.clear()
        self.update()

    def _hull(self) -> QPolygonF:
        """Ustten gorunum tekne silueti, kendi merkezine gore."""
        return QPolygonF([
            QPointF(0, -46), QPointF(19, -14), QPointF(19, 40),
            QPointF(-19, 40), QPointF(-19, -14),
        ])

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, 88.0

        painter.save()
        painter.translate(cx, cy)

        # Duruslar dondurme/olcekleme ile temsil edilir: yan yatis dar bir
        # silueti, burun asagi/yukari kisalmis bir silueti verir.
        rotation, squash_x, squash_y = {
            0: (0, 1.0, 1.0),
            1: (0, 1.0, 1.0),
            2: (-90, 1.0, 0.45),
            3: (90, 1.0, 0.45),
            4: (0, 1.0, 0.42),
            5: (180, 1.0, 0.42),
            6: (180, 1.0, 1.0),
        }.get(self.pose, (0, 1.0, 1.0))
        painter.rotate(rotation)
        painter.scale(squash_x, squash_y)

        upside_down = self.pose == 6
        fill = qcolor(COLORS.surface_3) if upside_down else qcolor(COLORS.accent, 60)
        painter.setBrush(fill)
        painter.setPen(QPen(qcolor(COLORS.accent), 2.0))
        painter.drawPolygon(self._hull())

        if not upside_down:
            painter.setBrush(qcolor(COLORS.accent))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(0, -22), 5, 5)  # burun isareti
        painter.restore()

        # Adim noktalari
        painter.setPen(Qt.PenStyle.NoPen)
        dot_y = 158.0
        total = 6
        spacing = 22
        start = cx - (total - 1) * spacing / 2
        for step in range(1, total + 1):
            x = start + (step - 1) * spacing
            if step in self.done:
                painter.setBrush(qcolor(COLORS.success))
            elif step == self.pose:
                painter.setBrush(qcolor(COLORS.accent))
            else:
                painter.setBrush(qcolor(COLORS.border_default))
            painter.drawEllipse(QPointF(x, dot_y), 5, 5)

        painter.setPen(qcolor(COLORS.text_secondary))
        painter.setFont(QFont(self.font().family(), Type.label, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(0, 172, self.width(), 20),
            Qt.AlignmentFlag.AlignCenter,
            self.POSE_NAMES.get(self.pose, ""),
        )
        painter.end()


class CompassCoverageRing(QWidget):
    """Tek bir pusulanin kalibrasyon kapsamini gosteren halka."""

    def __init__(self, compass_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(118, 132)
        self.compass_id = compass_id
        self.percent = 0
        self.status = 0
        self.fitness: float | None = None

    def set_progress(self, percent: int, status: int) -> None:
        self.percent = max(0, min(100, percent))
        self.status = status
        self.update()

    def set_report(self, status: int, fitness: float) -> None:
        self.status = status
        self.fitness = fitness
        self.percent = 100
        self.update()

    def reset(self) -> None:
        self.percent = 0
        self.status = 0
        self.fitness = None
        self.update()

    def _tone(self) -> str:
        if self.status == 4:          # MAG_CAL_SUCCESS
            return COLORS.success
        if self.status in (5, 6, 7):  # FAILED / BAD_ORIENTATION / BAD_RADIUS
            return COLORS.danger
        return COLORS.accent

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(14, 10, 90, 90)

        painter.setPen(QPen(qcolor(COLORS.surface_3), 9))
        painter.drawArc(box, 0, 360 * 16)

        if self.percent:
            painter.setPen(QPen(qcolor(self._tone()), 9, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawArc(box, 90 * 16, -int(360 * 16 * self.percent / 100))

        painter.setPen(qcolor(COLORS.text_primary))
        painter.setFont(QFont(mono_font_family(), Type.heading, QFont.Weight.Bold))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, f"{self.percent}%")

        painter.setPen(qcolor(COLORS.text_tertiary))
        painter.setFont(QFont(self.font().family(), Type.micro, QFont.Weight.Bold))
        painter.drawText(
            QRectF(0, 104, self.width(), 14),
            Qt.AlignmentFlag.AlignCenter,
            f"PUSULA {self.compass_id + 1}",
        )
        if self.fitness is not None:
            painter.setPen(qcolor(self._tone()))
            painter.drawText(
                QRectF(0, 117, self.width(), 14),
                Qt.AlignmentFlag.AlignCenter,
                f"fitness {self.fitness:.1f}",
            )
        painter.end()


class MotorLayoutView(QWidget):
    """Iki motorlu katamaran semasi; test edilen motor vurgulanir."""

    motor_clicked = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(206)
        self.active = 0
        self.labels = {1: "SOL", 2: "SAĞ"}
        # Aractan okunan gercek port; bulununcaya kadar "?" gosterilir —
        # SERVO1/SERVO3 varsayimini kanit gibi sunmamak icin.
        self.port_labels = {1: "?", 2: "?"}
        self.assigned = {1: False, 2: False}

    def set_active(self, motor: int) -> None:
        self.active = motor
        self.update()

    def set_port_label(self, motor: int, text: str, assigned: bool) -> None:
        self.port_labels[motor] = text
        self.assigned[motor] = assigned
        self.update()

    def mousePressEvent(self, event) -> None:
        for motor, rect in self._motor_rects().items():
            if rect.contains(event.position()):
                self.motor_clicked.emit(motor)
                return

    def _motor_rects(self) -> dict[int, QRectF]:
        cx = self.width() / 2
        return {
            1: QRectF(cx - 74, 104, 46, 46),
            2: QRectF(cx + 28, 104, 46, 46),
        }

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() / 2

        # Iki gövde (katamaran)
        painter.setPen(QPen(qcolor(COLORS.border_strong), 2))
        painter.setBrush(qcolor(COLORS.surface_2))
        for dx in (-51, 29):
            path = QPainterPath()
            path.moveTo(cx + dx + 11, 16)
            path.lineTo(cx + dx + 22, 46)
            path.lineTo(cx + dx + 22, 122)
            path.lineTo(cx + dx, 122)
            path.lineTo(cx + dx, 46)
            path.closeSubpath()
            painter.drawPath(path)

        # Güverte köprüsü
        painter.setBrush(qcolor(COLORS.surface_3))
        painter.drawRect(QRectF(cx - 30, 58, 60, 34))

        painter.setPen(qcolor(COLORS.text_tertiary))
        painter.setFont(QFont(self.font().family(), Type.micro, QFont.Weight.Bold))
        painter.drawText(QRectF(cx - 30, 58, 60, 34), Qt.AlignmentFlag.AlignCenter, "BAŞ")

        for motor, rect in self._motor_rects().items():
            live = motor == self.active
            known = self.assigned.get(motor, False)
            ring = COLORS.accent if live else (COLORS.border_strong if known else COLORS.warning)
            painter.setBrush(qcolor(COLORS.accent if live else COLORS.surface_3))
            painter.setPen(QPen(qcolor(ring), 2))
            painter.drawEllipse(rect)
            painter.setPen(qcolor(COLORS.text_on_accent if live else COLORS.text_secondary))
            painter.setFont(QFont(self.font().family(), Type.micro, QFont.Weight.Bold))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.labels[motor])

            # Port etiketi — canli, aractan okunan gercek deger. UI fontu
            # kullanilir: dar govdeli mono fontlarin "M" harfi bu punto ve
            # kalinlikta sikisip okunmaz hale geliyordu (olcerek görüldü).
            port_text = self.port_labels.get(motor, "?")
            painter.setPen(qcolor(COLORS.text_primary if known else COLORS.warning))
            painter.setFont(QFont(self.font().family(), Type.caption, QFont.Weight.DemiBold))
            painter.drawText(
                QRectF(rect.left() - 24, rect.bottom() + 4, rect.width() + 48, 18),
                Qt.AlignmentFlag.AlignCenter,
                port_text,
            )

        painter.setPen(qcolor(COLORS.text_tertiary))
        painter.setFont(QFont(self.font().family(), Type.micro))
        painter.drawText(
            QRectF(0, 180, self.width(), 16),
            Qt.AlignmentFlag.AlignCenter,
            "Test etmek için bir motora tıklayın",
        )
        painter.end()


class StepStrip(QWidget):
    """Bir kalibrasyonun kac adimda nerede oldugunu gosteren serit."""

    def __init__(self, steps: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.steps = steps
        self.current = -1
        self.setFixedHeight(46)

    def set_current(self, index: int) -> None:
        self.current = index
        self.update()

    def paintEvent(self, _event) -> None:
        if not self.steps:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        slot = self.width() / len(self.steps)

        for index, text in enumerate(self.steps):
            cx = slot * index + slot / 2
            done = index < self.current
            live = index == self.current
            if index:
                painter.setPen(QPen(
                    qcolor(COLORS.accent if done or live else COLORS.border_default), 2))
                painter.drawLine(QPointF(cx - slot + 11, 15), QPointF(cx - 11, 15))

            painter.setPen(Qt.PenStyle.NoPen)
            if done:
                painter.setBrush(qcolor(COLORS.success))
            elif live:
                painter.setBrush(qcolor(COLORS.accent))
            else:
                painter.setBrush(qcolor(COLORS.surface_3))
            painter.drawEllipse(QPointF(cx, 15), 9, 9)

            painter.setPen(qcolor(
                COLORS.text_on_accent if (done or live) else COLORS.text_tertiary))
            painter.setFont(QFont(self.font().family(), Type.micro, QFont.Weight.Bold))
            painter.drawText(QRectF(cx - 9, 6, 18, 18),
                             Qt.AlignmentFlag.AlignCenter, str(index + 1))

            painter.setPen(qcolor(
                COLORS.text_primary if live else COLORS.text_tertiary))
            painter.setFont(QFont(self.font().family(), Type.micro,
                                  QFont.Weight.DemiBold if live else QFont.Weight.Normal))
            painter.drawText(QRectF(cx - slot / 2, 28, slot, 16),
                             Qt.AlignmentFlag.AlignCenter, text)
        painter.end()

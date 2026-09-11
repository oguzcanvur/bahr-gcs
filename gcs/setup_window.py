"""Araç kurulum ve kalibrasyon penceresi.

Mission Planner'ın "Initial Setup" ekranının bu proje için yazılmış karşılığı:
parametre okuma/yazma, kumanda kalibrasyonu, ivmeölçer ve pusula
kalibrasyonu, motor testi ve failsafe/sonar/batarya ayarları — hepsi bu
arayüzden, başka bir yer istasyonuna ihtiyaç duymadan.

Ayrı bir pencere olarak açılır: içerik (pusula küresi, RC çubukları, 6
pozisyonlu duruş çizimi) ana penceredeki 340 px'lik yan panele sığmaz ve
harita görünürken kurulum yapabilmek işe yarar.

Protokol tarafı gcs/mavlink_worker.py içinde; buradaki her ekran yalnızca
oradaki sinyalleri dinler ve komutları çağırır.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gcs.components import Card, StatusPill, button, field_label, h_divider, section_label
from gcs.param_meta import GROUPS, BY_NAME, ParamInfo, describe, format_value
from gcs.servo_ports import function_label, motor_test_order, physical_port
from gcs.setup_widgets import (
    BoatPoseView,
    CompassCoverageRing,
    InfoDot,
    MotorLayoutView,
    RcChannelBar,
    StepStrip,
)
from gcs.theme import APP_NAME, COLORS, Space, Type, app_icon, mono_font_family


def same_value(shown: float, stored: float, decimals: int | None = None) -> bool:
    """İki parametre değeri "aynı" mı — float32 yuvarlamasını hesaba katarak.

    MAVLink parametreleri float32 taşır: araçtaki 0.9, GCS'e
    0.89999997615814209 olarak gelir. Ekrandaki kutu bunu 0.90 diye gösterir
    ve geri okurken tam 0.9 (double) döner. Katı bir eşitlik testi bu farkı
    "kullanıcı değiştirdi" sanar; kimse dokunmadığı hâlde satırlar değişmiş
    görünür ve "Araca yaz" dokunulmamış parametreleri yazar.

    Bu yüzden karşılaştırma, değerin gösterildiği hassasiyette yapılır.
    """
    if decimals is not None:
        tolerance = max(10.0 ** -decimals / 2.0, abs(stored) * 1e-6)
    else:
        tolerance = max(1e-6, abs(stored) * 1e-6)
    return abs(shown - stored) <= tolerance


# ---------------------------------------------------------------------------
# Tek parametre satiri
# ---------------------------------------------------------------------------

class ParamRow(QWidget):
    """Ad + Turkce baslik + bilgi isareti + duzenleyici + aracin degeri."""

    edited = pyqtSignal()

    def __init__(self, info: ParamInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.info = info
        self.vehicle_value: float | None = None
        self._suppress = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Space.sm)

        text = QWidget()
        text_layout = QVBoxLayout(text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(Space.xs)
        title = QLabel(info.label)
        title.setObjectName("fieldLabel")
        top.addWidget(title)
        top.addWidget(InfoDot(describe(info.name)))
        if info.reboot_required:
            flag = QLabel("yeniden başlatma gerekir")
            flag.setStyleSheet(
                f"color: {COLORS.warning}; font-size: {Type.micro}px; font-weight: 600;"
            )
            top.addWidget(flag)
        top.addStretch(1)
        text_layout.addLayout(top)

        name = QLabel(info.name)
        name.setStyleSheet(
            f"font-family: '{mono_font_family()}'; font-size: {Type.micro}px;"
            f"color: {COLORS.text_tertiary};"
        )
        text_layout.addWidget(name)
        layout.addWidget(text, 1)

        if info.choices:
            self.editor: QWidget = QComboBox()
            for value, label in sorted(info.choices.items()):
                self.editor.addItem(label, value)
            self.editor.setMinimumWidth(210)
            self.editor.currentIndexChanged.connect(self._on_edited)
        else:
            spin = QDoubleSpinBox()
            spin.setDecimals(info.decimals)
            spin.setSingleStep(info.step)
            spin.setMinimum(info.minimum if info.minimum is not None else -1e9)
            spin.setMaximum(info.maximum if info.maximum is not None else 1e9)
            if info.unit:
                spin.setSuffix(f" {info.unit}")
            spin.setMinimumWidth(150)
            spin.valueChanged.connect(self._on_edited)
            self.editor = spin
        layout.addWidget(self.editor)

        self.vehicle_label = QLabel("—")
        self.vehicle_label.setFixedWidth(92)
        self.vehicle_label.setAlignment(Qt.AlignmentFlag.AlignRight
                                        | Qt.AlignmentFlag.AlignVCenter)
        self.vehicle_label.setStyleSheet(
            f"font-family: '{mono_font_family()}'; font-size: {Type.caption}px;"
            f"color: {COLORS.text_tertiary};"
        )
        layout.addWidget(self.vehicle_label)

    def _on_edited(self) -> None:
        if self._suppress:
            return
        self._refresh_dirty_style()
        self.edited.emit()

    def set_vehicle_value(self, value: float) -> None:
        self.vehicle_value = value
        self.vehicle_label.setText(f"{value:g}")
        self._suppress = True
        if isinstance(self.editor, QComboBox):
            index = self.editor.findData(int(round(value)))
            if index >= 0:
                self.editor.setCurrentIndex(index)
            else:
                # Araçtaki değer bizim listemizde yok — uydurmak yerine göster.
                self.editor.addItem(f"{value:g} — (tanımsız)", int(round(value)))
                self.editor.setCurrentIndex(self.editor.count() - 1)
        else:
            self.editor.setValue(value)
        self._suppress = False
        self._refresh_dirty_style()

    def current_value(self) -> float:
        if isinstance(self.editor, QComboBox):
            return float(self.editor.currentData())
        return float(self.editor.value())

    def is_dirty(self) -> bool:
        if self.vehicle_value is None:
            return False
        if isinstance(self.editor, QComboBox):
            return int(round(self.current_value())) != int(round(self.vehicle_value))
        return not same_value(self.current_value(), self.vehicle_value, self.info.decimals)

    def _refresh_dirty_style(self) -> None:
        dirty = self.is_dirty()
        self.vehicle_label.setStyleSheet(
            f"font-family: '{mono_font_family()}'; font-size: {Type.caption}px;"
            f"color: {COLORS.warning if dirty else COLORS.text_tertiary};"
        )


# ---------------------------------------------------------------------------
# Sayfa temeli
# ---------------------------------------------------------------------------

class SetupPage(QWidget):
    """Kaydirilabilir govde + alt aksiyon serisi olan sayfa iskeleti."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(Space.xl, Space.lg, Space.xl, Space.lg)
        outer.setSpacing(Space.md)

        heading = QLabel(title)
        heading.setStyleSheet(
            f"font-size: {Type.title}px; font-weight: 700; color: {COLORS.text_primary};"
        )
        outer.addWidget(heading)
        if subtitle:
            note = QLabel(subtitle)
            note.setWordWrap(True)
            note.setStyleSheet(
                f"font-size: {Type.label}px; color: {COLORS.text_secondary};"
            )
            outer.addWidget(note)
        outer.addWidget(h_divider())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        holder = QWidget()
        self.body = QVBoxLayout(holder)
        self.body.setContentsMargins(0, 0, Space.sm, 0)
        self.body.setSpacing(Space.md)
        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)

        self.actions = QHBoxLayout()
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(Space.sm)
        self.actions.addStretch(1)
        outer.addLayout(self.actions)

    def on_parameter(self, name: str, value: float) -> None:
        """Araçtan bir parametre geldiğinde çağrılır."""

    def on_shown(self) -> None:
        """Sayfa görünür olduğunda çağrılır."""

    def on_hidden(self) -> None:
        """Başka sayfaya geçilirken çağrılır."""


class ParamGroupPage(SetupPage):
    """param_meta.GROUPS içindeki bir grubu düzenleyen sayfa."""

    def __init__(self, mavlink, title: str, infos: list[ParamInfo],
                 subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(title, subtitle, parent)
        self._mavlink = mavlink
        self.rows: dict[str, ParamRow] = {}

        # The divider sits *above* its row (none above the first), so a row and
        # its divider can be hidden together.
        self._dividers: dict[str, QWidget] = {}
        card = Card("Parametreler")
        for index, info in enumerate(infos):
            if index:
                self._dividers[info.name] = card.add(h_divider())
            row = ParamRow(info)
            row.edited.connect(self._refresh_actions)
            self.rows[info.name] = row
            card.add(row)
        self.body.addWidget(card)
        self.body.addStretch(1)

        self.dirty_label = QLabel("")
        self.dirty_label.setStyleSheet(
            f"color: {COLORS.warning}; font-size: {Type.label}px; font-weight: 600;"
        )
        self.actions.insertWidget(0, self.dirty_label)
        self.revert_button = button("Değişiklikleri geri al", "quiet", self._revert)
        self.write_button = button("Araca yaz", "primary", self._write)
        self.actions.addWidget(self.revert_button)
        self.actions.addWidget(self.write_button)
        self._refresh_actions()

    def on_parameter(self, name: str, value: float) -> None:
        row = self.rows.get(name)
        if row is not None:
            row.set_vehicle_value(value)
            self._refresh_actions()

    def apply_vehicle_param_set(self, names: set[str]) -> None:
        """Hide rows for parameters this vehicle's firmware does not have.

        ArduPilot renames parameters between releases (GPS_TYPE became
        GPS1_TYPE, RNGFND1_MIN_CM became RNGFND1_MIN, ...), so param_meta
        defines both names. Once the full table has arrived we know which one
        this firmware actually uses; the other row would otherwise sit there
        showing "—" forever and could never be written.
        """
        if not names:
            return  # download failed or empty — don't blank the page
        first_visible = True
        for name, row in self.rows.items():
            present = name in names
            row.setVisible(present)
            divider = self._dividers.get(name)
            if divider is not None:
                divider.setVisible(present and not first_visible)
            if present:
                first_visible = False

    def _dirty_rows(self) -> list[ParamRow]:
        return [row for row in self.rows.values() if row.is_dirty()]

    def _refresh_actions(self) -> None:
        dirty = self._dirty_rows()
        self.write_button.setEnabled(bool(dirty))
        self.revert_button.setEnabled(bool(dirty))
        self.dirty_label.setText(
            f"{len(dirty)} değişiklik yazılmayı bekliyor" if dirty else ""
        )

    def _revert(self) -> None:
        for row in self.rows.values():
            if row.vehicle_value is not None:
                row.set_vehicle_value(row.vehicle_value)
        self._refresh_actions()

    def _write(self) -> None:
        dirty = self._dirty_rows()
        reboot = [row.info.name for row in dirty if row.info.reboot_required]
        if reboot:
            answer = QMessageBox.question(
                self, "Yeniden başlatma gerekiyor",
                "Şu parametreler ancak otopilot yeniden başlatıldıktan sonra "
                "etkili olur:\n\n  " + "\n  ".join(reboot) + "\n\nYine de yazılsın mı?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        for row in dirty:
            self._mavlink.set_parameter(row.info.name, row.current_value())

    def on_shown(self) -> None:
        for name in self.rows:
            self._mavlink.request_parameter(name)


# ---------------------------------------------------------------------------
# Genel bakis
# ---------------------------------------------------------------------------

class OverviewPage(SetupPage):
    def __init__(self, mavlink, parent: QWidget | None = None) -> None:
        super().__init__(
            "Genel bakış",
            "Kurulum sırası yukarıdan aşağıya izlenmek üzere dizilmiştir. "
            "Kalibrasyonların hepsi araç DISARM iken yapılır — ArduPilot arm "
            "durumundayken kalibrasyon komutlarını reddeder.",
            parent,
        )
        self._mavlink = mavlink

        checklist = Card("Kurulum sırası")
        steps = [
            ("1. Gövde ve motor çıkışları",
             "Aracın tekne olduğunu ve hangi pinin hangi motoru sürdüğünü tanımlayın. "
             "Bu yanlışsa diğer her şey yanlış çalışır."),
            ("2. Kumanda (RC) kalibrasyonu",
             "Kumanda çubuklarının uç değerlerini öğretin."),
            ("3. İvmeölçer kalibrasyonu",
             "6 pozisyonlu kalibrasyon; aracın yatay referansını kurar."),
            ("4. Pusula kalibrasyonu",
             "Aracı her eksende çevirerek manyetik sapmaları ölçtürün."),
            ("5. Uçuş modları ve failsafe",
             "Mod anahtarını ve arıza davranışını ayarlayın."),
            ("6. Seyir ve kontrol ayarları",
             "Tarama hızları, dönüş yarıçapı ve direksiyon kazançları."),
            ("7. Sonar / derinlik ölçer",
             "Batimetri verisinin geldiği sensörü tanımlayın."),
        ]
        for index, (title, note) in enumerate(steps):
            if index:
                checklist.add_divider()
            item = QWidget()
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(2)
            head = QLabel(title)
            head.setStyleSheet(
                f"font-size: {Type.body}px; font-weight: 700; color: {COLORS.text_primary};"
            )
            body = QLabel(note)
            body.setWordWrap(True)
            body.setStyleSheet(
                f"font-size: {Type.label}px; color: {COLORS.text_secondary};"
            )
            item_layout.addWidget(head)
            item_layout.addWidget(body)
            checklist.add(item)
        self.body.addWidget(checklist)

        warning = Card("Güvenlik")
        note = QLabel(
            "• Motor testi ve kalibrasyon sırasında pervanelerin dönebileceğini "
            "unutmayın — tekneyi karada test ederken pervaneleri sökün veya "
            "gövdeyi sabitleyin.\n"
            "• İvmeölçer kalibrasyonu aracı fiziksel olarak altı ayrı duruşa "
            "getirmenizi ister; kabloların gerilmediğinden emin olun.\n"
            "• Pusula kalibrasyonunu metal masa, hoparlör veya güç kablolarından "
            "uzakta yapın; aksi halde ölçüm bozulur ve araç yönünü şaşırır."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COLORS.text_secondary}; font-size: {Type.label}px;")
        warning.add(note)
        self.body.addWidget(warning)
        self.body.addStretch(1)


# ---------------------------------------------------------------------------
# Kumanda kalibrasyonu
# ---------------------------------------------------------------------------

class RadioPage(SetupPage):
    """Canli RC_CHANNELS okuyup min/max yakalar ve RCn_* olarak yazar."""

    CHANNELS = 8

    def __init__(self, mavlink, parent: QWidget | None = None) -> None:
        super().__init__(
            "Kumanda (RC) kalibrasyonu",
            "Kalibrasyonu başlatın, sonra her çubuğu ve anahtarı uçtan uca birkaç "
            "kez gezdirin. Arayüz her kanalın gördüğü en küçük ve en büyük değeri "
            "yakalar; bitirdiğinizde bunlar RCn_MIN / RCn_MAX olarak araca yazılır, "
            "çubuklar serbestken okunan değer de RCn_TRIM olur.",
            parent,
        )
        self._mavlink = mavlink
        self._capturing = False
        self._latest: list[int] = []

        self.state_pill = StatusPill("BEKLEMEDE", "neutral")
        bars = Card("Kanallar")
        bars.add_header_widget(self.state_pill)
        self.bars: list[RcChannelBar] = []
        for index in range(self.CHANNELS):
            bar = RcChannelBar(f"CH{index + 1}")
            self.bars.append(bar)
            bars.add(bar)
        self.body.addWidget(bars)

        self.hint = QLabel(
            "Kalibrasyonu başlatmadan önce vericinizin açık ve alıcıya bağlı "
            "olduğundan emin olun. Değerler hareket etmiyorsa bağlantı yoktur."
        )
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet(f"color: {COLORS.text_tertiary}; font-size: {Type.label}px;")
        self.body.addWidget(self.hint)
        self.body.addStretch(1)

        self.start_button = button("Kalibrasyonu başlat", "primary", self._start)
        self.finish_button = button("Bitir ve araca yaz", "default", self._finish)
        self.cancel_button = button("Vazgeç", "quiet", self._cancel)
        self.finish_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        for widget in (self.cancel_button, self.finish_button, self.start_button):
            self.actions.addWidget(widget)

    def on_shown(self) -> None:
        self._mavlink.set_rc_monitor(True)

    def on_hidden(self) -> None:
        self._mavlink.set_rc_monitor(False)
        if self._capturing:
            self._cancel()

    def on_rc_channels(self, channels: list[int]) -> None:
        self._latest = channels
        for index, bar in enumerate(self.bars):
            if index < len(channels):
                bar.set_value(channels[index], self._capturing)

    def _start(self) -> None:
        self._capturing = True
        for bar in self.bars:
            bar.reset()
        self._mavlink.set_rc_calibrating(True)
        self.state_pill.set_state("ÇUBUKLARI GEZDİRİN", "accent")
        self.start_button.setEnabled(False)
        self.finish_button.setEnabled(True)
        self.cancel_button.setEnabled(True)

    def _cancel(self) -> None:
        self._capturing = False
        self._mavlink.set_rc_calibrating(False)
        self.state_pill.set_state("BEKLEMEDE", "neutral")
        self.start_button.setEnabled(True)
        self.finish_button.setEnabled(False)
        self.cancel_button.setEnabled(False)

    def captured_ranges(self) -> dict[str, int]:
        """Yazilacak RCn_MIN / RCn_MAX / RCn_TRIM degerleri."""
        values: dict[str, int] = {}
        for index, bar in enumerate(self.bars, start=1):
            if not bar.captured or bar.maximum - bar.minimum < 50:
                # Hiç hareket etmemiş bir kanalı kalibre edilmiş gibi yazmak,
                # o kanalı kullanılamaz hale getirir.
                continue
            values[f"RC{index}_MIN"] = bar.minimum
            values[f"RC{index}_MAX"] = bar.maximum
            values[f"RC{index}_TRIM"] = (
                self._latest[index - 1] if index - 1 < len(self._latest) else bar.trim
            )
        return values

    def off_centre_channels(self) -> list[str]:
        """Kanallari, trim'i araligin ucuna yakin olanlar olarak dondurur.

        Trim, cubuklar serbestken okunan degerdir. Operator cubugu ucta
        tutarken 'Bitir'e basarsa araca 'notr = tam saga kirik' diye yazilir
        ve tekne kumanda ortadayken sert donmeye baslar. Sessizce yazmak
        yerine uyariyoruz.
        """
        suspect = []
        for index, bar in enumerate(self.bars, start=1):
            if not bar.captured or bar.maximum - bar.minimum < 50:
                continue
            trim = self._latest[index - 1] if index - 1 < len(self._latest) else bar.trim
            span = bar.maximum - bar.minimum
            if trim - bar.minimum < span * 0.2 or bar.maximum - trim < span * 0.2:
                suspect.append(f"CH{index}")
        return suspect

    def _finish(self) -> None:
        values = self.captured_ranges()
        if not values:
            QMessageBox.warning(
                self, "Hareket görülmedi",
                "Hiçbir kanalda anlamlı hareket yakalanmadı. Verici açık mı ve "
                "alıcıya bağlı mı kontrol edip tekrar deneyin.",
            )
            return
        moved = len(values) // 3
        off_centre = self.off_centre_channels()
        warning = ""
        if off_centre:
            warning = (
                f"\n\n⚠  Şu kanallarda çubuk şu anda ortada değil: "
                f"{', '.join(off_centre)}.\nBu haliyle yazarsanız araç, kumanda "
                "serbestken bile o yöne komut alıyor sanır. Çubukları bırakıp "
                "tekrar deneyin."
            )
        answer = QMessageBox.question(
            self, "Kalibrasyonu yaz",
            f"{moved} kanal için min/max/trim değerleri araca yazılacak.\n\n"
            "Çubukların şu anda serbest (orta) konumda olduğundan emin olun — "
            "trim değeri o anki okumadan alınır." + warning,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for name, value in values.items():
            self._mavlink.set_parameter(name, float(value))
        self._cancel()
        self.state_pill.set_state("YAZILDI", "success")


# ---------------------------------------------------------------------------
# Ivmeolcer kalibrasyonu
# ---------------------------------------------------------------------------

class AccelPage(SetupPage):
    def __init__(self, mavlink, parent: QWidget | None = None) -> None:
        super().__init__(
            "İvmeölçer kalibrasyonu",
            "Araç altı ayrı duruşa getirilir ve her duruşta ivmeölçer okunur. "
            "Otopilot hangi duruşu istediğini kendisi söyler; aşağıdaki çizim onu "
            "gösterir. Her duruşta aracı sabit tutup 'Bu pozisyondayım'a basın.",
            parent,
        )
        self._mavlink = mavlink
        self._running = False
        self._step = 0

        self.pose_view = BoatPoseView()
        pose_card = Card("İstenen duruş")
        self.pose_pill = StatusPill("BAŞLATILMADI", "neutral")
        pose_card.add_header_widget(self.pose_pill)
        pose_card.add(self.pose_view)
        self.body.addWidget(pose_card)

        self.vehicle_says = QLabel("—")
        self.vehicle_says.setWordWrap(True)
        self.vehicle_says.setStyleSheet(
            f"font-family: '{mono_font_family()}'; font-size: {Type.caption}px;"
            f"color: {COLORS.text_secondary};"
        )
        says = Card("Aracın söyledikleri")
        says.add(self.vehicle_says)
        self.body.addWidget(says)

        quick = Card("Hızlı kalibrasyonlar")
        for text, note, slot in (
            ("Jiroskop", "Aracı hareketsiz bırakıp çalıştırın. Birkaç saniye sürer.",
             self._mavlink.calibrate_gyro),
            ("Yatay referans (level)",
             "Aracı gerçekten yatay bir zemine koyun; bu duruşu 'düz' kabul eder.",
             self._mavlink.calibrate_level),
            ("Basit ivmeölçer",
             "Tam 6 pozisyonun kısaltılmış hâli; yalnızca kaba düzeltme yapar.",
             self._mavlink.calibrate_accel_simple),
            ("Barometre / zemin basıncı",
             "Mevcut basıncı sıfır kabul eder.", self._mavlink.calibrate_baro),
        ):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(Space.sm)
            text_box = QWidget()
            text_layout = QVBoxLayout(text_box)
            text_layout.setContentsMargins(0, 0, 0, 0)
            text_layout.setSpacing(0)
            head = QLabel(text)
            head.setObjectName("fieldLabel")
            sub = QLabel(note)
            sub.setWordWrap(True)
            sub.setStyleSheet(
                f"color: {COLORS.text_tertiary}; font-size: {Type.micro}px;"
            )
            text_layout.addWidget(head)
            text_layout.addWidget(sub)
            row_layout.addWidget(text_box, 1)
            row_layout.addWidget(button("Çalıştır", "quiet", slot))
            quick.add(row)
            quick.add_divider()
        self.body.addWidget(quick)
        self.body.addStretch(1)

        self.start_button = button("6 pozisyonlu kalibrasyonu başlat", "primary", self._start)
        self.confirm_button = button("Bu pozisyondayım →", "default", self._confirm)
        self.confirm_button.setEnabled(False)
        self.actions.addWidget(self.confirm_button)
        self.actions.addWidget(self.start_button)

    def _start(self) -> None:
        self._running = True
        self._step = 0
        self.pose_view.reset()
        self.vehicle_says.setText("—")
        self.pose_pill.set_state("BAŞLATILIYOR", "info")
        self.start_button.setEnabled(False)
        self._mavlink.start_accel_calibration()

    def _confirm(self) -> None:
        if self._step:
            self._mavlink.confirm_accel_position(self._step)
            self.confirm_button.setEnabled(False)
            self.pose_pill.set_state("OKUNUYOR…", "info")

    def on_accel_position(self, step: int) -> None:
        if step == 16777215:      # ACCELCAL_VEHICLE_POS_SUCCESS
            self._finish("KALİBRASYON BAŞARILI", "success")
            return
        if step == 16777216:      # ..._FAILED
            self._finish("KALİBRASYON BAŞARISIZ", "danger")
            return
        if not 1 <= step <= 6:
            return
        self._running = True
        self._step = step
        self.pose_view.set_pose(step)
        self.pose_pill.set_state(f"POZİSYON {step}/6", "accent")
        self.confirm_button.setEnabled(True)
        self.start_button.setEnabled(False)

    def _finish(self, text: str, tone: str) -> None:
        self._running = False
        self._step = 0
        self.pose_view.set_pose(0)
        self.pose_pill.set_state(text, tone)
        self.confirm_button.setEnabled(False)
        self.start_button.setEnabled(True)

    # Kalibrasyonla ilgisi olan mesajlar. Aracin her STATUSTEXT'ini buraya
    # basmak, pusula kalibrasyonundan kalan bir satirin ivmeolcer ekraninda
    # duruyor gorunmesine yol aciyordu.
    _RELEVANT = ("Place vehicle", "Calibration", "calibration", "Disarm",
                 "accel", "Accel", "gyro", "Gyro", "Level", "level")

    def on_statustext(self, _severity: int, text: str) -> None:
        if "ompass" in text:
            return
        if any(token in text for token in self._RELEVANT):
            self.vehicle_says.setText(text)


# ---------------------------------------------------------------------------
# Pusula kalibrasyonu
# ---------------------------------------------------------------------------

class CompassPage(SetupPage):
    def __init__(self, mavlink, parent: QWidget | None = None) -> None:
        super().__init__(
            "Pusula kalibrasyonu",
            "Başlattıktan sonra aracı yavaşça her eksende çevirin — burnu yukarı, "
            "aşağı, yan yatık ve her yöne dönerek. Amaç manyetik alanı bir küre "
            "gibi taramaktır; halkalar tarama oranını gösterir. Metal yüzeylerden "
            "ve güç kablolarından uzak durun.",
            parent,
        )
        self._mavlink = mavlink

        rings = Card("Kapsama")
        self.state_pill = StatusPill("BAŞLATILMADI", "neutral")
        rings.add_header_widget(self.state_pill)
        ring_row = QWidget()
        ring_layout = QHBoxLayout(ring_row)
        ring_layout.setContentsMargins(0, 0, 0, 0)
        ring_layout.setSpacing(Space.lg)
        self.rings: dict[int, CompassCoverageRing] = {}
        for compass_id in (0, 1, 2):
            ring = CompassCoverageRing(compass_id)
            # Araçta kaç pusula olduğunu ancak rapor verince biliriz; hiç
            # konuşmayan bir pusulayı "%0" diye göstermek, kalibrasyon
            # başarısız olmuş gibi okunuyor.
            ring.hide()
            self.rings[compass_id] = ring
            ring_layout.addWidget(ring)
        self.no_compass_label = QLabel("Henüz hiçbir pusuladan yanıt gelmedi.")
        self.no_compass_label.setStyleSheet(
            f"color: {COLORS.text_tertiary}; font-size: {Type.label}px;"
        )
        ring_layout.addWidget(self.no_compass_label)
        ring_layout.addStretch(1)
        rings.add(ring_row)
        self.body.addWidget(rings)

        self.report_label = QLabel("Henüz sonuç yok.")
        self.report_label.setWordWrap(True)
        self.report_label.setStyleSheet(
            f"color: {COLORS.text_secondary}; font-size: {Type.label}px;"
        )
        report = Card("Sonuç")
        report.add(self.report_label)
        self.body.addWidget(report)
        self.body.addStretch(1)

        self.start_button = button("Kalibrasyonu başlat", "primary", self._start)
        self.accept_button = button("Kabul et", "default", self._accept)
        self.cancel_button = button("İptal", "quiet", self._cancel)
        self.accept_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        for widget in (self.cancel_button, self.accept_button, self.start_button):
            self.actions.addWidget(widget)

    def _start(self) -> None:
        for ring in self.rings.values():
            ring.reset()
        self.report_label.setText("Aracı her eksende yavaşça çevirin…")
        self.state_pill.set_state("ÇEVİRİN", "accent")
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.accept_button.setEnabled(False)
        self._mavlink.start_compass_calibration(retry=True, autosave=True)

    def _accept(self) -> None:
        self._mavlink.accept_compass_calibration()
        self.state_pill.set_state("KABUL EDİLDİ", "success")
        self.accept_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def _cancel(self) -> None:
        self._mavlink.cancel_compass_calibration()
        self.state_pill.set_state("İPTAL EDİLDİ", "neutral")
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.accept_button.setEnabled(False)

    def _reveal(self, compass_id: int) -> CompassCoverageRing | None:
        ring = self.rings.get(compass_id)
        if ring is not None and ring.isHidden():
            ring.show()
            self.no_compass_label.hide()
        return ring

    def on_progress(self, data: dict) -> None:
        ring = self._reveal(data["compass_id"])
        if ring is not None:
            ring.set_progress(data["completion_pct"], data["cal_status"])
        self.state_pill.set_state("ÇEVİRİN", "accent")

    def on_report(self, data: dict) -> None:
        ring = self._reveal(data["compass_id"])
        if ring is not None:
            ring.set_report(data["cal_status"], data["fitness"])

        success = data["cal_status"] == 4
        offsets = data["offsets"]
        quality = (
            "çok iyi" if data["fitness"] < 5 else
            "kabul edilebilir" if data["fitness"] < 15 else "kötü"
        )
        message = (
            f"Pusula {data['compass_id'] + 1}: "
            f"{'başarılı' if success else 'BAŞARISIZ'} — "
            f"fitness {data['fitness']:.1f} ({quality}), "
            f"offset ({offsets[0]:.0f}, {offsets[1]:.0f}, {offsets[2]:.0f}). "
            + ("Araç değerleri kendisi kaydetti." if data["autosaved"]
               else "Kaydetmek için 'Kabul et'e basın.")
        )
        existing = self.report_label.text()
        if existing.startswith("Pusula"):
            message = existing + "\n" + message
        self.report_label.setText(message)

        self.state_pill.set_state(
            "BAŞARILI" if success else "BAŞARISIZ", "success" if success else "danger"
        )
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.accept_button.setEnabled(not data["autosaved"] and success)


# ---------------------------------------------------------------------------
# Govde, cikislar ve motor testi
# ---------------------------------------------------------------------------

class OutputsPage(ParamGroupPage):
    """Cikis atamalari + Mission Planner'daki Motor Test / Servo Output
    sayfasinin karsiligi: aractan okunan gercek SERVOn_FUNCTION degerlerine
    gore hangi fiziksel cikisin (MAIN OUT / AUX OUT) hangi gorevde oldugunu
    gosterir, ve motor testini o gorevin GERCEK DO_MOTOR_TEST numarasiyla
    gonderir.

    DO_MOTOR_TEST'in param1'i "1=sol, 2=sağ" gibi sabit degildir — ArduPilot
    kaynaginda (AR_Motors/AP_MotorsUGV.cpp, motor_test_order enum) 1=THROTTLE,
    2=STEERING, 3=THROTTLE_LEFT, 4=THROTTLE_RIGHT olarak tanimlidir. Iki
    motorlu bir teknede (SERVO1=ThrottleLeft, SERVO3=ThrottleRight) sol/sag
    motoru test etmek icin gonderilmesi gereken sayilar 3 ve 4'tur — bkz.
    gcs/servo_ports.py.
    """

    # SOL/SAĞ rolündeki motorun tasimasi gereken SRV_Channel fonksiyonu.
    _ROLE_FUNCTION = {1: 73, 2: 74}  # k_throttleLeft, k_throttleRight

    def __init__(self, mavlink, infos: list[ParamInfo], parent: QWidget | None = None) -> None:
        super().__init__(
            mavlink, "Motor çıkışları",
            infos,
            "Hangi çıkış pininin hangi motoru sürdüğünü burada tanımlarsınız. "
            "İki motorlu bir teknede sol motor ThrottleLeft (73), sağ motor "
            "ThrottleRight (74) olmalıdır — karışırsa tekne ileri gitmek yerine "
            "kendi etrafında döner.",
            parent,
        )
        self._motor_test_seconds = 2.0
        self._functions: dict[int, int] = {}

        test = Card("Motor testi")
        self.layout_view = MotorLayoutView()
        self.layout_view.motor_clicked.connect(self._test_role)
        test.add(self.layout_view)

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(Space.sm)
        controls_layout.addWidget(field_label("Gaz"))
        self.throttle_spin = QDoubleSpinBox()
        self.throttle_spin.setRange(1, 100)
        self.throttle_spin.setValue(15)
        self.throttle_spin.setDecimals(0)
        self.throttle_spin.setSuffix(" %")
        controls_layout.addWidget(self.throttle_spin)
        controls_layout.addWidget(field_label("Süre"))
        self.seconds_spin = QDoubleSpinBox()
        self.seconds_spin.setRange(0.5, 10)
        self.seconds_spin.setValue(2)
        self.seconds_spin.setDecimals(1)
        self.seconds_spin.setSuffix(" s")
        controls_layout.addWidget(self.seconds_spin)
        controls_layout.addStretch(1)
        test.add(controls)

        danger = QLabel(
            "⚠  Motor testi pervaneleri gerçekten döndürür. Test etmeden önce "
            "tekneyi sabitleyin veya pervaneleri sökün."
        )
        danger.setWordWrap(True)
        danger.setStyleSheet(f"color: {COLORS.warning}; font-size: {Type.label}px;")
        test.add(danger)

        self.port_card = Card("Port haritası")
        port_hint = QLabel(
            "Araçtan okunan gerçek SERVOn_FUNCTION değerlerine göre hangi "
            "fiziksel çıkışın (MAIN OUT / AUX OUT) hangi görevde olduğu — "
            "Mission Planner'daki Motor Test / Servo Output sayfasının "
            "karşılığı. FUNCTION değeri 0 olan (kullanılmayan) çıkışlar "
            "listelenmez."
        )
        port_hint.setWordWrap(True)
        port_hint.setStyleSheet(f"color: {COLORS.text_tertiary}; font-size: {Type.label}px;")
        self.port_card.add(port_hint)
        self.port_table = QTableWidget(0, 4)
        self.port_table.setHorizontalHeaderLabels(["Port", "Parametre", "Görev", ""])
        self.port_table.verticalHeader().setVisible(False)
        self.port_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.port_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.port_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        # ResizeToContents sized this to the cell widget's hint *before* the
        # button had been laid out, so it came out too narrow to show "Test"
        # (measured: the label rendered as a wrapped two-line sliver). A
        # fixed width sidesteps the ordering problem entirely.
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.port_table.setColumnWidth(3, 72)
        self.port_table.setMinimumHeight(160)
        self._set_port_table_placeholder("Parametreler okunuyor…")
        self.port_card.add(self.port_table)

        # Sira: Motor testi, Port haritası, sonra genel Parametreler karti
        # (zaten ParamGroupPage.__init__ tarafindan eklendi).
        self.body.insertWidget(0, test)
        self.body.insertWidget(1, self.port_card)

    # -- port haritasi -------------------------------------------------

    def _set_port_table_placeholder(self, text: str) -> None:
        self.port_table.setRowCount(1)
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.port_table.setItem(0, 0, item)
        self.port_table.setSpan(0, 0, 1, 4)

    def on_shown(self) -> None:
        super().on_shown()
        for channel in range(1, 15):
            self._mavlink.request_parameter(f"SERVO{channel}_FUNCTION")

    def on_parameter(self, name: str, value: float) -> None:
        super().on_parameter(name, value)
        if not (name.startswith("SERVO") and name.endswith("_FUNCTION")):
            return
        try:
            channel = int(name[len("SERVO"):-len("_FUNCTION")])
        except ValueError:
            return
        self._functions[channel] = int(value)
        self._rebuild_port_table()
        self._refresh_motor_labels()

    def _rebuild_port_table(self) -> None:
        used = sorted((ch, fn) for ch, fn in self._functions.items() if fn != 0)
        if not used:
            self._set_port_table_placeholder(
                "Atanmış (FUNCTION ≠ 0) bir çıkış bulunamadı."
            )
            return
        self.port_table.setRowCount(len(used))
        for row, (channel, function_id) in enumerate(used):
            self.port_table.setSpan(row, 0, 1, 1)  # önceki placeholder span'i temizle

            port_item = QTableWidgetItem(physical_port(channel))
            port_item.setFont(QFont(mono_font_family(), Type.caption, QFont.Weight.DemiBold))
            self.port_table.setItem(row, 0, port_item)

            param_item = QTableWidgetItem(f"SERVO{channel}_FUNCTION = {function_id}")
            param_item.setFont(QFont(mono_font_family(), Type.caption))
            self.port_table.setItem(row, 1, param_item)

            role_item = QTableWidgetItem(function_label(function_id))
            self.port_table.setItem(row, 2, role_item)

            order = motor_test_order(function_id)
            if order is not None:
                test_btn = button("Test", "quiet")
                test_btn.setProperty("compact", "true")
                test_btn.clicked.connect(
                    lambda _checked=False, c=channel, f=function_id: self._test_channel(c, f)
                )
                self.port_table.setCellWidget(row, 3, test_btn)
            else:
                self.port_table.setCellWidget(row, 3, None)
        self.port_table.resizeRowsToContents()

    def _refresh_motor_labels(self) -> None:
        for role, target_function in self._ROLE_FUNCTION.items():
            channel = next(
                (ch for ch, fn in self._functions.items() if fn == target_function), None
            )
            if channel is None:
                self.layout_view.set_port_label(role, "atanmamış", assigned=False)
            else:
                self.layout_view.set_port_label(role, physical_port(channel), assigned=True)

    # -- motor testi -----------------------------------------------------

    def _run_motor_test(self, order: int, description: str) -> None:
        answer = QMessageBox.question(
            self, "Motor testi",
            f"{description}\n\n%{self.throttle_spin.value():.0f} gazla "
            f"{self.seconds_spin.value():.1f} saniye çalıştırılacak.\n\n"
            "Pervane çevresinin boş olduğundan emin misiniz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._mavlink.motor_test(
            order, self.throttle_spin.value(), self.seconds_spin.value(),
            label=description.rstrip("."),
        )

    def _test_role(self, role: int) -> None:
        target_function = self._ROLE_FUNCTION[role]
        channel = next(
            (ch for ch, fn in self._functions.items() if fn == target_function), None
        )
        label = self.layout_view.labels[role]
        if channel is None:
            QMessageBox.warning(
                self, "Atanmamış çıkış",
                f"{label} motor için gerekli fonksiyon ({function_label(target_function)}) "
                "atanmış bir çıkış bulunamadı.\n\n"
                "Önce sayfadaki parametreleri araçtan okuyun, ya da çıkış "
                "atamasını kontrol edin — motor testi bu bilgi olmadan "
                "hangi pine gönderileceğini bilemez.",
            )
            return
        order = motor_test_order(target_function)  # her zaman biliniyor: 3 veya 4
        self.layout_view.set_active(role)
        self._run_motor_test(
            order,
            f"{label} motor — {physical_port(channel)} (SERVO{channel}, "
            f"{function_label(target_function)}).",
        )
        QTimer.singleShot(
            int(self.seconds_spin.value() * 1000) + 200,
            lambda: self.layout_view.set_active(0),
        )

    def _test_channel(self, channel: int, function_id: int) -> None:
        order = motor_test_order(function_id)
        if order is None:
            return
        self._run_motor_test(
            order, f"{physical_port(channel)} (SERVO{channel}, {function_label(function_id)})."
        )


# ---------------------------------------------------------------------------
# Tum parametreler
# ---------------------------------------------------------------------------

class AllParametersPage(SetupPage):
    """Araçtaki her parametre: ara, düzenle, .param dosyasına kaydet/yükle."""

    def __init__(self, mavlink, parent: QWidget | None = None) -> None:
        super().__init__(
            "Tüm parametreler",
            "Araçtan inen bütün parametreler. Gruplanmış sayfalarda görünmeyen bir "
            "parametreyi buradan arayıp değiştirebilirsiniz. Açıklaması tanımlı "
            "olanlar için satırın sonundaki değer alanının üstüne gelin.",
            parent,
        )
        self._mavlink = mavlink
        self._values: dict[str, float] = {}
        self._pending: dict[str, float] = {}

        search_row = QWidget()
        search_layout = QHBoxLayout(search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(Space.sm)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Parametre ara — ad veya açıklama içinde…")
        self.search.textChanged.connect(self._apply_filter)
        search_layout.addWidget(self.search, 1)
        self.count_label = QLabel("0 parametre")
        self.count_label.setStyleSheet(
            f"color: {COLORS.text_tertiary}; font-size: {Type.label}px;"
        )
        search_layout.addWidget(self.count_label)
        self.body.addWidget(search_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Parametre", "Değer", "Anlamı", "Açıklama"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        self.body.addWidget(self.table, 1)

        self.dirty_label = QLabel("")
        self.dirty_label.setStyleSheet(
            f"color: {COLORS.warning}; font-size: {Type.label}px; font-weight: 600;"
        )
        self.actions.insertWidget(0, self.dirty_label)
        self.actions.addWidget(button("Dosyadan yükle", "quiet", self._load_file))
        self.actions.addWidget(button("Dosyaya kaydet", "quiet", self._save_file))
        self.write_button = button("Değişiklikleri yaz", "primary", self._write)
        self.write_button.setEnabled(False)
        self.actions.addWidget(self.write_button)

    def set_parameters(self, values: dict[str, float]) -> None:
        self._values = dict(values)
        self._pending.clear()
        self._rebuild()

    def on_parameter(self, name: str, value: float) -> None:
        if name not in self._values:
            return  # tam indirme bitmeden gelen tekil okumalar tabloyu bozmasın
        if same_value(value, self._values[name]):
            return
        self._values[name] = value
        self._pending.pop(name, None)
        self._rebuild()

    def _rebuild(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for row, name in enumerate(sorted(self._values)):
            value = self._pending.get(name, self._values[name])
            self.table.insertRow(row)

            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setFont(QFont(mono_font_family(), Type.caption))
            self.table.setItem(row, 0, name_item)

            value_item = QTableWidgetItem(f"{value:g}")
            value_item.setFont(QFont(mono_font_family(), Type.caption))
            if name in self._pending:
                value_item.setForeground(Qt.GlobalColor.yellow)
            self.table.setItem(row, 1, value_item)

            meaning = QTableWidgetItem(format_value(name, value))
            meaning.setFlags(meaning.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, meaning)

            info = BY_NAME.get(name)
            summary = info.label if info is not None else ""
            note = QTableWidgetItem(summary)
            note.setFlags(note.flags() & ~Qt.ItemFlag.ItemIsEditable)
            note.setToolTip(f"<div style='max-width:460px'>{describe(name)}</div>")
            self.table.setItem(row, 3, note)
        self.table.blockSignals(False)
        self._apply_filter()
        self._refresh_actions()

    def _apply_filter(self) -> None:
        needle = self.search.text().strip().lower()
        shown = 0
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).text()
            hay = f"{name} {describe(name)} {BY_NAME.get(name).label if name in BY_NAME else ''}"
            visible = needle in hay.lower()
            self.table.setRowHidden(row, not visible)
            shown += visible
        total = self.table.rowCount()
        self.count_label.setText(
            f"{shown} / {total} parametre" if needle else f"{total} parametre"
        )

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 1:
            return
        name = self.table.item(item.row(), 0).text()
        try:
            value = float(item.text())
        except ValueError:
            item.setText(f"{self._values.get(name, 0):g}")
            return
        if same_value(value, self._values.get(name, value)):
            self._pending.pop(name, None)
        else:
            self._pending[name] = value
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        self.write_button.setEnabled(bool(self._pending))
        self.dirty_label.setText(
            f"{len(self._pending)} değişiklik yazılmayı bekliyor" if self._pending else ""
        )

    def _write(self) -> None:
        for name, value in list(self._pending.items()):
            self._mavlink.set_parameter(name, value)

    def _save_file(self) -> None:
        if not self._values:
            QMessageBox.information(self, "Boş", "Önce parametreleri indirin.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Parametreleri kaydet", "vehicle.param",
            "Parametre dosyası (*.param);;Tüm dosyalar (*)",
        )
        if not path:
            return
        lines = [f"{name},{self._values[name]:g}" for name in sorted(self._values)]
        Path(path).write_text("\n".join(lines) + "\n", encoding="ascii")
        QMessageBox.information(
            self, "Kaydedildi", f"{len(lines)} parametre şuraya yazıldı:\n{path}"
        )

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Parametre dosyası aç", "",
            "Parametre dosyası (*.param);;Tüm dosyalar (*)",
        )
        if not path:
            return
        loaded = parse_param_file(Path(path).read_text(encoding="ascii", errors="replace"))
        if not loaded:
            QMessageBox.warning(self, "Okunamadı", "Dosyada geçerli parametre bulunamadı.")
            return

        differing = {
            name: value for name, value in loaded.items()
            if name in self._values and abs(self._values[name] - value) > 1e-9
        }
        unknown = sorted(set(loaded) - set(self._values))
        if not differing:
            QMessageBox.information(
                self, "Fark yok",
                f"Dosyadaki {len(loaded)} parametre araçtakilerle aynı."
                + (f"\n\n{len(unknown)} parametre araçta yok, yok sayıldı." if unknown else ""),
            )
            return

        preview = "\n".join(
            f"  {name}: {self._values[name]:g} → {value:g}"
            for name, value in sorted(differing.items())[:20]
        )
        more = f"\n  … ve {len(differing) - 20} tane daha" if len(differing) > 20 else ""
        answer = QMessageBox.question(
            self, "Farkları uygula",
            f"{len(differing)} parametre araçtakinden farklı:\n\n{preview}{more}\n\n"
            + (f"({len(unknown)} parametre araçta yok, atlanacak.)\n\n" if unknown else "")
            + "Bu değerler düzenleme alanına yüklensin mi? "
              "(Araca yazmak için ayrıca 'Değişiklikleri yaz'a basmanız gerekir.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._pending.update(differing)
        self._rebuild()


def parse_param_file(text: str) -> dict[str, float]:
    """Mission Planner .param dosyasini okur (virgul veya bosluk ayracli)."""
    values: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace(",", " ").replace("\t", " ").split()
        if len(parts) < 2:
            continue
        try:
            values[parts[0].upper()] = float(parts[1])
        except ValueError:
            continue
    return values


# ---------------------------------------------------------------------------
# Pencere
# ---------------------------------------------------------------------------

class SetupWindow(QWidget):
    """Kurulum modullerini barindiran ayri pencere."""

    # Gruplanmis sayfalarin sirasi ve basliklari
    _GROUP_TITLES = {
        "frame": "Gövde ve kimlik",
        "outputs": "Motor çıkışları",
        "radio": "Kumanda parametreleri",
        "modes": "Uçuş modları",
        "navigation": "Seyir ayarları",
        "tuning": "Direksiyon ve hız",
        "battery": "Batarya",
        "failsafe": "Failsafe",
        "sonar": "Sonar / derinlik",
        "gps": "GPS ve pusula",
        "arming": "Arm koşulları",
    }

    def __init__(self, mavlink, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Araç Kurulumu ve Kalibrasyonu")
        # Shares the main window's root background rule so the page area sits
        # a step below the nav panel instead of matching it.
        self.setObjectName("appRoot")
        self.setWindowIcon(app_icon())
        self.resize(1180, 820)
        self.setMinimumSize(940, 640)
        self._mavlink = mavlink
        self._pages: list[SetupPage] = []
        self._current: SetupPage | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        split = QWidget()
        split_layout = QHBoxLayout(split)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setObjectName("sidePanel")
        self.nav.setFixedWidth(228)
        self.nav.setSpacing(2)
        self.nav.currentRowChanged.connect(self._on_page_changed)
        split_layout.addWidget(self.nav)

        self.stack = QStackedWidget()
        split_layout.addWidget(self.stack, 1)
        root.addWidget(split, 1)
        root.addWidget(self._build_footer())

        self._build_pages()
        self._connect_signals()
        self.nav.setCurrentRow(0)

    # -- iskelet -----------------------------------------------------------

    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("topBar")
        bar.setFixedHeight(62)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(Space.xl, Space.sm, Space.xl, Space.sm)
        layout.setSpacing(Space.md)

        title = QLabel("ARAÇ KURULUMU")
        title.setObjectName("brandMark")
        layout.addWidget(title)
        layout.addStretch(1)

        self.armed_pill = StatusPill("DURUM BİLİNMİYOR", "neutral")
        layout.addWidget(self.armed_pill)
        self.param_pill = StatusPill("PARAMETRE YOK", "neutral")
        layout.addWidget(self.param_pill)
        self.download_button = button(
            "Parametreleri indir", "primary", self._mavlink.download_parameters
        )
        layout.addWidget(self.download_button)
        return bar

    def _build_footer(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("statusStrip")
        bar.setFixedHeight(34)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(Space.xl, 0, Space.xl, 0)
        self.status_label = QLabel("Hazır.")
        self.status_label.setStyleSheet(
            f"color: {COLORS.text_tertiary}; font-size: {Type.caption}px;"
        )
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        return bar

    def _add_page(self, key: str, title: str, page: SetupPage) -> SetupPage:
        item = QListWidgetItem(title)
        item.setData(Qt.ItemDataRole.UserRole, key)
        self.nav.addItem(item)
        self.stack.addWidget(page)
        self._pages.append(page)
        return page

    def _build_pages(self) -> None:
        groups = {key: (title, infos) for key, title, infos in GROUPS}

        self.overview_page = self._add_page("overview", "Genel bakış",
                                            OverviewPage(self._mavlink))
        self._add_page("frame", self._GROUP_TITLES["frame"],
                       ParamGroupPage(self._mavlink, groups["frame"][0],
                                      groups["frame"][1]))
        self.outputs_page = self._add_page(
            "outputs", self._GROUP_TITLES["outputs"],
            OutputsPage(self._mavlink, groups["outputs"][1]))

        self.radio_page = self._add_page("radio_cal", "Kumanda kalibrasyonu",
                                         RadioPage(self._mavlink))
        self.accel_page = self._add_page("accel_cal", "İvmeölçer kalibrasyonu",
                                         AccelPage(self._mavlink))
        self.compass_page = self._add_page("compass_cal", "Pusula kalibrasyonu",
                                           CompassPage(self._mavlink))

        for key in ("radio", "modes", "navigation", "tuning", "battery",
                    "failsafe", "sonar", "gps", "arming"):
            title, infos = groups[key]
            self._add_page(key, self._GROUP_TITLES[key],
                           ParamGroupPage(self._mavlink, title, infos))

        self.all_params_page = self._add_page("all", "Tüm parametreler",
                                              AllParametersPage(self._mavlink))

    def _connect_signals(self) -> None:
        m = self._mavlink
        m.parameter_received.connect(self._on_parameter)
        m.parameters_received.connect(self._on_parameters)
        m.parameter_download.connect(self._on_download_state)
        m.statustext_received.connect(self._on_statustext)
        m.accel_position_requested.connect(self.accel_page.on_accel_position)
        m.mag_cal_progress.connect(self.compass_page.on_progress)
        m.mag_cal_report.connect(self.compass_page.on_report)
        m.rc_channels_received.connect(self.radio_page.on_rc_channels)
        m.status_updated.connect(self._on_status)

    # -- olaylar -----------------------------------------------------------

    def _on_page_changed(self, row: int) -> None:
        if not 0 <= row < len(self._pages):
            return
        if self._current is not None:
            self._current.on_hidden()
        self._current = self._pages[row]
        self.stack.setCurrentIndex(row)
        self._current.on_shown()

    def _on_parameter(self, name: str, value: float) -> None:
        for page in self._pages:
            page.on_parameter(name, value)

    def _on_parameters(self, values: dict) -> None:
        self.all_params_page.set_parameters(values)
        for name, value in values.items():
            for page in self._pages:
                if page is not self.all_params_page:
                    page.on_parameter(name, value)
        # Now that the full table is known, drop rows for parameter names this
        # firmware doesn't use (the old or new spelling of a renamed param).
        names = set(values)
        for page in self._pages:
            if isinstance(page, ParamGroupPage):
                page.apply_vehicle_param_set(names)
        self.param_pill.set_state(f"{len(values)} PARAMETRE", "success")

    def _on_download_state(self, state: str, received: int, expected: int) -> None:
        self.download_button.setEnabled(state in ("complete", "failed"))
        if state == "started":
            self.param_pill.set_state("İNDİRİLİYOR…", "info")
        elif state == "progress":
            self.param_pill.set_state(
                f"{received}/{expected or '?'}", "info"
            )
        elif state == "failed":
            self.param_pill.set_state("İNDİRİLEMEDİ", "danger")

    def _on_statustext(self, severity: int, text: str) -> None:
        self.accel_page.on_statustext(severity, text)
        self.status_label.setText(f"Araç: {text}")
        if "Disarm" in text:
            self.armed_pill.set_state("ARM — KALİBRASYON ENGELLİ", "danger")

    def _on_status(self, text: str) -> None:
        if text.startswith("[vehicle]"):
            return  # zaten statustext olarak gösteriliyor
        self.status_label.setText(text)

    def refresh_armed_state(self, armed: bool) -> None:
        self.armed_pill.set_state(
            "ARM — KALİBRASYON ENGELLİ" if armed else "DISARM — KALİBRASYONA HAZIR",
            "danger" if armed else "success",
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._current is not None:
            self._current.on_hidden()
        self._mavlink.set_rc_monitor(False)
        super().closeEvent(event)

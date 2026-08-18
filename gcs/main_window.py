"""BAHR-GCS — ana pencere.

Arayuz mimarisi (dock yigini yerine sabit, okunabilir bir kabuk):

    +---------------------------------------------------------------+
    |  UST KOMUTA CUBUGU  (marka | link | pusula | canli metrikler)  |
    +------+--------------------------------------------+-----------+
    | RAIL |               HARITA + HUD                 |  GOREV    |
    |      |                                            |  PANELI   |
    +------+--------------------------------------------+-----------+
    |  DURUM SERIDI  (son olay + konsol cekmecesi)                   |
    +---------------------------------------------------------------+

Tasarim ilkeleri: tek aksan rengi, 4 px spacing skalasi, tipografik
hiyerarsi (mono sayilar / sans etiketler), yuksek kontrast ve genis
bosluk kullanimi. Tum degerler gcs.theme icindeki token'lardan gelir.
"""

from __future__ import annotations

import json
import math
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QTimer, QUrl, Qt, qDebug
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices, QMediaRecorder
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QStackedLayout,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gcs.components import (
    AttitudeIndicator,
    BatteryGauge,
    Card,
    CompassStrip,
    DepthLegend,
    FormRow,
    KeyValueRow,
    LiveDot,
    MetricGrid,
    MetricTile,
    MissionProgressBar,
    SegmentedControl,
    Sparkline,
    VirtualJoystick,
    StatusPill,
    button,
    field_label,
    h_divider,
    section_label,
    toggle,
    v_divider,
)
from gcs.map_bridge import MapBridge
from gcs.mavlink_service import MavlinkService
from gcs.mission_planner import SurveyPlanner
from gcs.models import DepthSample, MissionPoint, MissionStats, TelemetryData
from gcs.theme import (
    APP_NAME,
    APP_TAGLINE_SHORT,
    COLORS,
    Radius,
    Space,
    Type,
    brand_badge,
    depth_color,
    mono_font_family,
    qcolor,
    ui_font_family,
)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Harita
# ---------------------------------------------------------------------------

class MapWidget(QWebEngineView):
    def __init__(self) -> None:
        super().__init__()
        self.bridge = MapBridge()
        self.channel = QWebChannel(self.page())
        self.channel.registerObject("bridge", self.bridge)
        self.page().setWebChannel(self.channel)
        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        self.page().setBackgroundColor(QColor(COLORS.bg_canvas))

        html_path = Path(__file__).resolve().parent.parent / "web" / "map.html"
        html = html_path.read_text(encoding="utf-8")
        self.setHtml(html, QUrl.fromLocalFile(str(html_path.parent) + "/"))

    def update_survey_path(self, mission_points: list[MissionPoint]) -> None:
        payload = [
            {"lat": point.latitude, "lng": point.longitude, "alt": point.altitude_m}
            for point in mission_points
        ]
        self.page().runJavaScript(f"setSurveyPath({json.dumps(payload)});")

    def update_vehicle_state(self, telemetry: TelemetryData, append_track: bool) -> None:
        payload = {
            "lat": telemetry.latitude,
            "lng": telemetry.longitude,
            "heading": telemetry.heading_deg,
            "appendTrack": append_track,
        }
        self.page().runJavaScript(f"updateVehicleState({json.dumps(payload)});")

    def clear_survey(self) -> None:
        self.page().runJavaScript("clearSurveyPath();")

    def update_sample_points(
        self,
        sample_points: list[dict],
        show_numbers: bool = False,
        density_preview: bool = False,
    ) -> None:
        payload = {
            "points": sample_points,
            "showNumbers": show_numbers,
            "densityPreview": density_preview,
        }
        self.page().runJavaScript(f"setSamplePoints({json.dumps(payload)});")

    def set_home_point(self, latitude: float, longitude: float) -> None:
        self.page().runJavaScript(f"setHomePoint({json.dumps({'lat': latitude, 'lng': longitude})});")

    def set_heading_cone_visible(self, visible: bool) -> None:
        self.page().runJavaScript(f"setHeadingConeVisible({json.dumps(visible)});")

    def clear_track(self) -> None:
        self.page().runJavaScript("clearVehicleTrack();")

    def set_measure_mode(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setMeasureMode({json.dumps(enabled)});")

    def set_goto_mode(self, enabled: bool) -> None:
        self.page().runJavaScript(f"setGotoMode({json.dumps(enabled)});")

    def update_depth_heatmap(self, depth_points: list[dict]) -> None:
        self.page().runJavaScript(f"setDepthHeatmap({json.dumps(depth_points)});")

    def set_base_layer(self, layer_key: str) -> None:
        self.page().runJavaScript(f"setBaseLayer({json.dumps(layer_key)});")

    def focus_vehicle(self) -> None:
        self.page().runJavaScript("focusVehicle();")

    def start_polygon(self) -> None:
        self.page().runJavaScript("startPolygonDrawing();")

    def finish_polygon(self) -> None:
        self.page().runJavaScript("finishPolygonDrawing();")

    def clear_polygon(self) -> None:
        self.page().runJavaScript("clearPolygon();")


# ---------------------------------------------------------------------------
# Kamera paneli
# ---------------------------------------------------------------------------

class CameraPanel(Card):
    """USB kamera onizleme — kart tasarim dili ile yeniden kuruldu."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Camera", parent, spacing=Space.sm)

        self.capture_session = QMediaCaptureSession(self)
        self.camera: QCamera | None = None
        self.recorder: QMediaRecorder | None = None
        self.timestamp_enabled = True

        self.state_pill = StatusPill("OFFLINE", "neutral")
        self.add_header_widget(self.state_pill)

        self.camera_selector = QComboBox()
        self.camera_selector.currentIndexChanged.connect(self._on_camera_selected)
        self.add(FormRow("Device", self.camera_selector))

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(168)
        self.video_widget.setStyleSheet(
            f"background: {COLORS.bg_root}; border-radius: {Radius.md}px;"
        )
        self.capture_session.setVideoOutput(self.video_widget)
        self.add(self.video_widget, 1)

        controls = QWidget()
        controls_layout = QGridLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setHorizontalSpacing(Space.sm)
        controls_layout.setVerticalSpacing(Space.sm)
        self.toggle_button = button("Start", "primary", self._toggle_camera)
        self.snapshot_button = button("Snapshot", "quiet", self._save_snapshot)
        self.record_button = button("Record", "quiet", self._toggle_record)
        refresh_button = button("Rescan devices", "ghost", self._load_cameras)
        controls_layout.addWidget(self.toggle_button, 0, 0)
        controls_layout.addWidget(self.snapshot_button, 0, 1)
        controls_layout.addWidget(self.record_button, 1, 0)
        controls_layout.addWidget(refresh_button, 1, 1)
        self.add(controls)

        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        self.timestamp_checkbox = toggle("Timestamp overlay", True)
        self.timestamp_checkbox.toggled.connect(self._toggle_timestamp)
        self.timestamp_label = QLabel()
        self.timestamp_label.setStyleSheet(
            f'font-family: "{mono_font_family()}"; font-size: {Type.caption}px;'
            f"color: {COLORS.text_secondary};"
        )
        footer_layout.addWidget(self.timestamp_checkbox)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self.timestamp_label)
        self.add(footer)

        self.status_label = QLabel("No camera selected.")
        self.status_label.setObjectName("cardHint")
        self.status_label.setWordWrap(True)
        self.add(self.status_label)

        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self._update_timestamp)
        self.clock_timer.start()
        self._update_timestamp()
        self._load_cameras()

    def _load_cameras(self) -> None:
        cameras = QMediaDevices.videoInputs()
        current_id = self.camera_selector.currentData()
        self.camera_selector.blockSignals(True)
        self.camera_selector.clear()
        for camera in cameras:
            self.camera_selector.addItem(camera.description(), camera.id())
        self.camera_selector.blockSignals(False)

        if not cameras:
            self._stop_camera()
            self.status_label.setText("No USB camera found.")
            self.state_pill.set_state("NO DEVICE", "warning")
            self.toggle_button.setEnabled(False)
            self.snapshot_button.setEnabled(False)
            self.record_button.setEnabled(False)
            return

        self.toggle_button.setEnabled(True)
        self.snapshot_button.setEnabled(True)
        self.record_button.setEnabled(True)
        if current_id is not None:
            for index in range(self.camera_selector.count()):
                if self.camera_selector.itemData(index) == current_id:
                    self.camera_selector.setCurrentIndex(index)
                    break
        if self.camera_selector.currentIndex() < 0:
            self.camera_selector.setCurrentIndex(0)
        self.status_label.setText("Camera ready. Press Start.")
        self.state_pill.set_state("READY", "info")

    def _on_camera_selected(self) -> None:
        if self.camera is not None:
            self._start_selected_camera()

    def _toggle_camera(self) -> None:
        if self.camera is None:
            self._start_selected_camera()
        else:
            self._stop_camera()
            self.state_pill.set_state("OFFLINE", "neutral")

    def _start_selected_camera(self) -> None:
        cameras = QMediaDevices.videoInputs()
        index = self.camera_selector.currentIndex()
        if index < 0 or index >= len(cameras):
            self.status_label.setText("No camera selected.")
            return

        self._stop_camera()
        self.camera = QCamera(cameras[index])
        self.capture_session.setCamera(self.camera)
        self.recorder = QMediaRecorder()
        self.capture_session.setRecorder(self.recorder)
        self.camera.start()
        self.toggle_button.setText("Stop")
        self.status_label.setText(f"Live: {cameras[index].description()}")
        self.state_pill.set_state("LIVE", "success")

    def _stop_camera(self) -> None:
        if self.recorder is not None and self.recorder.recorderState() == QMediaRecorder.RecorderState.RecordingState:
            self.recorder.stop()
        self.record_button.setText("Record")
        if self.camera is not None:
            self.camera.stop()
            self.capture_session.setCamera(None)
            self.camera.deleteLater()
            self.camera = None
        self.recorder = None
        self.toggle_button.setText("Start")

    def _save_snapshot(self) -> None:
        image = self.video_widget.grab()
        if image.isNull():
            self.status_label.setText("Snapshot failed.")
            return
        target = Path.cwd() / f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        image.save(str(target))
        self.status_label.setText(f"Snapshot saved: {target.name}")

    def _toggle_record(self) -> None:
        if self.recorder is None:
            self.status_label.setText("Start camera before recording.")
            return
        if self.recorder.recorderState() == QMediaRecorder.RecorderState.RecordingState:
            self.recorder.stop()
            self.record_button.setText("Record")
            self.status_label.setText("Recording stopped.")
            self.state_pill.set_state("LIVE", "success")
            return
        target = Path.cwd() / f"camera_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        self.recorder.setOutputLocation(QUrl.fromLocalFile(str(target)))
        self.recorder.record()
        self.record_button.setText("Stop Rec")
        self.status_label.setText(f"Recording: {target.name}")
        self.state_pill.set_state("REC", "danger")

    def _toggle_timestamp(self, enabled: bool) -> None:
        self.timestamp_enabled = enabled
        self.timestamp_label.setVisible(enabled)

    def _update_timestamp(self) -> None:
        self.timestamp_label.setText(datetime.now().strftime("%H:%M:%S"))


# ---------------------------------------------------------------------------
# Harita + HUD katmani
# ---------------------------------------------------------------------------

class MapOverlayPane(QWidget):
    """Haritanin uzerine yuzen HUD ogelerini konumlandirir.

    ONEMLI — Qt hit-test kurali:
    `WA_TransparentForMouseEvents` isaretli bir widget, `childAt()` taramasinda
    TUM ALT AGACI ile birlikte atlanir. Bu yuzden tiklanabilir araç çubugu
    seffaf HUD katmaninin icine konulamaz; dogrudan bu pane'in cocugu olarak
    olusturulup elle konumlandirilir ve en uste alinir.

    Sonuc:
      * `overlay_layer`  -> tiklama gecirir, yalnizca pasif HUD tasir
        (suni ufuk + okuma karti)
      * `toolbar`        -> pane'in dogrudan cocugu, tam etkilesimli
    """

    def __init__(self, map_widget: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.map_widget = map_widget

        self.overlay_layer = QWidget()
        self.overlay_layer.setObjectName("mapOverlayLayer")
        self.overlay_layer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout = QStackedLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setStackingMode(QStackedLayout.StackingMode.StackAll)
        layout.addWidget(self.map_widget)
        layout.addWidget(self.overlay_layer)
        layout.setCurrentWidget(self.overlay_layer)

        grid = QGridLayout(self.overlay_layer)
        grid.setContentsMargins(Space.lg, Space.lg, Space.lg, Space.lg)
        grid.setSpacing(Space.md)
        grid.setRowStretch(0, 1)

        bottom = QWidget()
        bottom.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(Space.md)

        self.horizon_widget = AttitudeIndicator()
        horizon_frame = QFrame()
        horizon_frame.setObjectName("glassPanel")
        horizon_frame.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        horizon_layout = QVBoxLayout(horizon_frame)
        horizon_layout.setContentsMargins(Space.md, Space.md, Space.md, Space.md)
        horizon_layout.addWidget(self.horizon_widget)

        self.hud_card = self._build_hud_readout()

        bottom_layout.addWidget(horizon_frame, 0, Qt.AlignmentFlag.AlignBottom)
        bottom_layout.addWidget(self.hud_card, 0, Qt.AlignmentFlag.AlignBottom)
        bottom_layout.addStretch(1)

        grid.addWidget(bottom, 1, 0, Qt.AlignmentFlag.AlignBottom)

        # Etkilesimli katman: seffaf HUD katmaninin disinda, pane'in cocugu.
        self.toolbar = self._build_toolbar()
        self.toolbar.setParent(self)
        self.toolbar.show()
        self._place_toolbar()

    # -- yerlesim ---------------------------------------------------------

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._place_toolbar()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.toolbar.raise_()
        self._place_toolbar()

    def _place_toolbar(self) -> None:
        self.toolbar.adjustSize()
        x = max(Space.lg, self.width() - self.toolbar.width() - Space.lg)
        self.toolbar.move(x, Space.lg)
        self.toolbar.raise_()

    def _build_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("glassPanel")
        frame.setFixedWidth(242)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(Space.md, Space.md, Space.md, Space.md)
        layout.setSpacing(Space.sm)

        layout.addWidget(section_label("Base layer"))
        self.layer_control = SegmentedControl(["Street", "Satellite"])
        layout.addWidget(self.layer_control)
        layout.addWidget(h_divider())

        layout.addWidget(section_label("Polygon"))
        polygon_row = QWidget()
        polygon_layout = QHBoxLayout(polygon_row)
        polygon_layout.setContentsMargins(0, 0, 0, 0)
        polygon_layout.setSpacing(Space.xs)
        self.draw_button = button("Draw", "primary")
        self.finish_button = button("Finish", "quiet")
        self.clear_polygon_button = button("Clear", "ghost")
        for widget in (self.draw_button, self.finish_button, self.clear_polygon_button):
            widget.setProperty("compact", "true")
            polygon_layout.addWidget(widget, 1)
        layout.addWidget(polygon_row)
        layout.addWidget(h_divider())

        layout.addWidget(section_label("Map tools"))
        self.focus_button = button("Center on vehicle", "quiet")
        self.home_button = button("Set home here", "quiet")
        self.clear_track_button = button("Clear track", "ghost")
        self.cone_toggle = toggle("Heading cone", True)
        self.measure_toggle = toggle("Measure tool", False)
        for widget in (
            self.focus_button,
            self.home_button,
            self.clear_track_button,
            self.cone_toggle,
            self.measure_toggle,
        ):
            layout.addWidget(widget)

        # Go to commands the vehicle — it is not a view option, so it gets its
        # own section rather than sitting among the display toggles above.
        layout.addWidget(h_divider())
        layout.addWidget(section_label("Vehicle command"))
        self.goto_toggle = button("Go to point", "quiet")
        self.goto_toggle.setCheckable(True)
        self.goto_toggle.setToolTip(
            "Click a point on the map to send the vehicle there (switches to Guided)."
        )
        layout.addWidget(self.goto_toggle)
        return frame

    def _build_hud_readout(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("glassPanel")
        frame.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QGridLayout(frame)
        layout.setContentsMargins(Space.lg, Space.md, Space.lg, Space.md)
        layout.setHorizontalSpacing(Space.xl)
        layout.setVerticalSpacing(Space.xs)

        self.hud_items: dict[str, QLabel] = {}
        for column, (key, caption) in enumerate(
            [("speed", "SPEED m/s"), ("heading", "HEADING"), ("depth", "DEPTH m")]
        ):
            caption_label = QLabel(caption)
            caption_label.setObjectName("hudCaption")
            value_label = QLabel("—")
            value_label.setObjectName("hudValue")
            layout.addWidget(caption_label, 0, column)
            layout.addWidget(value_label, 1, column)
            self.hud_items[key] = value_label
        return frame

    def set_hud(self, speed: str, heading: str, depth: str, depth_tone: str) -> None:
        self.hud_items["speed"].setText(speed)
        self.hud_items["heading"].setText(heading)
        self.hud_items["depth"].setText(depth)
        self.hud_items["depth"].setStyleSheet(
            f'font-family: "{mono_font_family()}"; font-size: {Type.title}px;'
            f"font-weight: 700; color: {depth_tone};"
        )


# ---------------------------------------------------------------------------
# Waypoint listesi
# ---------------------------------------------------------------------------

class WaypointListDialog(QDialog):
    """On-demand coordinate list for the generated survey path.

    Kept as a separate window so the plan panel stays uncluttered — the map is
    the primary surface and this is reference data, not a live readout.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mission waypoints")
        self.resize(460, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Space.lg, Space.lg, Space.lg, Space.lg)
        layout.setSpacing(Space.md)

        self.summary = QLabel("No mission generated yet.")
        self.summary.setObjectName("cardHint")
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Latitude", "Longitude", "Leg"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setStyleSheet(
            f"QTableWidget {{ background: {COLORS.bg_canvas};"
            f" border: 1px solid {COLORS.border_subtle};"
            f" border-radius: {Radius.md}px;"
            f' font-family: "{mono_font_family()}"; font-size: {Type.caption}px;'
            f" color: {COLORS.text_primary}; gridline-color: {COLORS.border_subtle}; }}"
            f"QHeaderView::section {{ background: {COLORS.surface_2};"
            f" color: {COLORS.text_tertiary}; border: none;"
            f" padding: {Space.xs}px {Space.sm}px;"
            f' font-family: "{ui_font_family()}"; font-size: {Type.micro}px;'
            f" font-weight: 700; letter-spacing: {Type.tracking_wide}px; }}"
            f"QTableWidget::item {{ padding: {Space.xs}px {Space.sm}px; }}"
        )
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.copy_button = button("Copy all", "quiet", self._copy_to_clipboard)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(button("Close", "quiet", self.close))
        layout.addLayout(buttons)

        self._points: list[MissionPoint] = []

    def set_points(self, points: list[MissionPoint]) -> None:
        self._points = list(points)
        self.table.setRowCount(len(self._points))

        total_m = 0.0
        previous: MissionPoint | None = None
        for row, point in enumerate(self._points):
            leg = 0.0 if previous is None else _haversine_m(
                previous.latitude, previous.longitude, point.latitude, point.longitude
            )
            total_m += leg
            cells = [
                str(row + 1),
                f"{point.latitude:.7f}",
                f"{point.longitude:.7f}",
                "—" if previous is None else f"{leg:.0f} m",
            ]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setForeground(QColor(COLORS.text_tertiary))
                elif column == 3:
                    item.setForeground(QColor(COLORS.text_secondary))
                item.setTextAlignment(
                    int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                    if column
                    else int(Qt.AlignmentFlag.AlignCenter)
                )
                self.table.setItem(row, column, item)
            previous = point

        if self._points:
            self.summary.setText(
                f"{len(self._points)} waypoints · total track {total_m:.0f} m"
            )
        else:
            self.summary.setText("No mission generated yet — draw a polygon and generate a path.")
        self.copy_button.setEnabled(bool(self._points))

    def _copy_to_clipboard(self) -> None:
        lines = ["index,latitude,longitude"]
        lines += [
            f"{index + 1},{point.latitude:.7f},{point.longitude:.7f}"
            for index, point in enumerate(self._points)
        ]
        QApplication.clipboard().setText("\n".join(lines))


# ---------------------------------------------------------------------------
# Arac parametreleri
# ---------------------------------------------------------------------------

class VehicleTuningDialog(QDialog):
    """Read and write the vehicle parameters that shape survey behaviour.

    Only writes what the operator changed, and reports the value the vehicle
    echoes back rather than the one we asked for — ArduPilot stores integers
    and clamps ranges, so the two can differ.
    """

    # Grouped by what they actually affect, with the units ArduPilot uses.
    PARAMETERS = [
        ("Waypoint navigation", [
            ("WP_RADIUS", "Acceptance radius", "m"),
            ("WP_SPEED", "Target speed", "m/s"),
            ("WP_ACCEL", "Acceleration", "m/s²"),
            ("WP_JERK", "Jerk — lower is smoother", "m/s³"),
            ("WP_OVERSHOOT", "Allowed overshoot", "m"),
        ]),
        ("Vehicle", [
            ("TURN_RADIUS", "Turn radius", "m"),
            ("CRUISE_SPEED", "Cruise speed", "m/s"),
            ("CRUISE_THROTTLE", "Cruise throttle", "%"),
            ("FRAME_CLASS", "1 = rover, 2 = boat", ""),
        ]),
        ("Steering controller — disturbance rejection", [
            ("ATC_STR_RAT_P", "Rate P", ""),
            ("ATC_STR_RAT_I", "Rate I", ""),
            ("ATC_STR_RAT_D", "Rate D", ""),
        ]),
    ]

    def __init__(self, mavlink, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Vehicle tuning")
        self.resize(600, 640)
        self._mavlink = mavlink
        self._rows: dict[str, dict] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Space.lg, Space.lg, Space.lg, Space.lg)
        layout.setSpacing(Space.md)

        self.summary = QLabel("Read the vehicle to see its current values.")
        self.summary.setObjectName("cardHint")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(Space.md)

        for group, entries in self.PARAMETERS:
            card = Card(group)
            grid = QGridLayout()
            grid.setHorizontalSpacing(Space.sm)
            grid.setVerticalSpacing(Space.xs)
            for row, (name, description, unit) in enumerate(entries):
                label = QLabel(name)
                label.setStyleSheet(
                    f'font-family: "{mono_font_family()}"; font-size: {Type.caption}px;'
                )
                current = QLabel("—")
                current.setStyleSheet(
                    f'font-family: "{mono_font_family()}"; font-size: {Type.caption}px;'
                    f"color: {COLORS.text_secondary};"
                )
                current.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                editor = QLineEdit()
                editor.setPlaceholderText("unchanged")
                editor.setFixedWidth(90)
                hint = QLabel(f"{description}{f'  ({unit})' if unit else ''}")
                hint.setObjectName("cardHint")

                grid.addWidget(label, row * 2, 0)
                grid.addWidget(current, row * 2, 1)
                grid.addWidget(editor, row * 2, 2)
                grid.addWidget(hint, row * 2 + 1, 0, 1, 3)
                self._rows[name] = {"current": current, "editor": editor, "value": None}
            card.add_layout(grid)
            body_layout.addWidget(card)

        body_layout.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.addWidget(button("Read from vehicle", "quiet", self.refresh))
        buttons.addStretch(1)
        buttons.addWidget(button("Write changes", "primary", self._write_changes))
        buttons.addWidget(button("Close", "quiet", self.close))
        layout.addLayout(buttons)

    def refresh(self) -> None:
        for name in self._rows:
            self._mavlink.request_parameter(name)
        self.summary.setText("Reading parameters from the vehicle…")

    def on_parameter(self, name: str, value: float) -> None:
        row = self._rows.get(name)
        if row is None:
            return
        row["value"] = value
        row["current"].setText(f"{value:g}")
        row["current"].setStyleSheet(
            f'font-family: "{mono_font_family()}"; font-size: {Type.caption}px;'
            f"color: {COLORS.success};"
        )
        # The vehicle has confirmed this value, so the pending edit is settled.
        editor = row["editor"]
        if editor.text().strip():
            try:
                requested = float(editor.text().replace(",", "."))
            except ValueError:
                return
            if abs(requested - value) < 1e-6:
                editor.clear()

        known = sum(1 for r in self._rows.values() if r["value"] is not None)
        self.summary.setText(f"{known} / {len(self._rows)} parameters read from the vehicle.")

    def _write_changes(self) -> None:
        written = 0
        for name, row in self._rows.items():
            text = row["editor"].text().strip()
            if not text:
                continue
            try:
                value = float(text.replace(",", "."))
            except ValueError:
                row["editor"].setStyleSheet(f"border: 1px solid {COLORS.danger};")
                continue
            row["editor"].setStyleSheet("")
            self._mavlink.set_parameter(name, value)
            written += 1
        if written:
            self.summary.setText(
                f"Wrote {written} parameter(s). The value shown updates when the "
                "vehicle confirms it — if it does not change, the write was refused."
            )
        else:
            self.summary.setText("Nothing to write — type a value next to a parameter first.")


# ---------------------------------------------------------------------------
# Batimetri gorunumu
# ---------------------------------------------------------------------------

class BathymetryView(QWidget):
    """Plan view of the soundings collected at the planned sample points.

    Deliberately independent of the Leaflet map: this is the survey product,
    read in local metres against the polygon, with no basemap to argue with.
    """

    MARGIN = 44

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(420, 360)
        self._samples: list[dict] = []
        self._polygon: list[dict] = []
        self._origin: tuple[float, float] | None = None

    def set_data(self, samples: list[dict], polygon: list[dict]) -> None:
        self._samples = samples
        self._polygon = polygon or []
        reference = samples or self._polygon
        if reference:
            first = reference[0]
            self._origin = (first.get("lat"), first.get("lng"))
        self.update()

    # -- projeksiyon -------------------------------------------------------

    def _to_metres(self, lat: float, lon: float) -> tuple[float, float]:
        """Equirectangular projection about the first point — fine at survey scale."""
        origin_lat, origin_lon = self._origin
        east = math.radians(lon - origin_lon) * 6371000.0 * math.cos(math.radians(origin_lat))
        north = math.radians(lat - origin_lat) * 6371000.0
        return east, north

    def _bounds(self) -> tuple[float, float, float, float] | None:
        coords = [
            self._to_metres(item["lat"], item["lng"])
            for item in list(self._samples) + list(self._polygon)
        ]
        if not coords:
            return None
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        return min(xs), max(xs), min(ys), max(ys)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), qcolor(COLORS.bg_canvas))

        if self._origin is None or not (self._samples or self._polygon):
            painter.setPen(QPen(qcolor(COLORS.text_tertiary)))
            painter.setFont(QFont(ui_font_family(), Type.body))
            painter.drawText(
                self.rect(), int(Qt.AlignmentFlag.AlignCenter),
                "No soundings yet.\nRun the survey and readings will appear here.",
            )
            return

        bounds = self._bounds()
        min_x, max_x, min_y, max_y = bounds
        span_x = max(1.0, max_x - min_x)
        span_y = max(1.0, max_y - min_y)
        usable_w = self.width() - 2 * self.MARGIN
        usable_h = self.height() - 2 * self.MARGIN
        # One scale for both axes so the survey is not distorted.
        scale = min(usable_w / span_x, usable_h / span_y)
        offset_x = self.MARGIN + (usable_w - span_x * scale) / 2
        offset_y = self.MARGIN + (usable_h - span_y * scale) / 2

        def project(lat: float, lon: float) -> QPointF:
            east, north = self._to_metres(lat, lon)
            return QPointF(
                offset_x + (east - min_x) * scale,
                # Screen y grows downwards; north must go up.
                self.height() - offset_y - (north - min_y) * scale,
            )

        # Survey boundary
        if len(self._polygon) >= 3:
            path = QPainterPath()
            first = project(self._polygon[0]["lat"], self._polygon[0]["lng"])
            path.moveTo(first)
            for vertex in self._polygon[1:]:
                path.lineTo(project(vertex["lat"], vertex["lng"]))
            path.closeSubpath()
            painter.setPen(QPen(qcolor(COLORS.border_strong), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        # Soundings, coloured on the shared depth scale
        painter.setPen(Qt.PenStyle.NoPen)
        for item in self._samples:
            colour = qcolor(depth_color(item["depth"]))
            painter.setBrush(colour)
            painter.drawEllipse(project(item["lat"], item["lng"]), 5.0, 5.0)

        self._draw_scale_bar(painter, scale)

    def _draw_scale_bar(self, painter: QPainter, scale: float) -> None:
        # Pick a round distance that lands near 120 px on screen.
        target_px = 120.0
        raw = target_px / scale
        magnitude = 10 ** math.floor(math.log10(max(1.0, raw)))
        for step in (1, 2, 5, 10):
            nice = step * magnitude
            if nice * scale >= target_px * 0.6:
                break
        length = nice * scale
        y = self.height() - 18
        x = self.MARGIN
        painter.setPen(QPen(qcolor(COLORS.text_tertiary), 1.4))
        painter.drawLine(QPointF(x, y), QPointF(x + length, y))
        painter.drawLine(QPointF(x, y - 4), QPointF(x, y + 4))
        painter.drawLine(QPointF(x + length, y - 4), QPointF(x + length, y + 4))
        painter.setFont(QFont(mono_font_family(), Type.micro))
        painter.drawText(
            QRectF(x, y - 20, length, 16),
            int(Qt.AlignmentFlag.AlignCenter), f"{nice:.0f} m",
        )


class BathymetryDialog(QDialog):
    """2D depth map of the collected sample points."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bathymetry — collected samples")
        self.resize(640, 640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Space.lg, Space.lg, Space.lg, Space.lg)
        layout.setSpacing(Space.md)

        self.summary = QLabel("No soundings collected yet.")
        self.summary.setObjectName("cardHint")
        layout.addWidget(self.summary)

        self.view = BathymetryView()
        layout.addWidget(self.view, 1)
        layout.addWidget(DepthLegend())

        # Soundings are geographic on the wire but a survey is easier to read
        # — and to hand to any other tool — in local metres.
        self.coord_mode = SegmentedControl(["Lat / Lon", "Metres E/N"])
        self.coord_mode.changed.connect(lambda _text: self._refresh_table())
        layout.addWidget(self.coord_mode)

        self.table = QTableWidget(0, 4)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setMaximumHeight(190)
        self.table.setStyleSheet(
            f"QTableWidget {{ background: {COLORS.bg_canvas};"
            f" border: 1px solid {COLORS.border_subtle};"
            f" border-radius: {Radius.md}px;"
            f' font-family: "{mono_font_family()}"; font-size: {Type.caption}px;'
            f" color: {COLORS.text_primary}; }}"
            f"QHeaderView::section {{ background: {COLORS.surface_2};"
            f" color: {COLORS.text_tertiary}; border: none;"
            f" padding: {Space.xs}px {Space.sm}px;"
            f' font-family: "{ui_font_family()}"; font-size: {Type.micro}px;'
            f" font-weight: 700; }}"
        )
        layout.addWidget(self.table)

        self.origin_label = QLabel()
        self.origin_label.setObjectName("cardHint")
        layout.addWidget(self.origin_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.copy_button = button("Copy CSV", "quiet", self._copy_to_clipboard)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(button("Close", "quiet", self.close))
        layout.addLayout(buttons)

        self._samples: list[dict] = []
        self._origin: tuple[float, float] | None = None

    # -- koordinat donusumu -------------------------------------------------

    def _is_cartesian(self) -> bool:
        return self.coord_mode.current_text().startswith("Metres")

    def _to_local_m(self, lat: float, lon: float) -> tuple[float, float]:
        """East/north metres from the survey origin (first sounding).

        Equirectangular about the origin — exact enough over a survey area,
        and it keeps the axes orthogonal so the numbers stay easy to reason
        about alongside the plot.
        """
        origin_lat, origin_lon = self._origin
        east = math.radians(lon - origin_lon) * 6371000.0 * math.cos(math.radians(origin_lat))
        north = math.radians(lat - origin_lat) * 6371000.0
        return east, north

    def _refresh_table(self) -> None:
        cartesian = self._is_cartesian()
        headers = (["#", "East (m)", "North (m)", "Depth (m)"] if cartesian
                   else ["#", "Latitude", "Longitude", "Depth (m)"])
        self.table.setHorizontalHeaderLabels(headers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)

        self.table.setRowCount(len(self._samples))
        for row, item in enumerate(self._samples):
            if cartesian:
                east, north = self._to_local_m(item["lat"], item["lng"])
                cells = [str(item.get("index")), f"{east:+.2f}", f"{north:+.2f}"]
            else:
                cells = [str(item.get("index")), f"{item['lat']:.7f}", f"{item['lng']:.7f}"]
            cells.append(f"{item['depth']:.2f}")
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                cell.setTextAlignment(
                    int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
                    if column else int(Qt.AlignmentFlag.AlignCenter)
                )
                if column == 0:
                    cell.setForeground(QColor(COLORS.text_tertiary))
                self.table.setItem(row, column, cell)

        if cartesian and self._origin is not None:
            self.origin_label.setText(
                f"Origin (0, 0) = first sounding at "
                f"{self._origin[0]:.7f}, {self._origin[1]:.7f} · east and north in metres"
            )
        else:
            self.origin_label.setText("WGS84 degrees, as sent to the vehicle.")

    def set_samples(self, samples: list[dict], polygon: list[dict]) -> None:
        self._samples = sorted(samples, key=lambda item: item.get("index") or 0)
        self._origin = (
            (self._samples[0]["lat"], self._samples[0]["lng"]) if self._samples else None
        )
        self.view.set_data(self._samples, polygon)
        self._refresh_table()
        if self._samples:
            depths = [item["depth"] for item in self._samples]
            self.summary.setText(
                f"{len(self._samples)} soundings · "
                f"depth {min(depths):.2f} – {max(depths):.2f} m · "
                f"mean {sum(depths) / len(depths):.2f} m"
            )
        else:
            self.summary.setText(
                "No soundings collected yet — they appear as the vehicle reaches "
                "each planned sample point."
            )
        self.copy_button.setEnabled(bool(self._samples))

    def _copy_to_clipboard(self) -> None:
        """Export in whichever frame is on screen, so the file matches the table."""
        if self._is_cartesian() and self._origin is not None:
            lines = [
                f"# origin {self._origin[0]:.7f},{self._origin[1]:.7f}",
                "index,lane,east_m,north_m,depth_m",
            ]
            for item in self._samples:
                east, north = self._to_local_m(item["lat"], item["lng"])
                lines.append(
                    f"{item.get('index')},{item.get('lane')},"
                    f"{east:.2f},{north:.2f},{item['depth']:.2f}"
                )
        else:
            lines = ["index,lane,latitude,longitude,depth_m"]
            lines += [
                f"{item.get('index')},{item.get('lane')},"
                f"{item['lat']:.7f},{item['lng']:.7f},{item['depth']:.2f}"
                for item in self._samples
            ]
        QApplication.clipboard().setText("\n".join(lines))


# ---------------------------------------------------------------------------
# Ana pencere
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    RAIL_PAGES = ["LINK", "CRAFT", "POWER", "PILOT", "CAM"]

    # Selectable ArduPilot modes, in the order a survey run normally uses them.
    FLIGHT_MODES = [
        ("MANUAL", "Direct throttle and steering control. Arm the vehicle here — AUTO refuses to arm."),
        ("HOLD", "Cuts the motors and stops. A boat will drift with the current."),
        ("LOITER", "Station keeping — actively holds position against wind and current."),
        ("AUTO", "Runs the uploaded mission. This is what Start switches to."),
        ("GUIDED", "Drives to a single target sent from the map. Used by Go to."),
        ("RTL", "Returns to the home position."),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)

        self.map_widget = MapWidget()
        self.map_pane = MapOverlayPane(self.map_widget)
        self.camera_panel = CameraPanel()
        self.planner = SurveyPlanner()
        self.mavlink = MavlinkService()

        self.polygon_points: list[dict] = []
        self.mission_points: list[MissionPoint] = []
        self.sample_points: list[dict] = []
        self.depth_samples: list[DepthSample] = []
        # Readings bound to planned sample points, keyed by the point's index.
        self.collected_samples: dict[int, dict] = {}
        self.last_track_point: dict | None = None
        self.home_point: dict | None = None
        self.connection_target = "udp:127.0.0.1:14550"
        self.mission_stats = MissionStats()
        self.console_visible = False
        self._refresh_count = 0
        self._telemetry_total_time = 0.0
        self._telemetry_map_time = 0.0
        self._telemetry_rest_time = 0.0
        self._last_seen_heading: float | None = None
        self._last_seen_roll: float | None = None
        self._last_seen_pitch: float | None = None
        self._value_change_count = 0
        self.connected = False

        # Controls that only make sense once there is something to act on.
        # Registered while the UI is built, then driven by
        # _refresh_control_states().
        self._needs_link: list[QWidget] = []
        self._needs_mission: list[QWidget] = []
        self._needs_polygon: list[QWidget] = []

        self.map_widget.bridge.polygon_changed.connect(self._on_polygon_changed)
        self.map_widget.bridge.waypoint_moved.connect(self._on_waypoint_moved)
        self.map_widget.bridge.goto_selected.connect(self._on_goto_selected)
        self.mavlink.status_updated.connect(self._append_status)
        self.mavlink.connection_changed.connect(self._on_connection_changed)
        self.mavlink.depth_sample_received.connect(self._on_depth_sample)
        self.mavlink.message_rate_updated.connect(self._on_message_rate_updated)
        self.mavlink.mission_verified.connect(self._on_mission_verified)
        self.mavlink.mission_completed.connect(self._on_mission_completed)
        self.mavlink.waypoint_radius_received.connect(self._on_waypoint_radius)

        self._joystick_axes = (0, 0)
        # None until the vehicle reports which segment it is on.
        self._active_segment_is_turn: bool | None = None

        # Local demo simulator (sim/fake_vehicle.py), launched as a child
        # process. Not the app's own MAVLink worker — a separate OS process
        # speaking real MAVLink to it, so it exercises the exact same code
        # path a real vehicle would.
        self._demo_process: subprocess.Popen | None = None
        self._demo_output_queue: queue.Queue = queue.Queue()
        self._demo_reader_thread: threading.Thread | None = None

        self._build_ui()
        self._wire_map_tools()
        self._setup_timers()

        self._joystick_timer = QTimer(self)
        self._joystick_timer.setInterval(100)  # 10 Hz, well inside RC_OVERRIDE_TIME
        self._joystick_timer.timeout.connect(self._stream_joystick)
        self.joystick.moved.connect(self._on_joystick_moved)
        self._gated(self.joystick, "link")

        self._demo_output_timer = QTimer(self)
        self._demo_output_timer.setInterval(150)
        self._demo_output_timer.timeout.connect(self._drain_demo_output)
        self._refresh_control_states()
        self._refresh_turn_warning()
        self._append_status(f"{APP_NAME} ready. Select a link type and connect.")

    def _gated(self, widget: QWidget, requirement: str) -> QWidget:
        """Register a control so its enabled state follows app state."""
        {
            "link": self._needs_link,
            "mission": self._needs_mission,
            "polygon": self._needs_polygon,
        }[requirement].append(widget)
        return widget

    def _refresh_control_states(self) -> None:
        has_mission = bool(self.mission_points)
        for widget in self._needs_link:
            widget.setEnabled(self.connected)
        for widget in self._needs_mission:
            widget.setEnabled(self.connected and has_mission)
        for widget in self._needs_polygon:
            widget.setEnabled(len(self.polygon_points) >= 3)

    # -- kabuk ------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_top_bar())

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self._build_nav_rail())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self.map_pane)
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([340, 820, 424])
        body_layout.addWidget(splitter, 1)

        root_layout.addWidget(body, 1)
        root_layout.addWidget(self._build_console_drawer())
        root_layout.addWidget(self._build_status_strip())

        self.setCentralWidget(root)

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("topBar")
        bar.setFixedHeight(78)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(Space.lg, Space.sm, Space.lg, Space.sm)
        layout.setSpacing(Space.lg)

        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(Space.md)

        logo = QLabel()
        logo.setObjectName("brandLogo")
        logo.setFixedSize(42, 42)
        logo.setPixmap(brand_badge(42))
        brand_layout.addWidget(logo)

        wordmark = QWidget()
        wordmark_layout = QVBoxLayout(wordmark)
        wordmark_layout.setContentsMargins(0, 0, 0, 0)
        wordmark_layout.setSpacing(0)
        brand_title = QLabel(APP_NAME)
        brand_title.setObjectName("brandMark")
        brand_sub = QLabel(APP_TAGLINE_SHORT)
        brand_sub.setObjectName("brandSub")
        wordmark_layout.addWidget(brand_title)
        wordmark_layout.addWidget(brand_sub)
        brand_layout.addWidget(wordmark)

        layout.addWidget(brand)
        layout.addWidget(v_divider(42))

        link = QWidget()
        link_layout = QHBoxLayout(link)
        link_layout.setContentsMargins(0, 0, 0, 0)
        link_layout.setSpacing(Space.sm)
        self.link_dot = LiveDot()
        self.link_state_pill = StatusPill("DISCONNECTED", "danger")
        self.link_quality_pill = StatusPill("LINK —", "neutral")
        link_layout.addWidget(self.link_dot)
        link_layout.addWidget(self.link_state_pill)
        link_layout.addWidget(self.link_quality_pill)
        layout.addWidget(link)
        layout.addWidget(v_divider(42))

        self.compass = CompassStrip()
        layout.addWidget(self.compass)
        layout.addWidget(v_divider(42))

        metrics = QWidget()
        metrics_layout = QHBoxLayout(metrics)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(Space.md)
        self.tile_speed = MetricTile("Speed", "—", "m/s", bare=True)
        self.tile_heading = MetricTile("Heading", "—", "deg", bare=True)
        self.tile_depth = MetricTile("Depth", "—", "m", bare=True)
        self.tile_battery = MetricTile("Battery", "—", "%", bare=True)
        for tile in (self.tile_speed, self.tile_heading, self.tile_depth, self.tile_battery):
            metrics_layout.addWidget(tile)
        layout.addWidget(metrics)

        layout.addStretch(1)

        state = QWidget()
        state_layout = QVBoxLayout(state)
        state_layout.setContentsMargins(0, 0, 0, 0)
        state_layout.setSpacing(Space.xs)
        self.mode_pill = StatusPill("MODE UNKNOWN", "neutral")
        self.armed_pill = StatusPill("DISARMED", "neutral")
        state_layout.addWidget(self.mode_pill, 0, Qt.AlignmentFlag.AlignRight)
        state_layout.addWidget(self.armed_pill, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(state)

        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(Space.sm)
        actions_layout.addWidget(
            self._gated(button("Arm", "primary", self.mavlink.arm_vehicle), "link")
        )
        actions_layout.addWidget(
            self._gated(button("Disarm", "danger", self._confirm_disarm), "link")
        )
        actions_layout.addWidget(
            self._gated(button("RTL", "quiet", self._confirm_return_home), "link")
        )
        layout.addWidget(actions)
        return bar

    def _build_nav_rail(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("navRail")
        rail.setFixedWidth(74)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(Space.sm, Space.md, Space.sm, Space.md)
        layout.setSpacing(Space.xs)

        self.rail_group = QButtonGroup(self)
        self.rail_group.setExclusive(True)
        for index, name in enumerate(self.RAIL_PAGES):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("rail", "true")
            btn.setFixedHeight(46)
            if index == 0:
                btn.setChecked(True)
            self.rail_group.addButton(btn, index)
            layout.addWidget(btn)
        layout.addStretch(1)

        self.console_button = QPushButton("LOG")
        self.console_button.setCheckable(True)
        self.console_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.console_button.setProperty("rail", "true")
        self.console_button.setFixedHeight(46)
        self.console_button.toggled.connect(self._toggle_console)
        layout.addWidget(self.console_button)
        return rail

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("sidePanel")
        panel.setMinimumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.left_stack = QStackedWidget()
        self.left_stack.addWidget(self._scrollable(self._build_link_page()))
        self.left_stack.addWidget(self._scrollable(self._build_vehicle_page()))
        self.left_stack.addWidget(self._scrollable(self._build_power_page()))
        self.left_stack.addWidget(self._scrollable(self._build_pilot_page()))
        self.left_stack.addWidget(self._scrollable(self._build_camera_page()))
        self.rail_group.idClicked.connect(self.left_stack.setCurrentIndex)

        layout.addWidget(self.left_stack, 1)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("sidePanelRight")
        panel.setMinimumWidth(404)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(Space.lg, Space.md, Space.lg, Space.md)
        layout.setSpacing(Space.sm)

        tabs = QTabWidget()
        tabs.addTab(self._scrollable(self._build_plan_page(), padding=0), "Plan")
        tabs.addTab(self._scrollable(self._build_mission_page(), padding=0), "Mission")
        tabs.addTab(self._scrollable(self._build_depth_page(), padding=0), "Depth")
        layout.addWidget(tabs, 1)
        return panel

    def _scrollable(self, widget: QWidget, padding: int = Space.lg) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(padding, padding, padding, padding)
        container_layout.setSpacing(Space.md)
        container_layout.addWidget(widget)
        container_layout.addStretch(1)
        scroll.setWidget(container)
        return scroll

    # -- sol panel sayfalari ---------------------------------------------

    def _build_link_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Space.md)

        demo = Card("Local demo (no Gazebo)")
        demo_hint = QLabel(
            "Runs sim/fake_vehicle.py as a real MAVLink peer on this machine — "
            "no Ubuntu box or Gazebo needed. Starting it fills in UDP "
            "0.0.0.0:14550 and connects automatically."
        )
        demo_hint.setObjectName("cardHint")
        demo_hint.setWordWrap(True)
        demo.add(demo_hint)

        self.demo_status_label = QLabel("Stopped")
        self.demo_status_label.setStyleSheet(
            f'font-family: "{mono_font_family()}"; font-size: {Type.label}px;'
            f"color: {COLORS.text_secondary};"
        )
        demo.add(FormRow("Status", self.demo_status_label))

        demo_grid = QGridLayout()
        demo_grid.setHorizontalSpacing(Space.sm)
        demo_grid.setVerticalSpacing(Space.sm)
        self.demo_cruise_spin = self._double_spin(2.5, 0.1, 20.0, 0.1, " m/s")
        self.demo_turn_rate_spin = self._double_spin(35.0, 5.0, 180.0, 5.0, " deg/s")
        self.demo_depth_spin = self._double_spin(8.0, 0.5, 100.0, 0.5, " m")
        demo_grid.addWidget(FormRow("Cruise speed", self.demo_cruise_spin), 0, 0)
        demo_grid.addWidget(FormRow("Turn rate", self.demo_turn_rate_spin), 0, 1)
        demo_grid.addWidget(FormRow("Seabed depth", self.demo_depth_spin), 1, 0)
        demo.add_layout(demo_grid)
        self.demo_depth_toggle = toggle("Emit depth (sonar) readings", True)
        demo.add(self.demo_depth_toggle)

        demo.add_divider()
        demo.add(section_label("Fault injection"))
        fault_hint = QLabel(
            "Reproduce a specific failure path instead of normal operation."
        )
        fault_hint.setObjectName("cardHint")
        demo.add(fault_hint)
        # (cli flag, label) — cli flag is exactly sim/fake_vehicle.py's --fault choice.
        fault_flags = [
            ("reject-goto", "Reject Go to point (exercises the MP fallback)"),
            ("drop-waypoints", "Silently drop waypoints (exercises MISMATCH)"),
            ("corrupt-waypoint", "Silently corrupt a waypoint (exercises MISMATCH)"),
            ("no-gps", "No GPS fix (arming refused)"),
            ("no-telemetry", "Heartbeat only, no telemetry"),
        ]
        self.demo_fault_toggles: dict[str, QCheckBox] = {}
        for flag, label in fault_flags:
            box = toggle(label, False)
            demo.add(box)
            self.demo_fault_toggles[flag] = box

        demo_actions = QWidget()
        demo_actions_layout = QHBoxLayout(demo_actions)
        demo_actions_layout.setContentsMargins(0, 0, 0, 0)
        demo_actions_layout.setSpacing(Space.sm)
        self.demo_start_button = button("Start demo", "primary", self._start_demo)
        self.demo_stop_button = button("Stop demo", "danger", self._stop_demo)
        self.demo_stop_button.setEnabled(False)
        demo_actions_layout.addWidget(self.demo_start_button, 1)
        demo_actions_layout.addWidget(self.demo_stop_button, 1)
        demo.add(demo_actions)
        layout.addWidget(demo)

        card = Card("Connection")
        self.link_type_control = SegmentedControl(["UDP", "TCP", "Serial"])
        self.link_type_control.changed.connect(lambda _text: self._update_connection_string())
        card.add(self.link_type_control)

        self.host_edit = QLineEdit("127.0.0.1")
        self.host_edit.textChanged.connect(self._update_connection_string)
        self.port_edit = QLineEdit("14550")
        self.port_edit.textChanged.connect(self._update_connection_string)
        # A bare text field meant guessing which COM port the autopilot took —
        # on this machine COM3 is a Bluetooth port and the Cube is on COM9.
        # The list shows what is actually plugged in, and marks the ports that
        # look like an autopilot.
        serial_picker = QWidget()
        serial_layout = QHBoxLayout(serial_picker)
        serial_layout.setContentsMargins(0, 0, 0, 0)
        serial_layout.setSpacing(Space.sm)
        self.serial_port_combo = QComboBox()
        self.serial_port_combo.setEditable(True)
        self.serial_port_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.serial_port_combo.currentIndexChanged.connect(
            lambda _i: self._update_connection_string()
        )
        self.serial_port_combo.lineEdit().textEdited.connect(
            lambda _t: self._update_connection_string()
        )
        serial_layout.addWidget(self.serial_port_combo, 1)
        rescan = button("Rescan", "quiet", self._rescan_serial_ports)
        rescan.setProperty("compact", "true")
        rescan.setToolTip("Look for serial ports again — use after plugging the autopilot in")
        serial_layout.addWidget(rescan)

        self.baud_edit = QLineEdit("115200")
        self.baud_edit.textChanged.connect(self._update_connection_string)

        self.host_row = FormRow("Host", self.host_edit)
        self.port_row = FormRow("Port", self.port_edit)
        self.serial_row = FormRow("Serial port", serial_picker)
        self.baud_row = FormRow("Baud rate", self.baud_edit)
        for row in (self.host_row, self.port_row, self.serial_row, self.baud_row):
            card.add(row)

        card.add_divider()
        self.connection_string_label = QLabel(self.connection_target)
        self.connection_string_label.setStyleSheet(
            f'font-family: "{mono_font_family()}"; font-size: {Type.label}px;'
            f"color: {COLORS.accent};"
        )
        card.add(FormRow("Resolved target", self.connection_string_label))

        self.auto_reconnect_checkbox = toggle("Auto reconnect", False)
        card.add(self.auto_reconnect_checkbox)

        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(Space.sm)
        self.connect_button = button("Connect", "primary", self._connect_vehicle)
        self.disconnect_button = button("Disconnect", "quiet", self.mavlink.disconnect_vehicle)
        actions_layout.addWidget(self.connect_button, 1)
        actions_layout.addWidget(self.disconnect_button, 1)
        card.add(actions)
        layout.addWidget(card)

        # Gorunmez durum etiketi — otomatik yeniden baglanma mantigi bunu okuyor.
        self.link_status_label = QLabel("Disconnected", card)
        self.link_status_label.hide()

        health = Card("Link health")
        self.row_link_quality = KeyValueRow("Signal quality", "—")
        self.row_failsafe = KeyValueRow("Failsafe", "UNKNOWN")
        self.row_ekf = KeyValueRow("EKF", "UNKNOWN")
        for row in (self.row_link_quality, self.row_failsafe, self.row_ekf):
            health.add(row)
        layout.addWidget(health)

        self._rescan_serial_ports(announce=False)
        self._update_connection_string()
        return page

    def _build_vehicle_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Space.md)

        position = Card("Position")
        grid = MetricGrid(2)
        self.tile_lat = grid.add_tile(MetricTile("Latitude", "—"))
        self.tile_lon = grid.add_tile(MetricTile("Longitude", "—"))
        position.add(grid)
        position.add_divider()
        self.row_fix = KeyValueRow("GPS fix", "—")
        position.add(self.row_fix)
        layout.addWidget(position)

        attitude = Card("Attitude & motion")
        att_grid = MetricGrid(2)
        self.tile_roll = att_grid.add_tile(MetricTile("Roll", "—", "deg"))
        self.tile_pitch = att_grid.add_tile(MetricTile("Pitch", "—", "deg"))
        self.tile_speed_v = att_grid.add_tile(MetricTile("Ground speed", "—", "m/s"))
        self.tile_heading_v = att_grid.add_tile(MetricTile("Heading", "—", "deg"))
        attitude.add(att_grid)
        layout.addWidget(attitude)

        state = Card("Flight state")
        self.row_mode = KeyValueRow("Mode", "UNKNOWN")
        self.row_armed = KeyValueRow("Armed", "No")
        self.row_system = KeyValueRow("System", "UNKNOWN")
        for row in (self.row_mode, self.row_armed, self.row_system):
            state.add(row)
        layout.addWidget(state)
        return page

    def _build_power_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Space.md)

        card = Card("Battery")
        self.battery_pill = StatusPill("NO DATA", "neutral")
        card.add_header_widget(self.battery_pill)
        self.battery_gauge = BatteryGauge()
        card.add(self.battery_gauge)
        card.add_divider()
        self.row_voltage = KeyValueRow("Voltage", "—")
        self.row_current = KeyValueRow("Current", "—")
        self.row_remaining = KeyValueRow("Remaining", "—")
        self.row_runtime = KeyValueRow("Est. runtime", "—")
        for row in (self.row_voltage, self.row_current, self.row_remaining, self.row_runtime):
            card.add(row)
        layout.addWidget(card)

        note = Card("Note", flat=True)
        hint = QLabel(
            "The endurance estimate assumes a 20 Ah pack and the current draw reported "
            "by SYS_STATUS. Calibrate the pack capacity for accurate figures."
        )
        hint.setObjectName("cardHint")
        hint.setWordWrap(True)
        note.add(hint)
        layout.addWidget(note)
        return page

    def _build_pilot_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Space.md)

        modes = Card("Flight mode")
        mode_grid = QGridLayout()
        mode_grid.setContentsMargins(0, 0, 0, 0)
        mode_grid.setHorizontalSpacing(Space.sm)
        mode_grid.setVerticalSpacing(Space.sm)
        self.mode_buttons: dict[str, QPushButton] = {}
        for index, (name, _summary) in enumerate(self.FLIGHT_MODES):
            mode_button = button(name.title(), "quiet")
            mode_button.setProperty("compact", "true")
            mode_button.setCheckable(True)
            mode_button.clicked.connect(lambda _checked=False, mode=name: self._set_flight_mode(mode))
            mode_grid.addWidget(self._gated(mode_button, "link"), index // 3, index % 3)
            self.mode_buttons[name] = mode_button
        modes.add_layout(mode_grid)

        modes.add_divider()
        mode_help = QLabel(
            "".join(
                f'<p style="margin:0 0 4px 0;">'
                f'<span style="color:{COLORS.accent}; font-weight:700;">{name}</span>'
                f" — {summary}</p>"
                for name, summary in self.FLIGHT_MODES
            )
        )
        mode_help.setObjectName("cardHint")
        mode_help.setTextFormat(Qt.TextFormat.RichText)
        mode_help.setWordWrap(True)
        modes.add(mode_help)
        layout.addWidget(modes)

        stick_card = Card("Virtual joystick")
        self.joystick = VirtualJoystick()
        stick_row = QHBoxLayout()
        stick_row.addStretch(1)
        stick_row.addWidget(self.joystick)
        stick_row.addStretch(1)
        stick_card.add_layout(stick_row)

        self.joystick_readout = QLabel("throttle —   steering —")
        self.joystick_readout.setObjectName("cardHint")
        self.joystick_readout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stick_card.add(self.joystick_readout)

        stick_hint = QLabel(
            "Hold and drag to drive. Releasing re-centres the stick and sends "
            "neutral. Needs MANUAL mode and an armed vehicle."
        )
        stick_hint.setObjectName("cardHint")
        stick_hint.setWordWrap(True)
        stick_card.add(stick_hint)
        layout.addWidget(stick_card)

        manual = Card("Manual control")
        self.throttle_slider = QSlider(Qt.Orientation.Horizontal)
        self.throttle_slider.setRange(-100, 100)
        self.yaw_slider = QSlider(Qt.Orientation.Horizontal)
        self.yaw_slider.setRange(-100, 100)
        self.throttle_value_label = QLabel("0%")
        self.yaw_value_label = QLabel("0%")
        for value_label in (self.throttle_value_label, self.yaw_value_label):
            value_label.setStyleSheet(
                f'font-family: "{mono_font_family()}"; font-size: {Type.label}px;'
                f"font-weight: 700; color: {COLORS.text_primary};"
            )
            value_label.setFixedWidth(46)
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.throttle_slider.valueChanged.connect(
            lambda value: self.throttle_value_label.setText(f"{value}%")
        )
        self.yaw_slider.valueChanged.connect(
            lambda value: self.yaw_value_label.setText(f"{value}%")
        )

        for caption, slider, value_label in (
            ("Throttle", self.throttle_slider, self.throttle_value_label),
            ("Yaw", self.yaw_slider, self.yaw_value_label),
        ):
            block = QWidget()
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(Space.xs)
            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)
            head.addWidget(field_label(caption))
            head.addStretch(1)
            head.addWidget(value_label)
            block_layout.addLayout(head)
            block_layout.addWidget(slider)
            manual.add(block)

        manual.add_divider()
        send_row = QWidget()
        send_layout = QHBoxLayout(send_row)
        send_layout.setContentsMargins(0, 0, 0, 0)
        send_layout.setSpacing(Space.sm)
        send_layout.addWidget(
            self._gated(button("Send stick input", "primary", self._send_manual_control), "link"), 1
        )
        send_layout.addWidget(button("Center", "ghost", self._center_sticks))
        manual.add(send_row)
        layout.addWidget(manual)

        arming = Card("Arming")
        arm_row = QWidget()
        arm_layout = QHBoxLayout(arm_row)
        arm_layout.setContentsMargins(0, 0, 0, 0)
        arm_layout.setSpacing(Space.sm)
        arm_layout.addWidget(
            self._gated(button("Arm", "primary", self.mavlink.arm_vehicle), "link"), 1
        )
        arm_layout.addWidget(
            self._gated(button("Disarm", "danger", self._confirm_disarm), "link"), 1
        )
        arming.add(arm_row)
        layout.addWidget(arming)
        return page

    def _build_camera_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Space.md)
        layout.addWidget(self.camera_panel)
        return page

    # -- sag panel sekmeleri ---------------------------------------------

    def _build_plan_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Space.md)

        survey = Card("Survey parameters")
        self.track_spacing_spin = self._double_spin(30.0, 5.0, 500.0, 1.0, " m")
        self.sample_spacing_spin = self._double_spin(10.0, 1.0, 500.0, 1.0, " m")
        self.speed_spin = self._double_spin(2.0, 0.1, 20.0, 0.1, " m/s")
        self.angle_spin = self._double_spin(0.0, -180.0, 180.0, 1.0, " deg")
        self.overlap_spin = self._double_spin(0.3, 0.0, 0.95, 0.05)
        self.turn_radius_spin = self._double_spin(5.0, 0.0, 200.0, 0.5, " m")

        grid = QGridLayout()
        grid.setHorizontalSpacing(Space.sm)
        grid.setVerticalSpacing(Space.sm)
        pairs = [
            ("Track spacing", self.track_spacing_spin),
            ("Sample spacing", self.sample_spacing_spin),
            ("Survey speed", self.speed_spin),
            ("Heading", self.angle_spin),
        ]
        for index, (caption, widget) in enumerate(pairs):
            grid.addWidget(FormRow(caption, widget), index // 2, index % 2)
        grid.addWidget(FormRow("Overlap ratio", self.overlap_spin), 2, 0)
        grid.addWidget(FormRow("Turn radius", self.turn_radius_spin), 2, 1)
        survey.add_layout(grid)

        # Speed can be retargeted mid-survey, so it gets its own command
        # rather than only riding along with a mission upload.
        self.tuning_button = button("Vehicle tuning", "ghost")
        self.tuning_button.setProperty("compact", "true")
        self.tuning_button.setToolTip(
            "Read and write the vehicle parameters that shape turns and tracking"
        )
        self.tuning_button.clicked.connect(self._show_tuning)
        survey.add(self._gated(self.tuning_button, "link"))

        self.setup_button = button("Vehicle setup & calibration", "ghost")
        self.setup_button.setProperty("compact", "true")
        self.setup_button.setToolTip(
            "Full setup screen: parameters, radio / accelerometer / compass "
            "calibration, motor test, failsafe and sonar — no Mission Planner needed"
        )
        self.setup_button.clicked.connect(self._show_setup)
        survey.add(self._gated(self.setup_button, "link"))

        self.adaptive_speed_toggle = toggle("Slow through turns", True)
        self.adaptive_speed_toggle.setToolTip(
            "Track MISSION_CURRENT and cut speed on the turn-around arcs, "
            "restoring survey speed on the straight lanes."
        )
        survey.add(self.adaptive_speed_toggle)
        self.row_wp_radius = KeyValueRow("Vehicle WP_RADIUS", "—")
        survey.add(self.row_wp_radius)

        self.apply_speed_button = button("Apply speed now", "ghost")
        self.apply_speed_button.setProperty("compact", "true")
        self.apply_speed_button.setToolTip(
            "Send DO_CHANGE_SPEED immediately, without re-uploading the mission."
        )
        self.apply_speed_button.clicked.connect(
            lambda: self.mavlink.set_speed(self.speed_spin.value())
        )
        survey.add(self._gated(self.apply_speed_button, "link"))

        self.turn_warning = QLabel()
        self.turn_warning.setObjectName("cardHint")
        self.turn_warning.setWordWrap(True)
        self.turn_warning.setStyleSheet(f"color: {COLORS.warning};")
        self.turn_warning.hide()
        survey.add(self.turn_warning)
        for spin in (self.track_spacing_spin, self.overlap_spin, self.turn_radius_spin):
            spin.valueChanged.connect(self._refresh_turn_warning)

        survey.add_divider()
        actions = QWidget()
        actions_layout = QGridLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(Space.sm)
        actions_layout.addWidget(
            self._gated(button("Generate path", "primary", self._generate_survey), "polygon"),
            0, 0, 1, 2,
        )
        actions_layout.addWidget(
            self._gated(button("Upload", "quiet", self._upload_mission), "mission"), 1, 0
        )
        actions_layout.addWidget(
            self._gated(button("Start", "quiet", self.mavlink.start_mission), "mission"), 1, 1
        )
        actions_layout.addWidget(
            self._gated(button("Hold", "quiet", self.mavlink.stop_mission), "link"), 2, 0
        )
        actions_layout.addWidget(
            self._gated(button("Resume", "quiet", self.mavlink.resume_mission), "link"), 2, 1
        )
        actions_layout.addWidget(
            self._gated(button("Return home", "quiet", self._confirm_return_home), "link"),
            3, 0, 1, 2,
        )
        survey.add(actions)
        layout.addWidget(survey)

        alarms = Card("Depth alarm window")
        self.depth_low_spin = self._double_spin(1.0, 0.0, 1000.0, 0.5, " m")
        self.depth_high_spin = self._double_spin(20.0, 0.0, 1000.0, 0.5, " m")
        alarm_row = QWidget()
        alarm_layout = QHBoxLayout(alarm_row)
        alarm_layout.setContentsMargins(0, 0, 0, 0)
        alarm_layout.setSpacing(Space.sm)
        alarm_layout.addWidget(FormRow("Low", self.depth_low_spin), 1)
        alarm_layout.addWidget(FormRow("High", self.depth_high_spin), 1)
        alarms.add(alarm_row)
        layout.addWidget(alarms)

        samples = Card("Sample points")
        self.show_sample_numbers_checkbox = toggle("Number samples", False)
        self.show_sample_numbers_checkbox.toggled.connect(self._refresh_sample_points)
        self.density_preview_checkbox = toggle("Density preview", False)
        self.density_preview_checkbox.toggled.connect(self._refresh_sample_points)
        self.selected_lane_combo = QComboBox()
        self.selected_lane_combo.addItem("All lanes", -1)
        self.selected_lane_combo.currentIndexChanged.connect(self._refresh_sample_points)
        samples.add(self.show_sample_numbers_checkbox)
        samples.add(self.density_preview_checkbox)
        samples.add(FormRow("Visible lane", self.selected_lane_combo))
        layout.addWidget(samples)

        hint_card = Card("How it works", flat=True)
        hint = QLabel(
            "Track spacing defines the distance between survey lanes. Sample spacing "
            "only controls sonar trigger density along each lane. Draw the polygon "
            "using the map toolbar, then generate the coverage path."
        )
        hint.setObjectName("cardHint")
        hint.setWordWrap(True)
        hint_card.add(hint)
        layout.addWidget(hint_card)
        return page

    def _build_mission_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Space.md)

        progress = Card("Mission progress")
        # Header widgets cost no extra rows, so the coordinate list opens from
        # here rather than adding a permanent panel.
        self.waypoint_list_button = button("Coordinates", "ghost")
        self.waypoint_list_button.setProperty("compact", "true")
        self.waypoint_list_button.setToolTip("Show the generated waypoints and their coordinates")
        self.waypoint_list_button.clicked.connect(self._show_waypoint_list)
        progress.add_header_widget(self.waypoint_list_button)
        self.mission_state_pill = StatusPill("NO MISSION", "neutral")
        progress.add_header_widget(self.mission_state_pill)
        self.progress_bar = MissionProgressBar()
        progress.add(self.progress_bar)
        grid = MetricGrid(2)
        self.tile_waypoint = grid.add_tile(MetricTile("Waypoint", "0 / 0"))
        self.tile_remaining = grid.add_tile(MetricTile("Remaining", "0", "m"))
        self.tile_eta = grid.add_tile(MetricTile("ETA", "—"))
        self.tile_next_leg = grid.add_tile(MetricTile("Next leg", "—", "m"))
        progress.add(grid)
        layout.addWidget(progress)

        analytics = Card("Survey analytics")
        analytics_grid = MetricGrid(2)
        self.tile_area = analytics_grid.add_tile(MetricTile("Area", "0", "m²"))
        self.tile_track_length = analytics_grid.add_tile(MetricTile("Track length", "0", "m"))
        self.tile_samples = analytics_grid.add_tile(MetricTile("Expected samples", "0"))
        self.tile_duration = analytics_grid.add_tile(MetricTile("Est. duration", "—"))
        analytics.add(analytics_grid)
        layout.addWidget(analytics)

        home = Card("Home & track")
        self.row_home = KeyValueRow("Home point", "—")
        home.add(self.row_home)
        home_actions = QWidget()
        home_layout = QHBoxLayout(home_actions)
        home_layout.setContentsMargins(0, 0, 0, 0)
        home_layout.setSpacing(Space.sm)
        home_layout.addWidget(button("Set home", "quiet", self._set_home_from_vehicle), 1)
        home_layout.addWidget(button("Clear track", "ghost", self._clear_track), 1)
        home.add(home_actions)
        layout.addWidget(home)
        return page

    def _build_depth_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Space.md)

        current = Card("Sonar depth")
        self.bathymetry_button = button("2D map", "ghost")
        self.bathymetry_button.setProperty("compact", "true")
        self.bathymetry_button.setToolTip(
            "Plot the soundings collected at the planned sample points"
        )
        self.bathymetry_button.clicked.connect(self._show_bathymetry)
        current.add_header_widget(self.bathymetry_button)
        self.depth_alarm_pill = StatusPill("NO DATA", "neutral")
        current.add_header_widget(self.depth_alarm_pill)
        self.tile_depth_large = MetricTile("Current depth", "—", "m", large=True)
        current.add(self.tile_depth_large)
        self.depth_sparkline = Sparkline(COLORS.info)
        current.add(self.depth_sparkline)
        current.add(DepthLegend())
        layout.addWidget(current)

        stats = Card("Session statistics")
        grid = MetricGrid(2)
        self.tile_min_depth = grid.add_tile(MetricTile("Minimum", "—", "m"))
        self.tile_max_depth = grid.add_tile(MetricTile("Maximum", "—", "m"))
        stats.add(grid)
        stats.add_divider()
        self.row_last_sample = KeyValueRow("Last sample", "—")
        self.row_sample_count = KeyValueRow("Samples buffered", "0")
        self.row_collected = KeyValueRow("Sample points covered", "0 / 0")
        stats.add(self.row_last_sample)
        stats.add(self.row_sample_count)
        stats.add(self.row_collected)
        layout.addWidget(stats)
        return page

    # -- konsol / durum ---------------------------------------------------

    def _build_console_drawer(self) -> QWidget:
        self.console_drawer = QWidget()
        self.console_drawer.setObjectName("statusStrip")
        layout = QVBoxLayout(self.console_drawer)
        layout.setContentsMargins(Space.lg, Space.sm, Space.lg, Space.sm)
        layout.setSpacing(Space.xs)
        layout.addWidget(section_label("Event console"))
        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        self.status_log.setFixedHeight(150)
        layout.addWidget(self.status_log)
        self.console_drawer.hide()
        return self.console_drawer

    def _build_status_strip(self) -> QWidget:
        strip = QWidget()
        strip.setObjectName("statusStrip")
        strip.setFixedHeight(38)
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(Space.lg, 0, Space.lg, 0)
        layout.setSpacing(Space.md)

        self.status_dot = LiveDot()
        self.status_message = QLabel("Ready")
        self.status_message.setStyleSheet(
            f"font-size: {Type.label}px; color: {COLORS.text_secondary};"
        )
        self.status_time = QLabel("--:--:--")
        self.status_time.setStyleSheet(
            f'font-family: "{mono_font_family()}"; font-size: {Type.caption}px;'
            f"color: {COLORS.text_tertiary};"
        )
        self.waypoint_summary = QLabel("0 waypoints")
        self.waypoint_summary.setStyleSheet(
            f"font-size: {Type.caption}px; color: {COLORS.text_tertiary};"
        )
        self.msg_rate_label = QLabel("MAVLink — /s")
        self.msg_rate_label.setStyleSheet(
            f'font-family: "{mono_font_family()}"; font-size: {Type.caption}px;'
            f"color: {COLORS.text_tertiary};"
        )
        self.refresh_rate_label = QLabel("UI — Hz")
        self.refresh_rate_label.setStyleSheet(
            f'font-family: "{mono_font_family()}"; font-size: {Type.caption}px;'
            f"color: {COLORS.text_tertiary};"
        )

        layout.addWidget(self.status_dot)
        layout.addWidget(self.status_message, 1)
        layout.addWidget(self.waypoint_summary)
        layout.addWidget(v_divider(16))
        layout.addWidget(self.msg_rate_label)
        layout.addWidget(self.refresh_rate_label)
        layout.addWidget(v_divider(16))
        layout.addWidget(self.status_time)
        return strip

    def _toggle_console(self, visible: bool) -> None:
        self.console_visible = visible
        self.console_drawer.setVisible(visible)

    # -- harita araclari --------------------------------------------------

    def _wire_map_tools(self) -> None:
        pane = self.map_pane
        pane.cone_toggle.toggled.connect(self.map_widget.set_heading_cone_visible)
        pane.measure_toggle.toggled.connect(self.map_widget.set_measure_mode)
        pane.goto_toggle.toggled.connect(self.map_widget.set_goto_mode)
        self._gated(pane.goto_toggle, "link")
        self._refresh_control_states()
        pane.clear_track_button.clicked.connect(self._clear_track)
        self._gated(pane.home_button, "link")
        pane.home_button.clicked.connect(self._set_home_from_vehicle)
        pane.focus_button.clicked.connect(self.map_widget.focus_vehicle)
        pane.draw_button.clicked.connect(self.map_widget.start_polygon)
        pane.finish_button.clicked.connect(self.map_widget.finish_polygon)
        pane.clear_polygon_button.clicked.connect(self.map_widget.clear_polygon)
        pane.layer_control.changed.connect(
            lambda text: self.map_widget.set_base_layer(
                "satellite" if text == "Satellite" else "street"
            )
        )
        # Eski isimlerle uyumluluk
        self.heading_cone_checkbox = pane.cone_toggle
        self.measure_checkbox = pane.measure_toggle

    def _double_spin(
        self,
        value: float,
        minimum: float,
        maximum: float,
        step: float,
        suffix: str = "",
    ) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setDecimals(2)
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setSingleStep(step)
        widget.setSuffix(suffix)
        return widget

    def _setup_timers(self) -> None:
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.setInterval(3000)
        self.reconnect_timer.timeout.connect(self._attempt_reconnect)
        self.reconnect_timer.start()

        self.refresh_rate_timer = QTimer(self)
        self.refresh_rate_timer.setInterval(1000)
        self.refresh_rate_timer.timeout.connect(self._report_refresh_rate)
        self.refresh_rate_timer.start()

        # Poll the latest telemetry snapshot on the GUI thread instead of being
        # pushed to via a cross-thread signal from the MAVLink receive thread —
        # that path was measured to only deliver ~2 updates/s regardless of
        # throttling, apparently due to Qt signal contention with QWebEngineView.
        self.telemetry_poll_timer = QTimer(self)
        self.telemetry_poll_timer.setInterval(50)  # 20 Hz
        self.telemetry_poll_timer.timeout.connect(self._poll_telemetry)
        self.telemetry_poll_timer.start()

    def _poll_telemetry(self) -> None:
        self._on_telemetry_updated(self.mavlink.get_telemetry())

    def _report_refresh_rate(self) -> None:
        count = self._refresh_count
        self.refresh_rate_label.setText(f"UI {count} Hz")
        if count:
            avg_total_ms = (self._telemetry_total_time / count) * 1000
            avg_map_ms = (self._telemetry_map_time / count) * 1000
            avg_rest_ms = (self._telemetry_rest_time / count) * 1000
            breakdown_message = (
                f"UI timing: {count} calls/s, avg {avg_total_ms:.1f}ms total "
                f"(map JS: {avg_map_ms:.1f}ms, rest: {avg_rest_ms:.1f}ms), "
                f"attitude/heading changed {self._value_change_count}/s | "
                f"raw roll={self._number_text(self._last_seen_roll, '{:.3f}')} "
                f"pitch={self._number_text(self._last_seen_pitch, '{:.3f}')} "
                f"heading={self._number_text(self._last_seen_heading, '{:.3f}')}"
            )
            # qDebug() only takes ASCII; the readouts now use an em dash.
            qDebug(breakdown_message.encode("ascii", "backslashreplace").decode("ascii"))
            self._append_status(breakdown_message)
        self._refresh_count = 0
        self._telemetry_total_time = 0.0
        self._telemetry_map_time = 0.0
        self._telemetry_rest_time = 0.0
        self._value_change_count = 0

    def _on_message_rate_updated(self, rate_hz: float) -> None:
        self.msg_rate_label.setText(f"MAVLink {rate_hz:.0f}/s")

    # -- baglanti ---------------------------------------------------------

    def _rescan_serial_ports(self, announce: bool = True) -> None:
        """Refill the port list, keeping the operator's choice if it survived."""
        from gcs.serial_ports import available_ports, best_guess

        previous = self._selected_serial_port()
        ports = available_ports()
        combo = self.serial_port_combo
        combo.blockSignals(True)
        combo.clear()
        for info in ports:
            combo.addItem(info.label, info.device)
        combo.blockSignals(False)

        if not ports:
            combo.setEditText("")
            if announce:
                self._append_status("No serial ports found.")
            self._update_connection_string()
            return

        target = previous if previous in {p.device for p in ports} else None
        if target is None:
            guess = best_guess(ports)
            target = guess.device if guess is not None else ports[0].device
        index = combo.findData(target)
        combo.setCurrentIndex(index if index >= 0 else 0)

        if announce:
            autopilots = [p for p in ports if p.is_autopilot and p.speaks_mavlink]
            if autopilots:
                self._append_status(
                    f"{len(ports)} serial port(s); autopilot detected on "
                    + ", ".join(p.device for p in autopilots)
                )
            else:
                self._append_status(
                    f"{len(ports)} serial port(s), none of which look like an autopilot."
                )
        self._update_connection_string()

    def _selected_serial_port(self) -> str:
        """The COM port itself, not the descriptive label shown in the list."""
        combo = getattr(self, "serial_port_combo", None)
        if combo is None:
            return ""
        data = combo.currentData()
        text = combo.currentText().strip()
        # A typed-in value has no item data, and picking from the list gives a
        # label like "COM9 — Cube Orange Mavlink" that is not a port name.
        if data and text == combo.itemText(combo.currentIndex()):
            return str(data)
        return text.split(" ")[0] if text else ""

    def _update_connection_string(self) -> None:
        link_type = (
            self.link_type_control.current_text() if hasattr(self, "link_type_control") else "UDP"
        )
        is_serial = link_type == "Serial"
        if hasattr(self, "host_row"):
            self.host_row.setVisible(not is_serial)
            self.port_row.setVisible(not is_serial)
            self.serial_row.setVisible(is_serial)
            self.baud_row.setVisible(is_serial)
        if link_type == "UDP":
            self.connection_target = f"udp:{self.host_edit.text().strip()}:{self.port_edit.text().strip()}"
        elif link_type == "TCP":
            self.connection_target = f"tcp:{self.host_edit.text().strip()}:{self.port_edit.text().strip()}"
        else:
            self.connection_target = (
                f"{self._selected_serial_port()},{self.baud_edit.text().strip()}"
            )
        if hasattr(self, "connection_string_label"):
            self.connection_string_label.setText(self.connection_target)

    def _connect_vehicle(self) -> None:
        self._update_connection_string()
        self.mavlink.connect_vehicle(self.connection_target)

    # -- yerel demo simulatoru ---------------------------------------------

    def _start_demo(self) -> None:
        if self._demo_process is not None and self._demo_process.poll() is None:
            return  # already running

        # A leftover end-of-stream sentinel from a previous run, not yet
        # drained, would otherwise be read as *this* process having already
        # exited — clearing self._demo_process while it is still running and
        # orphaning it (closeEvent no-ops when self._demo_process is None).
        while not self._demo_output_queue.empty():
            try:
                self._demo_output_queue.get_nowait()
            except queue.Empty:
                break

        args = [
            sys.executable, "-m", "sim.fake_vehicle",
            "--cruise", str(self.demo_cruise_spin.value()),
            "--turn-rate", str(self.demo_turn_rate_spin.value()),
            "--depth-base", str(self.demo_depth_spin.value()),
        ]
        if not self.demo_depth_toggle.isChecked():
            args.append("--no-depth")
        for flag, box in self.demo_fault_toggles.items():
            if box.isChecked():
                args += ["--fault", flag]

        # sys.executable is this app's own venv interpreter, so the simulator
        # runs with the same pymavlink the GCS itself uses.
        project_root = Path(__file__).resolve().parent.parent
        popen_kwargs = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            self._demo_process = subprocess.Popen(
                args,
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                **popen_kwargs,
            )
        except OSError as exc:
            self._append_status(f"Failed to start local demo: {exc}")
            return

        self._demo_reader_thread = threading.Thread(
            target=self._read_demo_output, daemon=True
        )
        self._demo_reader_thread.start()
        self._demo_output_timer.start()

        self.demo_status_label.setText(f"Running (PID {self._demo_process.pid})")
        self.demo_status_label.setStyleSheet(
            f'font-family: "{mono_font_family()}"; font-size: {Type.label}px;'
            f"color: {COLORS.success};"
        )
        self.demo_start_button.setEnabled(False)
        self.demo_stop_button.setEnabled(True)
        self._append_status("Local demo simulator started.")

        # Point the link at it and connect once it has had a moment to bind
        # its socket and start sending heartbeats.
        self.link_type_control.set_current("UDP")
        self.host_edit.setText("0.0.0.0")
        self.port_edit.setText("14550")
        QTimer.singleShot(1000, self._connect_vehicle)

    def _read_demo_output(self) -> None:
        """Runs on a background thread — stdout is a blocking pipe."""
        process = self._demo_process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            self._demo_output_queue.put(line.rstrip())
        self._demo_output_queue.put(None)  # sentinel: process exited

    def _drain_demo_output(self) -> None:
        ended = False
        while True:
            try:
                line = self._demo_output_queue.get_nowait()
            except queue.Empty:
                break
            if line is None:
                ended = True
            elif line:
                self._append_status(line)
        if ended:
            self._on_demo_ended()

    def _on_demo_ended(self) -> None:
        self._demo_output_timer.stop()
        self._demo_process = None
        self.demo_status_label.setText("Stopped")
        self.demo_status_label.setStyleSheet(
            f'font-family: "{mono_font_family()}"; font-size: {Type.label}px;'
            f"color: {COLORS.text_secondary};"
        )
        self.demo_start_button.setEnabled(True)
        self.demo_stop_button.setEnabled(False)

    def _stop_demo(self) -> None:
        process = self._demo_process
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        self._append_status("Local demo simulator stopped.")
        # The reader thread's sentinel will also arrive, but updating now
        # means the UI reflects Stop immediately rather than on the next
        # timer tick.
        self._on_demo_ended()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        # An orphaned demo process is easy to leave behind otherwise — it has
        # no window of its own to remind anyone it is still running.
        self._stop_demo()
        # The setup screen is a separate top-level window, so it would keep the
        # application alive after the main window closes.
        setup = getattr(self, "_setup_window", None)
        if setup is not None:
            setup.close()
        super().closeEvent(event)

    def _attempt_reconnect(self) -> None:
        if self.auto_reconnect_checkbox.isChecked() and self.link_status_label.text() == "Disconnected":
            self.mavlink.connect_vehicle(self.connection_target)

    def _on_connection_changed(self, connected: bool) -> None:
        self.connected = connected
        self._refresh_control_states()
        if not connected:
            for mode_button in self.mode_buttons.values():
                mode_button.setChecked(False)
        self.link_status_label.setText("Connected" if connected else "Disconnected")
        self.connect_button.setEnabled(not connected)
        self.link_state_pill.set_state(
            "CONNECTED" if connected else "DISCONNECTED",
            "success" if connected else "danger",
        )
        self.link_dot.set_tone(COLORS.success if connected else COLORS.danger)
        self.status_dot.set_tone(COLORS.success if connected else COLORS.text_tertiary)

    # -- gorev ------------------------------------------------------------

    def _generate_survey(self) -> None:
        if len(self.polygon_points) < 3:
            self._append_status("Draw a polygon on the map first.")
            return

        self.mission_points = self.planner.generate_survey_path(
            polygon_points=self.polygon_points,
            line_spacing_m=self.track_spacing_spin.value(),
            heading_deg=self.angle_spin.value(),
            overlap_ratio=self.overlap_spin.value(),
            sample_spacing_m=self.sample_spacing_spin.value(),
            altitude_m=0.0,
            turn_radius_m=self.turn_radius_spin.value(),
        )
        self.sample_points = self.planner.generate_sample_points(
            polygon_points=self.polygon_points,
            line_spacing_m=self.track_spacing_spin.value(),
            heading_deg=self.angle_spin.value(),
            overlap_ratio=self.overlap_spin.value(),
            sample_spacing_m=self.sample_spacing_spin.value(),
        )
        self.sample_points = [
            {**point, "index": index + 1} for index, point in enumerate(self.sample_points)
        ]
        # A new plan invalidates readings bound to the old sample grid.
        self.collected_samples.clear()
        self.row_collected.set_value(f"0 / {len(self.sample_points)}")

        if not self.mission_points:
            self._append_status("Survey generation returned no valid path.")
            self.map_widget.clear_survey()
            self.mission_state_pill.set_state("NO MISSION", "neutral")
            self._refresh_control_states()
            return

        self._refresh_control_states()
        self.map_widget.update_survey_path(self.mission_points)
        self._populate_lane_selector()
        self._refresh_sample_points()
        self._update_survey_analytics()
        self.mission_state_pill.set_state("PLANNED", "info")
        self.waypoint_summary.setText(f"{len(self.mission_points)} waypoints")
        self._append_status(f"Generated {len(self.mission_points)} mission points.")

    def _refresh_turn_warning(self) -> None:
        """Flag turn radii the lane spacing cannot accommodate.

        Below half the effective spacing the planner can join lanes with a
        plain semicircle. Above it the vehicle physically cannot turn in that
        gap, so the path has to swing wide outside the polygon.
        """
        spacing = self.track_spacing_spin.value() * max(0.05, 1.0 - self.overlap_spin.value())
        radius = self.turn_radius_spin.value()
        if radius <= spacing / 2.0:
            self.turn_warning.hide()
            return
        overshoot = math.sqrt(max(0.0, 4 * radius**2 - (radius - spacing / 2.0) ** 2)) + radius
        self.turn_warning.setText(
            f"Turn radius exceeds half the {spacing:.0f} m lane spacing, so each turn "
            f"loops about {overshoot:.0f} m outside the polygon. Reduce the radius or "
            f"widen the track spacing to keep turns tight."
        )
        self.turn_warning.show()

    def _show_waypoint_list(self) -> None:
        """Open the generated waypoints and their coordinates on demand."""
        if not hasattr(self, "_waypoint_dialog") or self._waypoint_dialog is None:
            self._waypoint_dialog = WaypointListDialog(self)
        self._waypoint_dialog.set_points(self.mission_points)
        self._waypoint_dialog.show()
        self._waypoint_dialog.raise_()
        self._waypoint_dialog.activateWindow()

    def _upload_mission(self) -> None:
        self.mission_state_pill.set_state("UPLOADING", "info")
        self.mavlink.upload_mission(self.mission_points, self.speed_spin.value())

    def _on_mission_verified(self, verified: bool, _summary: str) -> None:
        if verified:
            self.mission_state_pill.set_state("VERIFIED", "success")
        else:
            self.mission_state_pill.set_state("MISMATCH", "danger")

    def _set_flight_mode(self, mode_name: str) -> None:
        # The button re-checks itself on click; the real state comes back on the
        # next HEARTBEAT, so undo the optimistic check here.
        self._sync_mode_buttons(self.mavlink.get_telemetry().mode)
        self.mavlink.set_mode(mode_name)

    def _sync_mode_buttons(self, active_mode: str | None) -> None:
        for name, mode_button in self.mode_buttons.items():
            mode_button.setChecked(name == active_mode)

    def _confirm(
        self,
        title: str,
        question: str,
        icon: QMessageBox.Icon = QMessageBox.Icon.Warning,
        default_yes: bool = False,
    ) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(question)
        box.setIcon(icon)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(
            QMessageBox.StandardButton.Yes if default_yes else QMessageBox.StandardButton.No
        )
        return box.exec() == QMessageBox.StandardButton.Yes

    # Fraction of survey speed to hold through the turn-around arcs.
    TURN_SPEED_RATIO = 0.45

    def _show_tuning(self) -> None:
        if getattr(self, "_tuning_dialog", None) is None:
            self._tuning_dialog = VehicleTuningDialog(self.mavlink, self)
            self.mavlink.parameter_received.connect(self._tuning_dialog.on_parameter)
        self._tuning_dialog.show()
        self._tuning_dialog.raise_()
        self._tuning_dialog.activateWindow()
        self._tuning_dialog.refresh()

    def _show_setup(self) -> None:
        """Open the full setup/calibration window (its own top-level window)."""
        if getattr(self, "_setup_window", None) is None:
            from gcs.setup_window import SetupWindow

            self._setup_window = SetupWindow(self.mavlink)
        self._setup_window.show()
        self._setup_window.raise_()
        self._setup_window.activateWindow()
        self._setup_window.refresh_armed_state(bool(self.mavlink.get_telemetry().armed))
        # Everything on that screen needs the parameter table, so fetch it on
        # first open rather than making the operator find the button.
        if not self._setup_window.all_params_page.table.rowCount():
            self.mavlink.download_parameters()

    def _on_waypoint_radius(self, radius_m: float) -> None:
        """Size turn-arc spacing from the vehicle's own acceptance radius."""
        if radius_m <= 0:
            return
        self.planner.waypoint_radius_m = radius_m
        self.row_wp_radius.set_value(f"{radius_m:.2f} m")
        self._append_status(
            f"Planner using vehicle WP_RADIUS {radius_m:.2f} m for turn spacing."
        )

    def _update_adaptive_speed(self, telemetry: TelemetryData) -> None:
        """Slow the vehicle through turns, restore survey speed on the lanes.

        Driven by MISSION_CURRENT rather than position, so it follows what the
        autopilot is actually navigating to. Speed is only re-sent when the
        segment type changes — DO_CHANGE_SPEED every telemetry tick would
        flood the link for no benefit.
        """
        if not self.adaptive_speed_toggle.isChecked():
            return
        if telemetry.mode != "AUTO" or not self.mission_points:
            self._active_segment_is_turn = None
            return

        seq = telemetry.current_waypoint_seq
        if seq is None or not (1 <= seq <= len(self.mission_points)):
            return

        in_turn = self.mission_points[seq - 1].is_turn
        if in_turn == self._active_segment_is_turn:
            return
        self._active_segment_is_turn = in_turn

        survey_speed = self.speed_spin.value()
        target = survey_speed * self.TURN_SPEED_RATIO if in_turn else survey_speed
        self.mavlink.set_speed(target)
        self._append_status(
            f"{'Turn' if in_turn else 'Lane'} segment at WP {seq} — "
            f"speed {target:.2f} m/s."
        )

    def _on_mission_completed(self, seq: int) -> None:
        del seq
        self.mission_state_pill.set_state("COMPLETE", "success")
        waypoints = len(self.mission_points)
        if self._confirm(
            "Mission complete",
            f"The survey finished — all {waypoints} waypoints covered.\n\n"
            "Return the vehicle home?",
            icon=QMessageBox.Icon.Question,
            default_yes=True,
        ):
            self.mavlink.return_to_launch()
        else:
            self._append_status("Mission complete. Vehicle left on station.")

    def _confirm_disarm(self) -> None:
        # Disarming underway cuts the motors and leaves the vehicle adrift.
        if self.mavlink.get_telemetry().armed and not self._confirm(
            "Disarm vehicle",
            "The vehicle is armed. Disarming cuts the motors immediately.\n\nDisarm anyway?",
        ):
            return
        self.mavlink.disarm_vehicle()

    def _confirm_return_home(self) -> None:
        running = self.mission_state_pill.text() in {"RUNNING", "VERIFIED"}
        if running and not self._confirm(
            "Return home",
            "This abandons the survey in progress and drives the vehicle back "
            "to its home position.\n\nReturn home?",
        ):
            return
        self.mavlink.return_to_launch()

    def _send_manual_control(self) -> None:
        self.mavlink.send_manual_control(self.throttle_slider.value(), self.yaw_slider.value())

    def _on_joystick_moved(self, steering: float, throttle: float) -> None:
        self._joystick_axes = (int(round(throttle * 100)), int(round(steering * 100)))
        self.joystick_readout.setText(
            f"throttle {self._joystick_axes[0]:+d}%   steering {self._joystick_axes[1]:+d}%"
        )
        if self.joystick.is_engaged():
            self._joystick_timer.start()
        else:
            # Released: hand the channels back to the vehicle's own RC input.
            self._joystick_timer.stop()
            if self.connected:
                self.mavlink.release_manual_control()

    def _stream_joystick(self) -> None:
        """ArduPilot expires manual overrides, so an active stick must repeat."""
        if not self.connected or not self.joystick.is_engaged():
            self._joystick_timer.stop()
            return
        throttle, steering = self._joystick_axes
        self.mavlink.send_manual_control(throttle, steering, announce=False)

    def _center_sticks(self) -> None:
        self.throttle_slider.setValue(0)
        self.yaw_slider.setValue(0)

    def _populate_lane_selector(self) -> None:
        self.selected_lane_combo.blockSignals(True)
        self.selected_lane_combo.clear()
        self.selected_lane_combo.addItem("All lanes", -1)
        lane_count = 1 + max((point["lane"] for point in self.sample_points), default=-1)
        for lane in range(lane_count):
            self.selected_lane_combo.addItem(f"Lane {lane + 1}", lane)
        self.selected_lane_combo.blockSignals(False)

    def _refresh_sample_points(self) -> None:
        lane = self.selected_lane_combo.currentData()
        points = (
            self.sample_points
            if lane in {-1, None}
            else [point for point in self.sample_points if point["lane"] == lane]
        )
        self.map_widget.update_sample_points(
            points,
            self.show_sample_numbers_checkbox.isChecked(),
            self.density_preview_checkbox.isChecked(),
        )

    def _set_home_from_vehicle(self) -> None:
        if self.last_track_point is None:
            self._append_status("No vehicle position available for home point.")
            return
        self.home_point = dict(self.last_track_point)
        self.map_widget.set_home_point(self.home_point["lat"], self.home_point["lng"])
        self.row_home.set_value(f"{self.home_point['lat']:.5f}, {self.home_point['lng']:.5f}")
        # Moving the marker alone used to leave the vehicle's own home
        # untouched, so RTL still drove back to wherever it booted up.
        self.mavlink.set_home_here()

    def _clear_track(self) -> None:
        self.last_track_point = None
        self.depth_samples.clear()
        self.collected_samples.clear()
        self.row_collected.set_value(f"0 / {len(self.sample_points)}")
        self.depth_sparkline.clear()
        self.map_widget.clear_track()
        self.map_widget.update_depth_heatmap([])
        self.row_sample_count.set_value("0")
        self._append_status("Track cleared.")

    def _on_polygon_changed(self, points: list[dict]) -> None:
        self.polygon_points = points
        self._refresh_control_states()
        if points:
            self._append_status(f"Polygon updated with {len(points)} vertices.")
        else:
            self.mission_points = []
            self.sample_points = []
            self.mission_state_pill.set_state("NO MISSION", "neutral")
            self.waypoint_summary.setText("0 waypoints")
            self._update_survey_analytics()
            self._refresh_control_states()

    def _on_waypoint_moved(self, index: int, latitude: float, longitude: float) -> None:
        if 0 <= index < len(self.mission_points):
            self.mission_points[index].latitude = latitude
            self.mission_points[index].longitude = longitude
            self._update_survey_analytics()
            self._append_status(f"Waypoint {index + 1} moved.")

    def _on_goto_selected(self, latitude: float, longitude: float) -> None:
        self._append_status(f"Go-to CLICKED  lat={latitude:.7f} lon={longitude:.7f}")
        self.mavlink.go_to(latitude, longitude)
        self.map_pane.goto_toggle.setChecked(False)

    # A sounding counts as "taken at" a planned sample point once the vehicle
    # passes within this radius of it.
    SAMPLE_CAPTURE_RADIUS_M = 6.0

    def _capture_sample_point(self, sample: DepthSample) -> None:
        """Bind an incoming sounding to the nearest planned sample point.

        The survey plan says where readings should be taken; this records what
        was actually measured there, so the bathymetry view plots the planned
        grid rather than the raw 5 Hz track.
        """
        if not self.sample_points:
            return
        nearest = None
        nearest_distance = self.SAMPLE_CAPTURE_RADIUS_M
        for point in self.sample_points:
            distance = _haversine_m(
                sample.latitude, sample.longitude, point["lat"], point["lng"]
            )
            if distance < nearest_distance:
                nearest, nearest_distance = point, distance
        if nearest is None:
            return

        index = nearest.get("index")
        previous = self.collected_samples.get(index)
        # Keep the reading taken closest to the planned position.
        if previous is not None and previous["offset_m"] <= nearest_distance:
            return
        self.collected_samples[index] = {
            "index": index,
            "lane": nearest.get("lane"),
            "lat": sample.latitude,
            "lng": sample.longitude,
            "depth": sample.depth_m,
            "offset_m": nearest_distance,
            "time": sample.timestamp,
        }
        self.row_collected.set_value(
            f"{len(self.collected_samples)} / {len(self.sample_points)}"
        )
        if hasattr(self, "_bathymetry_dialog") and self._bathymetry_dialog is not None:
            if not self._bathymetry_dialog.isHidden():
                self._bathymetry_dialog.set_samples(
                    list(self.collected_samples.values()), self.polygon_points
                )

    def _show_bathymetry(self) -> None:
        if not hasattr(self, "_bathymetry_dialog") or self._bathymetry_dialog is None:
            self._bathymetry_dialog = BathymetryDialog(self)
        self._bathymetry_dialog.set_samples(
            list(self.collected_samples.values()), self.polygon_points
        )
        self._bathymetry_dialog.show()
        self._bathymetry_dialog.raise_()
        self._bathymetry_dialog.activateWindow()

    def _on_depth_sample(self, sample: DepthSample) -> None:
        self._capture_sample_point(sample)
        self.depth_samples.append(sample)
        self.depth_samples = self.depth_samples[-300:]
        self.depth_sparkline.push(sample.depth_m)
        self.row_sample_count.set_value(str(len(self.depth_samples)))
        self.map_widget.update_depth_heatmap(
            [
                {"lat": item.latitude, "lng": item.longitude, "depth": item.depth_m}
                for item in self.depth_samples
            ]
        )

    # -- telemetri --------------------------------------------------------

    def _on_telemetry_updated(self, telemetry: TelemetryData) -> None:
        self._refresh_count += 1
        _t_start = time.perf_counter()
        if (
            telemetry.heading_deg != self._last_seen_heading
            or telemetry.roll_deg != self._last_seen_roll
            or telemetry.pitch_deg != self._last_seen_pitch
        ):
            self._value_change_count += 1
            self._last_seen_heading = telemetry.heading_deg
            self._last_seen_roll = telemetry.roll_deg
            self._last_seen_pitch = telemetry.pitch_deg
        depth_tone = depth_color(telemetry.depth_m)
        depth_text = f"{telemetry.depth_m:.2f}" if telemetry.depth_m is not None else "—"
        battery_pct = telemetry.battery_remaining_pct
        speed_text = self._number_text(telemetry.ground_speed_mps, "{:.1f}")
        heading_text = self._number_text(telemetry.heading_deg, "{:03.0f}")

        # Ust komuta cubugu
        self.tile_speed.set_value(speed_text)
        self.tile_heading.set_value(heading_text)
        self.tile_depth.set_value(depth_text, depth_tone)
        self.tile_battery.set_value(
            f"{battery_pct}" if battery_pct is not None else "—", self._battery_tone(battery_pct)
        )
        self.compass.set_heading(telemetry.heading_deg)
        self.mode_pill.set_state(
            telemetry.mode or "UNKNOWN",
            "info" if telemetry.mode not in {"", "UNKNOWN"} else "neutral",
        )
        self.armed_pill.set_state(
            "ARMED" if telemetry.armed else "DISARMED", "danger" if telemetry.armed else "neutral"
        )
        # Every calibration is refused while armed, so the setup screen shows
        # arm state prominently — keep it live while that window is open.
        setup = getattr(self, "_setup_window", None)
        if setup is not None and setup.isVisible():
            setup.refresh_armed_state(bool(telemetry.armed))
        self._sync_mode_buttons(telemetry.mode)
        self._update_adaptive_speed(telemetry)
        self.link_quality_pill.set_state(
            f"LINK {telemetry.link_quality_pct}%" if telemetry.link_quality_pct is not None else "LINK —",
            "success" if (telemetry.link_quality_pct or 0) >= 70 else "warning",
        )

        # Harita HUD
        self.map_pane.horizon_widget.set_attitude(telemetry.roll_deg, telemetry.pitch_deg)
        self.map_pane.set_hud(
            speed_text,
            f"{heading_text}°" if telemetry.heading_deg is not None else heading_text,
            depth_text,
            depth_tone,
        )

        # Arac paneli
        self.tile_lat.set_value(self._number_text(telemetry.latitude, "{:.5f}"))
        self.tile_lon.set_value(self._number_text(telemetry.longitude, "{:.5f}"))
        self.tile_roll.set_value(self._number_text(telemetry.roll_deg, "{:+.1f}"))
        self.tile_pitch.set_value(self._number_text(telemetry.pitch_deg, "{:+.1f}"))
        self.tile_speed_v.set_value(speed_text)
        self.tile_heading_v.set_value(heading_text)
        self.row_fix.set_value(
            self._fix_text(telemetry.fix_type),
            COLORS.success if (telemetry.fix_type or 0) >= 3 else COLORS.warning,
        )
        self.row_mode.set_value(telemetry.mode)
        self.row_armed.set_value(
            "Yes" if telemetry.armed else "No",
            COLORS.danger if telemetry.armed else COLORS.text_primary,
        )
        self.row_system.set_value(telemetry.system_status)
        self.row_link_quality.set_value(
            f"{telemetry.link_quality_pct or 0}%",
            COLORS.success if (telemetry.link_quality_pct or 0) >= 70 else COLORS.warning,
        )
        self.row_failsafe.set_value(telemetry.failsafe)
        self.row_ekf.set_value(
            telemetry.ekf_status,
            COLORS.success if telemetry.ekf_status == "OK" else COLORS.text_secondary,
        )

        # Guc paneli
        self.battery_gauge.set_state(
            float(battery_pct) if battery_pct is not None else None, telemetry.battery_voltage_v
        )
        self.battery_pill.set_state(
            f"{battery_pct}%" if battery_pct is not None else "NO DATA",
            self._battery_tone_name(battery_pct),
        )
        self.row_voltage.set_value(
            f"{telemetry.battery_voltage_v:.2f} V" if telemetry.battery_voltage_v is not None else "—"
        )
        self.row_current.set_value(
            f"{telemetry.battery_current_a:.2f} A" if telemetry.battery_current_a is not None else "—"
        )
        self.row_remaining.set_value(
            f"{battery_pct}%" if battery_pct is not None else "—", self._battery_tone(battery_pct)
        )
        self.row_runtime.set_value(self._estimate_runtime_text(telemetry))

        # Derinlik paneli
        self.tile_depth_large.set_value(depth_text, depth_tone)
        self.tile_min_depth.set_value(
            f"{telemetry.min_depth_m:.2f}" if telemetry.min_depth_m is not None else "—"
        )
        self.tile_max_depth.set_value(
            f"{telemetry.max_depth_m:.2f}" if telemetry.max_depth_m is not None else "—"
        )
        self.row_last_sample.set_value(
            telemetry.last_depth_time.strftime("%H:%M:%S") if telemetry.last_depth_time else "—"
        )
        alarm_text, alarm_tone = self._depth_alarm(telemetry.depth_m)
        self.depth_alarm_pill.set_state(alarm_text, alarm_tone)

        # Harita — konum gelmeden arac isaretcisi hic cizilmez.
        _t_before_map = time.perf_counter()
        if telemetry.latitude is not None and telemetry.longitude is not None:
            current_point = {"lat": telemetry.latitude, "lng": telemetry.longitude}
            append_track = self.last_track_point != current_point
            if append_track:
                self.last_track_point = current_point
            if self.home_point is None:
                self.home_point = dict(current_point)
                self.map_widget.set_home_point(current_point["lat"], current_point["lng"])
                self.row_home.set_value(
                    f"{current_point['lat']:.5f}, {current_point['lng']:.5f}"
                )
            self.map_widget.update_vehicle_state(telemetry, append_track)
        _t_after_map = time.perf_counter()
        self._update_mission_progress(telemetry)
        _t_end = time.perf_counter()

        self._telemetry_total_time += _t_end - _t_start
        self._telemetry_map_time += _t_after_map - _t_before_map
        self._telemetry_rest_time += (_t_before_map - _t_start) + (_t_end - _t_after_map)

    def _append_status(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.status_log.append(
            f"<span style='color:{COLORS.text_tertiary}'>{stamp}</span>&nbsp;&nbsp;{message}"
        )
        self.status_message.setText(message)
        self.status_time.setText(stamp)

    # -- yardimci hesaplar ------------------------------------------------

    @staticmethod
    def _number_text(value: float | None, spec: str) -> str:
        return spec.format(value) if value is not None else "—"

    def _fix_text(self, fix_type: int | None) -> str:
        if fix_type is None:
            return "—"
        return {
            0: "NO GPS",
            1: "NO FIX",
            2: "2D FIX",
            3: "3D FIX",
            4: "DGPS",
            5: "RTK FLOAT",
            6: "RTK FIXED",
        }.get(fix_type, str(fix_type))

    def _battery_tone(self, percent: int | None) -> str:
        if percent is None:
            return COLORS.text_tertiary
        if percent < 20:
            return COLORS.danger
        if percent < 40:
            return COLORS.warning
        return COLORS.text_primary

    def _battery_tone_name(self, percent: int | None) -> str:
        if percent is None:
            return "neutral"
        if percent < 20:
            return "danger"
        if percent < 40:
            return "warning"
        return "success"

    def _depth_alarm(self, depth_m: float | None) -> tuple[str, str]:
        if depth_m is None:
            return "NO DATA", "neutral"
        if depth_m < self.depth_low_spin.value():
            return "LOW DEPTH", "danger"
        if depth_m > self.depth_high_spin.value():
            return "HIGH DEPTH", "warning"
        return "IN RANGE", "success"

    def _depth_alarm_text(self, depth_m: float | None) -> str:
        return self._depth_alarm(depth_m)[0]

    def _estimate_runtime_text(self, telemetry: TelemetryData) -> str:
        if telemetry.battery_remaining_pct is None or telemetry.battery_current_a in {None, 0}:
            return "—"
        capacity_ah = 20.0
        remaining_ah = capacity_ah * (telemetry.battery_remaining_pct / 100.0)
        hours = remaining_ah / telemetry.battery_current_a if telemetry.battery_current_a else 0.0
        return self._format_duration(hours * 3600.0)

    def _update_mission_progress(self, telemetry: TelemetryData) -> None:
        if telemetry.latitude is None or telemetry.longitude is None:
            self.tile_waypoint.set_value(f"— / {len(self.mission_points)}")
            self.tile_remaining.set_value("—")
            self.tile_eta.set_value("—")
            self.tile_next_leg.set_value("—")
            self.progress_bar.set_progress(0, len(self.mission_points))
            return
        if not self.mission_points:
            self.tile_waypoint.set_value("0 / 0")
            self.tile_remaining.set_value("0")
            self.tile_eta.set_value("—")
            self.tile_next_leg.set_value("—")
            self.progress_bar.set_progress(0, 0)
            return
        distances = [
            self._haversine_m(telemetry.latitude, telemetry.longitude, wp.latitude, wp.longitude)
            for wp in self.mission_points
        ]

        # Prefer what the vehicle says it is flying to. Mission slot 0 is the
        # home position, so its seq N is our mission_points[N - 1]. Falling
        # back to the nearest waypoint is only a guess — on a lawnmower the
        # neighbouring lane is often closer than the leg actually being run.
        active_index = None
        seq = telemetry.current_waypoint_seq
        if seq is not None and 1 <= seq <= len(self.mission_points):
            active_index = seq - 1
        if active_index is None:
            active_index = distances.index(min(distances))

        leg_distance = (
            telemetry.waypoint_distance_m
            if telemetry.waypoint_distance_m is not None
            else distances[active_index]
        )
        remaining = self._remaining_distance(active_index, telemetry.latitude, telemetry.longitude)
        speed = telemetry.ground_speed_mps or 0.0
        eta_seconds = remaining / speed if speed > 0.1 else 0.0
        self.tile_waypoint.set_value(f"{active_index + 1} / {len(self.mission_points)}")
        self.tile_remaining.set_value(f"{remaining:.0f}")
        self.tile_eta.set_value(self._format_duration(eta_seconds))
        self.tile_next_leg.set_value(f"{leg_distance:.0f}")
        self.progress_bar.set_progress(active_index + 1, len(self.mission_points))
        if telemetry.armed and self.mission_state_pill.text() == "PLANNED":
            self.mission_state_pill.set_state("RUNNING", "success")

    def _update_survey_analytics(self) -> None:
        area = self._polygon_area_approx_m2(self.polygon_points)
        track_length = 0.0
        for first, second in zip(self.mission_points, self.mission_points[1:]):
            track_length += self._haversine_m(
                first.latitude, first.longitude, second.latitude, second.longitude
            )
        expected_samples = len(self.sample_points)
        duration = track_length / self.speed_spin.value() if self.speed_spin.value() > 0.1 else 0.0
        self.tile_area.set_value(f"{area:,.0f}".replace(",", " "))
        self.tile_track_length.set_value(f"{track_length:,.0f}".replace(",", " "))
        self.tile_samples.set_value(str(expected_samples))
        self.tile_duration.set_value(self._format_duration(duration))

    def _remaining_distance(self, active_index: int, current_lat: float, current_lng: float) -> float:
        remaining = self._haversine_m(
            current_lat,
            current_lng,
            self.mission_points[active_index].latitude,
            self.mission_points[active_index].longitude,
        )
        for first, second in zip(
            self.mission_points[active_index:], self.mission_points[active_index + 1:]
        ):
            remaining += self._haversine_m(
                first.latitude, first.longitude, second.latitude, second.longitude
            )
        return remaining

    def _polygon_area_approx_m2(self, polygon_points: list[dict]) -> float:
        if len(polygon_points) < 3:
            return 0.0
        lat0 = sum(point["lat"] for point in polygon_points) / len(polygon_points)
        xy = []
        for point in polygon_points:
            xy.append(
                (
                    point["lng"] * 111320.0 * math.cos(math.radians(lat0)),
                    point["lat"] * 110540.0,
                )
            )
        area = 0.0
        for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]):
            area += x1 * y2 - x2 * y1
        return abs(area) / 2.0

    def _haversine_m(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        return _haversine_m(lat1, lon1, lat2, lon2)

    def _format_duration(self, seconds: float) -> str:
        if seconds <= 0:
            return "—"
        total_seconds = int(seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {secs}s"
        return f"{secs}s"

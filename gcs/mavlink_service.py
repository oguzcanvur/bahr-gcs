"""GUI-side proxy for MAVLink I/O.

The actual pymavlink connection lives in a separate process (see
gcs/mavlink_worker.py) — see that module's docstring for why. This class
just forwards commands to it and drains telemetry/status events back into
Qt signals, keeping the exact same public API the rest of the app already
uses (main_window.py needs no changes).
"""
from __future__ import annotations

import multiprocessing
from queue import Empty
from typing import Iterable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, qDebug

from gcs.mavlink_worker import run_worker
from gcs.models import MissionPoint, TelemetryData


class MavlinkService(QObject):
    status_updated = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)
    depth_sample_received = pyqtSignal(object)
    message_rate_updated = pyqtSignal(float)
    mission_verified = pyqtSignal(bool, str)
    mission_completed = pyqtSignal(int)
    waypoint_radius_received = pyqtSignal(float)
    parameter_received = pyqtSignal(str, float)

    # -- setup / calibration ------------------------------------------------
    # (state, received, expected) where state is started/progress/complete/failed
    parameter_download = pyqtSignal(str, int, int)
    parameters_received = pyqtSignal(dict)
    statustext_received = pyqtSignal(int, str)
    accel_position_requested = pyqtSignal(int)
    mag_cal_progress = pyqtSignal(dict)
    mag_cal_report = pyqtSignal(dict)
    rc_channels_received = pyqtSignal(list)
    command_result = pyqtSignal(int, int)

    _EVENT_DRAIN_INTERVAL_MS = 20

    def __init__(self) -> None:
        super().__init__()
        self._telemetry = TelemetryData()
        self._command_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._event_queue: multiprocessing.Queue = multiprocessing.Queue()
        self._process = multiprocessing.Process(
            target=run_worker, args=(self._command_queue, self._event_queue), daemon=True
        )
        self._process.start()

        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(self._EVENT_DRAIN_INTERVAL_MS)
        self._drain_timer.timeout.connect(self._drain_events)
        self._drain_timer.start()

    def get_telemetry(self) -> TelemetryData:
        """Latest telemetry snapshot, refreshed from the worker process."""
        return self._telemetry

    def connect_vehicle(self, connection_string: str) -> None:
        self._command_queue.put(("connect", connection_string))

    def disconnect_vehicle(self) -> None:
        self._command_queue.put(("disconnect", None))

    def upload_mission(
        self, mission_points: Iterable[MissionPoint], survey_speed_mps: float | None = None
    ) -> None:
        self._command_queue.put(("upload_mission", (list(mission_points), survey_speed_mps)))

    def start_mission(self) -> None:
        self._command_queue.put(("start_mission", None))

    def stop_mission(self) -> None:
        self._command_queue.put(("stop_mission", None))

    def resume_mission(self) -> None:
        self._command_queue.put(("resume_mission", None))

    def set_speed(self, speed_mps: float) -> None:
        self._command_queue.put(("set_speed", float(speed_mps)))

    def return_to_launch(self) -> None:
        self._command_queue.put(("return_to_launch", None))

    def send_manual_control(
        self, throttle_pct: int, yaw_pct: int, announce: bool = True
    ) -> None:
        # The joystick streams at 10 Hz; announce=False keeps those out of the
        # status log so they don't drown every other message.
        self._command_queue.put(("manual_control", (throttle_pct, yaw_pct, announce)))

    def release_manual_control(self) -> None:
        self._command_queue.put(("release_manual_control", None))

    def go_to(self, latitude: float, longitude: float) -> None:
        self._command_queue.put(("go_to", (latitude, longitude)))

    def set_home_here(self) -> None:
        self._command_queue.put(("set_home_here", None))

    def request_parameter(self, name: str) -> None:
        self._command_queue.put(("request_parameter", name))

    def set_parameter(self, name: str, value: float) -> None:
        self._command_queue.put(("set_parameter", (name, float(value))))

    def set_mode(self, mode_name: str) -> None:
        self._command_queue.put(("set_mode", mode_name))

    def set_guided_mode(self) -> None:
        self.set_mode("GUIDED")

    def set_hold_mode(self) -> None:
        self.set_mode("HOLD")

    def arm_vehicle(self) -> None:
        self._command_queue.put(("arm", None))

    def disarm_vehicle(self) -> None:
        self._command_queue.put(("disarm", None))

    # -- setup / calibration ------------------------------------------------

    def download_parameters(self) -> None:
        self._command_queue.put(("download_parameters", None))

    def calibrate_gyro(self) -> None:
        self._command_queue.put(("calibrate_gyro", None))

    def calibrate_level(self) -> None:
        self._command_queue.put(("calibrate_level", None))

    def calibrate_accel_simple(self) -> None:
        self._command_queue.put(("calibrate_accel_simple", None))

    def calibrate_baro(self) -> None:
        self._command_queue.put(("calibrate_baro", None))

    def start_accel_calibration(self) -> None:
        self._command_queue.put(("start_accel_calibration", None))

    def confirm_accel_position(self, step: int) -> None:
        self._command_queue.put(("confirm_accel_position", int(step)))

    def start_compass_calibration(self, retry: bool = True, autosave: bool = True) -> None:
        self._command_queue.put(("start_compass_calibration", (bool(retry), bool(autosave))))

    def accept_compass_calibration(self) -> None:
        self._command_queue.put(("accept_compass_calibration", None))

    def cancel_compass_calibration(self) -> None:
        self._command_queue.put(("cancel_compass_calibration", None))

    def set_rc_calibrating(self, calibrating: bool) -> None:
        self._command_queue.put(("set_rc_calibrating", bool(calibrating)))

    def set_rc_monitor(self, enabled: bool) -> None:
        self._command_queue.put(("set_rc_monitor", bool(enabled)))

    def motor_test(self, motor: int, throttle_pct: float, seconds: float, label: str = "") -> None:
        self._command_queue.put(
            ("motor_test", (int(motor), float(throttle_pct), float(seconds), label))
        )

    def reboot_autopilot(self) -> None:
        self._command_queue.put(("reboot_autopilot", None))

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self._event_queue.get_nowait()
            except Empty:
                break
            if kind == "telemetry":
                self._telemetry = payload
            elif kind == "status":
                qDebug(payload.encode("ascii", "backslashreplace").decode("ascii"))
                self.status_updated.emit(payload)
            elif kind == "connection":
                self.connection_changed.emit(payload)
            elif kind == "depth":
                self.depth_sample_received.emit(payload)
            elif kind == "rate":
                self.message_rate_updated.emit(payload)
            elif kind == "mission_verified":
                verified, summary = payload
                self.mission_verified.emit(verified, summary)
            elif kind == "mission_complete":
                self.mission_completed.emit(payload)
            elif kind == "wp_radius":
                self.waypoint_radius_received.emit(payload)
            elif kind == "parameter":
                name, value = payload
                self.parameter_received.emit(name, value)
            elif kind == "param_download":
                state, received, expected = payload
                self.parameter_download.emit(state, received, expected)
            elif kind == "parameters":
                self.parameters_received.emit(payload)
            elif kind == "statustext":
                severity, text = payload
                self.statustext_received.emit(severity, text)
            elif kind == "accel_cal_position":
                self.accel_position_requested.emit(payload)
            elif kind == "mag_cal_progress":
                self.mag_cal_progress.emit(payload)
            elif kind == "mag_cal_report":
                self.mag_cal_report.emit(payload)
            elif kind == "rc_channels":
                self.rc_channels_received.emit(payload)
            elif kind == "command_result":
                command, result = payload
                self.command_result.emit(command, result)

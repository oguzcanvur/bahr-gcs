"""MAVLink I/O worker — runs in its own OS process, not a thread.

A busy `threading.Thread` doing ~1000 msg/s of pymavlink work was measured to
starve the GUI thread of CPython's GIL almost completely on Windows (a
documented CPython/Windows scheduling fairness issue: a continuously-busy
thread can win the race to reacquire the GIL against a thread that just woke
from sleep, far more often than on Linux). Tuning switch intervals and
removing Qt signals from the hot path did not help, because the starvation
happens below both of those layers. Running MAVLink I/O in a separate
process sidesteps it entirely — a separate process has its own GIL, so it
can never starve the GUI process no matter how busy it is.

No PyQt import here on purpose: multiprocessing (spawn, the default on
Windows) re-imports whatever this process needs, and keeping this module
Qt-free keeps that re-import cheap and avoids ever touching Qt/WebEngine
from a non-GUI process.
"""
from __future__ import annotations

import math
import threading
import time
from datetime import datetime
from queue import Empty, Queue
from typing import Iterable

from pymavlink import mavutil

from gcs.models import DepthSample, MissionPoint, TelemetryData

# Telemetry is updated on every message internally, but only pushed across
# the process boundary (pickled + IPC) at this capped rate.
_TELEMETRY_PUSH_INTERVAL_S = 0.05  # 20 Hz


class _Worker:
    # Mission-protocol traffic is routed through _mission_queue rather than
    # read off the socket directly — see the _mission_queue comment below.
    # Manual driving, matching Mission Planner's RC override joystick path.
    _RC_IGNORE = 0xFFFF          # UINT16_MAX: "ignore this channel" per spec
    _RC_NEUTRAL_US = 1500
    _RC_SPAN_US = 400            # full deflection -> 1100..1900 us
    _RC_STEERING_CHANNEL = 1     # RCMAP_ROLL default
    _RC_THROTTLE_CHANNEL = 3     # RCMAP_THROTTLE default

    _MISSION_MESSAGE_TYPES = (
        "MISSION_REQUEST_INT",
        "MISSION_REQUEST",
        "MISSION_ACK",
        "MISSION_COUNT",
        "MISSION_ITEM_INT",
        "MISSION_ITEM",
    )

    def __init__(self, command_queue, event_queue) -> None:
        self._command_queue = command_queue
        self._event_queue = event_queue
        self._master = None
        self._running = False
        self._listener_thread: threading.Thread | None = None
        self._telemetry = TelemetryData()
        self._last_push_time = 0.0
        self._msg_type_counts: dict[str, int] = {}
        self._rate_window_start = 0.0
        # Mission protocol messages are consumed here by upload_mission()
        # instead of via recv_match() directly, since _recv_loop() is
        # continuously reading the same socket on its own thread and would
        # otherwise race it for MISSION_REQUEST(_INT)/MISSION_ACK packets.
        self._mission_queue: Queue = Queue()
        # Last point handed to go_to(), so the COMMAND_ACK and the vehicle's
        # own POSITION_TARGET_GLOBAL_INT can be compared against what we asked
        # for instead of being reported in isolation.
        self._goto_target: tuple[float, float] | None = None
        # Mission completion is announced once per run, not on every repeat of
        # the vehicle's final MISSION_ITEM_REACHED.
        self._mission_item_count = 0
        self._mission_complete_sent = False

        # -- setup / calibration state --------------------------------------
        # Full parameter download. PARAM_VALUE arrives on the receive thread
        # while the chaser thread below re-requests whatever never showed up,
        # so both touch this state and it needs a lock.
        self._param_lock = threading.Lock()
        self._param_values: dict[str, float] = {}
        self._param_types: dict[str, int] = {}
        self._param_seen_index: set[int] = set()
        self._param_expected = 0
        self._param_download_active = False
        self._param_last_rx = 0.0
        self._param_chaser: threading.Thread | None = None
        # RC_CHANNELS is only pushed across the process boundary while the
        # radio calibration screen is actually watching it.
        self._rc_monitor = False
        self._rc_last_push = 0.0
        # Which 6-position step the vehicle last asked for, so a repeated
        # request is not reported to the UI as a new one.
        self._accel_step: int | None = None

    def _emit_status(self, message: str) -> None:
        self._event_queue.put(("status", message))

    def _emit_connection(self, connected: bool) -> None:
        self._event_queue.put(("connection", connected))

    def _emit_verification(self, verified: bool, summary: str) -> None:
        self._emit_status(summary)
        self._event_queue.put(("mission_verified", (verified, summary)))

    # -- komutlar -----------------------------------------------------------

    def connect_vehicle(self, connection_string: str) -> None:
        # A stale socket from a previous connection can still be bound to this
        # port (see disconnect_vehicle); close it explicitly rather than
        # trusting garbage collection to get to it before the bind below.
        self._close_master()
        self._emit_status(f"Connecting to {connection_string}...")
        try:
            master = self._open_connection(connection_string)
            # recv_match — what wait_heartbeat wraps — returns None on
            # timeout rather than raising, so a silent timeout must be
            # checked explicitly or a connection that never heard from the
            # vehicle gets reported as successful.
            heartbeat = master.wait_heartbeat(timeout=5)
        except Exception as exc:
            self._emit_status(f"Connection failed: {exc}")
            self._emit_connection(False)
            return
        if heartbeat is None:
            master.close()
            self._emit_status("Connection failed: no heartbeat within 5 s.")
            self._emit_connection(False)
            return

        heartbeat = self._lock_onto_autopilot(master, heartbeat)

        self._master = master
        self._running = True
        self._emit_connection(True)
        self._emit_status(
            f"Vehicle heartbeat received "
            f"(system {master.target_system}, component {master.target_component})."
        )
        self._request_telemetry_streams()
        # The planner needs the vehicle's acceptance radius to space turn
        # waypoints; guessing it produces arcs the vehicle cannot fly.
        try:
            master.mav.param_request_read_send(
                master.target_system, master.target_component, b"WP_RADIUS", -1
            )
        except Exception as exc:
            self._emit_status(f"WP_RADIUS request failed: {exc}")

        self._listener_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._listener_thread.start()

    @staticmethod
    def _is_autopilot_heartbeat(message) -> bool:
        """True only for the flight controller's own heartbeat.

        A Cube Orange puts more than one MAVLink component on the same link:
        besides the autopilot on component 1, it also emits an
        MAV_TYPE_ADSB heartbeat from component 0 with autopilot =
        MAV_AUTOPILOT_INVALID. That component carries no telemetry, but its
        heartbeat has base_mode/custom_mode fields like any other — decoding
        them as the vehicle's produces a nonsense flight mode (measured on
        real hardware: "Mode(0x00000004)" showed in 18 of 22 telemetry
        frames, burying the true "HOLD").
        """
        return int(getattr(message, "autopilot", mavutil.mavlink.MAV_AUTOPILOT_INVALID)) != \
            mavutil.mavlink.MAV_AUTOPILOT_INVALID

    def _lock_onto_autopilot(self, master, heartbeat):
        """Point target_system/target_component at the real flight controller.

        wait_heartbeat() takes whichever heartbeat arrives first, which on a
        Cube is often the ADSB component. Commands would then be addressed to
        component 0 instead of the autopilot's component 1.
        """
        if self._is_autopilot_heartbeat(heartbeat):
            return heartbeat

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            try:
                message = master.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
            except OSError:
                break
            if message is None:
                continue
            if self._is_autopilot_heartbeat(message):
                master.target_system = message.get_srcSystem()
                master.target_component = message.get_srcComponent()
                return message

        self._emit_status(
            "Warning: no autopilot heartbeat seen — the only components "
            "answering do not identify as an autopilot. Commands may be ignored."
        )
        return heartbeat

    def disconnect_vehicle(self) -> None:
        self._running = False
        self._close_master()
        self._emit_status("Disconnected.")
        self._emit_connection(False)

    def _close_master(self) -> None:
        """Release the socket immediately rather than waiting on GC.

        mavfile holds a reference cycle (master.mav references master back),
        so dropping `self._master` alone leaves the underlying socket bound
        until Python's cyclic collector gets to it — which is not guaranteed
        to happen before the next connect attempt tries to bind the same
        port, and previously made a quick reconnect fail non-deterministically.
        """
        master, self._master = self._master, None
        if master is not None:
            try:
                master.close()
            except Exception:
                pass

    def _drain_mission_queue(self) -> None:
        """Drop mission traffic left over from an earlier (failed) exchange."""
        while not self._mission_queue.empty():
            try:
                self._mission_queue.get_nowait()
            except Empty:
                break

    def _await_mission_message(self, types, timeout: float = 5.0, seq: int | None = None):
        """Next queued mission message of `types`, or None on timeout.

        Messages of other types (and, when `seq` is given, stale items for a
        different sequence number) are discarded rather than ending the wait.
        """
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                message = self._mission_queue.get(timeout=remaining)
            except Empty:
                return None
            if message.get_type() not in types:
                continue
            if seq is not None and int(getattr(message, "seq", seq)) != seq:
                continue
            return message

    def upload_mission(
        self, mission_points: Iterable[MissionPoint], survey_speed_mps: float | None = None
    ) -> None:
        waypoints = list(mission_points)
        if not waypoints:
            self._emit_status("No mission points available.")
            return
        if self._master is None:
            self._emit_status("No MAVLink vehicle connected. Mission kept in UI only.")
            return

        self._drain_mission_queue()
        self._mission_item_count = len(waypoints) + 1  # slot 0 is home
        self._mission_complete_sent = False

        try:
            if survey_speed_mps is not None and survey_speed_mps > 0:
                self._master.mav.command_long_send(
                    self._master.target_system,
                    self._master.target_component,
                    mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED,
                    0,
                    1,
                    float(survey_speed_mps),
                    -1,
                    0,
                    0,
                    0,
                    0,
                )
            self._master.waypoint_clear_all_send()
            time.sleep(0.2)
            # ArduPilot reserves mission slot 0 for the home position, so the
            # survey points start at seq 1 — sending one at seq 0 would have it
            # silently swallowed as home.
            self._master.waypoint_count_send(len(waypoints) + 1)

            for _ in range(len(waypoints) + 1):
                request = self._await_mission_message(
                    ("MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK")
                )
                if request is None:
                    raise TimeoutError("Mission upload timed out waiting for waypoint request.")
                if request.get_type() == "MISSION_ACK":
                    # Vehicle already had fewer items than expected and ack'd early.
                    continue

                sequence = int(request.seq)
                if sequence == 0:
                    # Home placeholder. If no position has arrived yet, send
                    # zeros — ArduPilot overwrites slot 0 with its own home
                    # anyway, and verification skips it.
                    latitude = self._telemetry.latitude or 0.0
                    longitude = self._telemetry.longitude or 0.0
                    altitude = 0.0
                else:
                    wp = waypoints[sequence - 1]
                    latitude, longitude, altitude = wp.latitude, wp.longitude, wp.altitude_m

                self._master.mav.mission_item_int_send(
                    self._master.target_system,
                    self._master.target_component,
                    sequence,
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                    mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    0,
                    1,
                    0.0,
                    2.0,
                    0.0,
                    math.nan,
                    int(latitude * 1e7),
                    int(longitude * 1e7),
                    float(altitude),
                )

            ack = self._await_mission_message(("MISSION_ACK",))
            if ack is None:
                raise TimeoutError("Mission upload timed out waiting for MISSION_ACK.")
            ack_type = int(getattr(ack, "type", 0))
            if ack_type != mavutil.mavlink.MAV_MISSION_ACCEPTED:
                raise RuntimeError(f"Vehicle rejected the mission ({self._mission_ack_name(ack_type)}).")

            if survey_speed_mps is not None and survey_speed_mps > 0:
                self._emit_status(
                    f"Mission upload completed. Survey speed set to {survey_speed_mps:.1f} m/s."
                )
            else:
                self._emit_status("Mission upload completed.")
        except Exception as exc:
            self._emit_status(f"Mission upload failed: {exc}")
            return

        self._verify_mission(waypoints)

    def _verify_mission(self, waypoints: list[MissionPoint]) -> None:
        """Read the mission back off the vehicle and compare it to what we sent.

        Upload can fail silently — a dropped MISSION_REQUEST or an off-by-one
        in the sequence numbering still ends in a MISSION_ACCEPTED ack — so the
        only way to know the vehicle really holds this mission is to read it.
        """
        try:
            onboard = self._download_mission()
        except Exception as exc:
            self._emit_verification(False, f"Mission verification failed: {exc}")
            return

        # Slot 0 is the vehicle's own home position, not one of our waypoints.
        expected = len(waypoints) + 1
        if len(onboard) != expected:
            self._emit_verification(
                False,
                f"Mission MISMATCH: vehicle holds {len(onboard)} items, expected {expected}.",
            )
            return

        mismatched = [
            index + 1
            for index, point in enumerate(waypoints)
            if abs(onboard[index + 1][0] - int(point.latitude * 1e7)) > 1
            or abs(onboard[index + 1][1] - int(point.longitude * 1e7)) > 1
        ]
        if mismatched:
            preview = ", ".join(str(seq) for seq in mismatched[:5])
            suffix = "..." if len(mismatched) > 5 else ""
            self._emit_verification(
                False,
                f"Mission MISMATCH: {len(mismatched)} of {len(waypoints)} waypoints differ "
                f"on the vehicle (seq {preview}{suffix}).",
            )
            return

        self._emit_verification(
            True, f"Mission verified: {len(waypoints)} waypoints match the vehicle."
        )

    def _download_mission(self) -> list[tuple[int, int]]:
        """Mission currently stored on the vehicle as (lat, lon) in 1e7 degrees."""
        if self._master is None:
            raise RuntimeError("no vehicle connected")

        self._drain_mission_queue()
        self._master.mav.mission_request_list_send(
            self._master.target_system, self._master.target_component
        )
        count_message = self._await_mission_message(("MISSION_COUNT",))
        if count_message is None:
            raise TimeoutError("no MISSION_COUNT from vehicle")

        items: list[tuple[int, int]] = []
        for sequence in range(int(count_message.count)):
            self._master.mav.mission_request_int_send(
                self._master.target_system, self._master.target_component, sequence
            )
            item = self._await_mission_message(
                ("MISSION_ITEM_INT", "MISSION_ITEM"), seq=sequence
            )
            if item is None:
                raise TimeoutError(f"no mission item {sequence} from vehicle")
            if item.get_type() == "MISSION_ITEM":
                # The float variant carries plain degrees rather than 1e7 units.
                items.append((int(round(item.x * 1e7)), int(round(item.y * 1e7))))
            else:
                items.append((int(item.x), int(item.y)))

        self._master.mav.mission_ack_send(
            self._master.target_system,
            self._master.target_component,
            mavutil.mavlink.MAV_MISSION_ACCEPTED,
        )
        return items

    @staticmethod
    def _mission_ack_name(ack_type: int) -> str:
        try:
            return mavutil.mavlink.enums["MAV_MISSION_RESULT"][ack_type].name
        except Exception:
            return f"result {ack_type}"

    def start_mission(self) -> None:
        # Re-running the same mission should prompt again when it finishes.
        self._mission_complete_sent = False
        self._send_command(
            mavutil.mavlink.MAV_CMD_MISSION_START, status_text="Mission start requested."
        )

    def stop_mission(self) -> None:
        self._send_command(
            mavutil.mavlink.MAV_CMD_DO_PAUSE_CONTINUE,
            param1=0.0,
            status_text="Hold position requested.",
        )

    def resume_mission(self) -> None:
        # DO_PAUSE_CONTINUE is a pair: param1=0 pauses, param1=1 carries on
        # with the rest of the mission from where it stopped.
        self._send_command(
            mavutil.mavlink.MAV_CMD_DO_PAUSE_CONTINUE,
            param1=1.0,
            status_text="Resume mission requested.",
        )

    def set_speed(self, speed_mps: float) -> None:
        """Change the target speed without re-uploading the mission."""
        self._send_command(
            mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED,
            param1=1.0,               # 1 = ground speed
            param2=float(speed_mps),
            param3=-1.0,              # throttle: -1 leaves it alone
            status_text=f"Speed change requested: {speed_mps:.1f} m/s.",
        )

    def return_to_launch(self) -> None:
        self._send_command(
            mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH, status_text="Return-home requested."
        )

    def send_manual_control(
        self, throttle_pct: int, yaw_pct: int, announce: bool = True
    ) -> None:
        """Drive manually with RC_CHANNELS_OVERRIDE, exactly as Mission Planner does.

        Mission Planner's joystick path is SendRCOverride() — raw PWM per
        channel — not MANUAL_CONTROL. That distinction matters on Rover:
        radio.cpp binds channel_steer/channel_throttle with set_angle(), so
        those channels take their neutral from RC*_TRIM. MANUAL_CONTROL goes
        through GCS_MAVLINK::manual_override(), which instead centres on
        (radio_min + radio_max) / 2. When trim is not exactly halfway the two
        disagree, and a stick pushed straight forward still commands steering
        — which on a skid-steer rover shows up as spinning rather than
        driving straight.

        Channel map (ArduRover defaults): RCMAP_ROLL = RC1 = steering,
        RCMAP_THROTTLE = RC3 = throttle. Every other channel is sent as
        UINT16_MAX, which per the MAVLink spec means "ignore this field", so
        mode switches and the rest stay under the vehicle's own RC input.
        """
        if self._master is None:
            self._emit_status("No MAVLink vehicle connected. Manual control ignored.")
            return

        steering_us = self._percent_to_pwm(yaw_pct)
        throttle_us = self._percent_to_pwm(throttle_pct)
        self._send_rc_override(steering_us, throttle_us)
        if announce:
            self._emit_status(
                f"Manual control: throttle {throttle_pct}% ({throttle_us} us), "
                f"steering {yaw_pct}% ({steering_us} us)."
            )

    def release_manual_control(self) -> None:
        """Hand the channels back to the vehicle's own RC input.

        A zero in RC_CHANNELS_OVERRIDE releases that channel, so letting go of
        the stick stops us holding the vehicle at neutral indefinitely.
        """
        if self._master is None:
            return
        self._send_rc_override(0, 0)

    def _send_rc_override(self, steering_us: int, throttle_us: int) -> None:
        # Eight channels, same as Mission Planner's SendRCOverride(rc1..rc8).
        channels = [self._RC_IGNORE] * 8
        channels[self._RC_STEERING_CHANNEL - 1] = steering_us
        channels[self._RC_THROTTLE_CHANNEL - 1] = throttle_us
        try:
            self._master.mav.rc_channels_override_send(
                self._master.target_system,
                self._master.target_component,
                *channels,
            )
        except Exception as exc:
            self._emit_status(f"Manual control failed: {exc}")

    @classmethod
    def _percent_to_pwm(cls, percent: int) -> int:
        percent = max(-100, min(100, int(percent)))
        return int(round(cls._RC_NEUTRAL_US + (percent / 100.0) * cls._RC_SPAN_US))

    def arm_vehicle(self) -> None:
        self._send_command(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, param1=1.0, status_text="Arm requested."
        )

    def disarm_vehicle(self) -> None:
        self._send_command(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            param1=0.0,
            status_text="Disarm requested.",
        )

    def _send_command(
        self,
        command: int,
        param1: float = 0.0,
        param2: float = 0.0,
        param3: float = 0.0,
        param4: float = 0.0,
        param5: float = 0.0,
        param6: float = 0.0,
        param7: float = 0.0,
        status_text: str = "Command sent.",
    ) -> None:
        if self._master is None:
            self._emit_status(f"No MAVLink vehicle connected. {status_text}")
            return
        try:
            self._master.mav.command_long_send(
                self._master.target_system,
                self._master.target_component,
                command,
                0,
                param1,
                param2,
                param3,
                param4,
                param5,
                param6,
                param7,
            )
            self._emit_status(status_text)
        except Exception as exc:
            self._emit_status(f"Command failed: {exc}")

    def go_to(self, latitude: float, longitude: float) -> None:
        """Send the vehicle to a single point, the way QGC and MP do it.

        QGroundControl (APMFirmwarePlugin::guidedModeGotoLocation) issues
        MAV_CMD_DO_REPOSITION as a COMMAND_INT in MAV_FRAME_GLOBAL with the
        vehicle's *current AMSL altitude* in z, and relies on
        MAV_DO_REPOSITION_FLAGS_CHANGE_MODE to enter Guided. Mission Planner
        (setGuidedModeWP) instead switches to GUIDED explicitly and then sends
        SET_POSITION_TARGET_GLOBAL_INT, and refuses outright when the altitude
        is zero. We follow QGC's primary path and keep MP's message as the
        fallback if the vehicle rejects the command.
        """
        if self._master is None:
            self._emit_status("No MAVLink vehicle connected. Go-to ignored.")
            return

        # QGC refuses to send when the vehicle position/altitude is unknown;
        # without it we have no altitude to put in the command.
        altitude_amsl = self._telemetry.altitude_amsl_m
        if altitude_amsl is None:
            self._emit_status("Go-to ignored: no vehicle altitude yet (waiting for GPS).")
            return

        self._goto_target = (latitude, longitude)
        self._emit_status(
            f"Go-to SENT     lat={latitude:.7f} lon={longitude:.7f} "
            f"alt={altitude_amsl:.2f} m AMSL (frame=GLOBAL, DO_REPOSITION)"
        )
        try:
            self._master.mav.command_int_send(
                self._master.target_system,
                self._master.target_component,
                mavutil.mavlink.MAV_FRAME_GLOBAL,
                mavutil.mavlink.MAV_CMD_DO_REPOSITION,
                0,  # current
                0,  # autocontinue
                -1.0,  # param1: ground speed, -1 = keep the vehicle's default
                float(mavutil.mavlink.MAV_DO_REPOSITION_FLAGS_CHANGE_MODE),
                0.0,  # param3: loiter radius, unused on rovers/boats
                math.nan,  # param4: yaw, NaN = keep current yaw behaviour
                int(latitude * 1e7),
                int(longitude * 1e7),
                float(altitude_amsl),
            )
        except Exception as exc:
            self._emit_status(f"Go-to failed: {exc}")

    def _go_to_fallback(self, latitude: float, longitude: float) -> None:
        """Mission Planner's route: explicit GUIDED, then a position target.

        Used when the vehicle answers DO_REPOSITION with anything other than
        ACCEPTED — older ArduPilot builds do not implement it for every frame.
        """
        if self._master is None:
            return
        altitude_rel = self._telemetry.altitude_rel_m or 0.0
        self._set_mode("GUIDED")
        # type_mask: ignore everything except position (bits 0-2 cleared).
        # Matches Mission Planner's 0xFFFF - FORCE - POS_IGNORE.
        type_mask = 0xFFFF - (1 << 9) - 0b111
        try:
            self._master.mav.set_position_target_global_int_send(
                0,  # time_boot_ms
                self._master.target_system,
                self._master.target_component,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                type_mask,
                int(latitude * 1e7),
                int(longitude * 1e7),
                float(altitude_rel),
                0.0, 0.0, 0.0,   # velocity, ignored
                0.0, 0.0, 0.0,   # acceleration, ignored
                0.0, 0.0,        # yaw, yaw_rate, ignored
            )
            self._emit_status(
                f"Go-to FALLBACK SET_POSITION_TARGET_GLOBAL_INT "
                f"lat={latitude:.7f} lon={longitude:.7f} alt={altitude_rel:.2f} m rel"
            )
        except Exception as exc:
            self._emit_status(f"Go-to fallback failed: {exc}")

    def request_parameter(self, name: str) -> None:
        if self._master is None:
            self._emit_status(f"No vehicle connected. {name} read ignored.")
            return
        try:
            self._master.mav.param_request_read_send(
                self._master.target_system,
                self._master.target_component,
                name.encode("ascii"),
                -1,  # -1 = look up by name rather than index
            )
        except Exception as exc:
            self._emit_status(f"{name} read failed: {exc}")

    def set_parameter(self, name: str, value: float) -> None:
        """Write a parameter and let the vehicle's PARAM_VALUE confirm it.

        ArduPilot ignores the param_type field and uses the parameter's own
        stored type (GCS_Param.cpp: handle_param_set looks the type up via
        AP_Param::find), so REAL32 is safe for every parameter. It replies
        with a PARAM_VALUE carrying the value it actually stored — which may
        differ from what we asked for if the parameter is an integer or is
        clamped, so the UI reports the vehicle's value, not ours.
        """
        if self._master is None:
            self._emit_status(f"No vehicle connected. {name} write ignored.")
            return
        try:
            self._master.mav.param_set_send(
                self._master.target_system,
                self._master.target_component,
                name.encode("ascii"),
                float(value),
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
            )
            self._emit_status(f"{name} <- {value:g} requested.")
        except Exception as exc:
            self._emit_status(f"{name} write failed: {exc}")

    # -- setup / calibration -----------------------------------------------
    #
    # Command semantics below were read out of ArduPilot master rather than
    # guessed:
    #   GCS_Common.cpp::_handle_command_preflight_calibration  — which param
    #     selects which calibration.
    #   GCS_Common.cpp::convert_COMMAND_LONG_to_COMMAND_INT    — PREFLIGHT_
    #     CALIBRATION does not store a location, so COMMAND_LONG param5 lands
    #     in COMMAND_INT.x as a plain cast (no 1e7 scaling). Sending these as
    #     COMMAND_LONG is therefore safe.
    #   AP_AccelCal.cpp                                        — the vehicle
    #     broadcasts MAV_CMD_ACCELCAL_VEHICLE_POS to ask for a pose, and the
    #     GCS echoes the same command back to advance. (The older path, an
    #     ambiguous COMMAND_ACK, is explicitly deprecated in that file.)
    #   AP_Compass_Calibration.cpp::handle_mag_cal_command     — mag mask,
    #     retry, autosave, delay, autoreboot.
    #
    # Every calibration is refused by the vehicle while armed; that refusal
    # comes back as a STATUSTEXT, which is surfaced to the operator.

    _CAL_ACCEL_FULL = 1
    _CAL_ACCEL_TRIM = 2
    _CAL_ACCEL_SIMPLE = 4

    def download_parameters(self) -> None:
        """Pull the whole parameter table, chasing whatever gets dropped.

        A PARAM_REQUEST_LIST reply is a long unacknowledged burst — on a
        lossy telemetry link some of it simply never arrives. Every GCS
        therefore tracks which indices showed up and re-requests the gaps
        individually; without that the table silently comes back short.
        """
        if self._master is None:
            self._emit_status("No vehicle connected. Parameter download ignored.")
            self._event_queue.put(("param_download", ("failed", 0, 0)))
            return

        with self._param_lock:
            if self._param_download_active:
                self._emit_status("Parameter download already running.")
                return
            self._param_values.clear()
            self._param_types.clear()
            self._param_seen_index.clear()
            self._param_expected = 0
            self._param_download_active = True
            self._param_last_rx = time.monotonic()

        try:
            self._master.mav.param_request_list_send(
                self._master.target_system, self._master.target_component
            )
        except Exception as exc:
            with self._param_lock:
                self._param_download_active = False
            self._emit_status(f"Parameter download failed to start: {exc}")
            self._event_queue.put(("param_download", ("failed", 0, 0)))
            return

        self._emit_status("Parameter download started.")
        self._event_queue.put(("param_download", ("started", 0, 0)))
        self._param_chaser = threading.Thread(target=self._chase_missing_parameters, daemon=True)
        self._param_chaser.start()

    def _chase_missing_parameters(self) -> None:
        """Re-request dropped indices until the table is whole or we give up."""
        idle_timeout = 2.0
        deadline = time.monotonic() + 120.0
        rounds = 0

        while time.monotonic() < deadline:
            time.sleep(0.4)
            with self._param_lock:
                if not self._param_download_active:
                    return
                expected = self._param_expected
                seen = set(self._param_seen_index)
                idle_for = time.monotonic() - self._param_last_rx
                received = len(self._param_values)

            self._event_queue.put(("param_download", ("progress", received, expected)))

            if expected and len(seen) >= expected:
                break
            if idle_for < idle_timeout:
                continue  # still streaming, let it run

            if not expected:
                self._emit_status("Parameter download: no reply from vehicle.")
                break

            missing = [i for i in range(expected) if i not in seen]
            if not missing:
                break
            rounds += 1
            if rounds > 12:
                self._emit_status(
                    f"Parameter download gave up with {len(missing)} parameter(s) missing."
                )
                break
            self._emit_status(
                f"Parameter download: re-requesting {len(missing)} missing "
                f"parameter(s) (round {rounds})."
            )
            for index in missing[:60]:  # bounded burst, the rest next round
                if self._master is None:
                    break
                try:
                    self._master.mav.param_request_read_send(
                        self._master.target_system,
                        self._master.target_component,
                        b"",
                        index,
                    )
                except Exception:
                    break
                time.sleep(0.01)

        with self._param_lock:
            self._param_download_active = False
            values = dict(self._param_values)
            expected = self._param_expected
        self._emit_status(f"Parameter download complete: {len(values)}/{expected or len(values)}.")
        self._event_queue.put(("param_download", ("complete", len(values), expected)))
        self._event_queue.put(("parameters", values))

    def calibrate_gyro(self) -> None:
        self._send_command(
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            param1=1.0,
            status_text="Gyro calibration requested — keep the vehicle still.",
        )

    def calibrate_level(self) -> None:
        """Board level / trim calibration (PREFLIGHT_CALIBRATION param5 = 2)."""
        self._send_command(
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            param5=float(self._CAL_ACCEL_TRIM),
            status_text="Level calibration requested — hold the vehicle level and still.",
        )

    def calibrate_accel_simple(self) -> None:
        self._send_command(
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            param5=float(self._CAL_ACCEL_SIMPLE),
            status_text="Simple accelerometer calibration requested.",
        )

    def calibrate_baro(self) -> None:
        self._send_command(
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            param3=1.0,
            status_text="Barometer/ground pressure calibration requested.",
        )

    def start_accel_calibration(self) -> None:
        self._accel_step = None
        self._send_command(
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            param5=float(self._CAL_ACCEL_FULL),
            status_text="Full accelerometer calibration started.",
        )

    def confirm_accel_position(self, step: int) -> None:
        """Tell the vehicle the boat is now in the pose it asked for."""
        self._send_command(
            mavutil.mavlink.MAV_CMD_ACCELCAL_VEHICLE_POS,
            param1=float(step),
            status_text=f"Accel calibration: position {step} confirmed.",
        )

    def start_compass_calibration(self, retry: bool = True, autosave: bool = True) -> None:
        self._send_command(
            mavutil.mavlink.MAV_CMD_DO_START_MAG_CAL,
            param1=0.0,  # 0 = every compass
            param2=1.0 if retry else 0.0,
            param3=1.0 if autosave else 0.0,
            param4=0.0,  # start delay, seconds
            param5=0.0,  # autoreboot when done
            status_text="Compass calibration started — rotate the vehicle through every axis.",
        )

    def accept_compass_calibration(self) -> None:
        self._send_command(
            mavutil.mavlink.MAV_CMD_DO_ACCEPT_MAG_CAL,
            param1=0.0,
            status_text="Compass calibration accepted.",
        )

    def cancel_compass_calibration(self) -> None:
        self._send_command(
            mavutil.mavlink.MAV_CMD_DO_CANCEL_MAG_CAL,
            param1=0.0,
            status_text="Compass calibration cancelled.",
        )

    def set_rc_calibrating(self, calibrating: bool) -> None:
        """Suspend the vehicle's normal RC handling while sticks are swept."""
        self._send_command(
            mavutil.mavlink.MAV_CMD_PREFLIGHT_CALIBRATION,
            param4=1.0 if calibrating else 0.0,
            status_text=(
                "Radio calibration mode ON." if calibrating else "Radio calibration mode OFF."
            ),
        )

    def set_rc_monitor(self, enabled: bool) -> None:
        """Start/stop forwarding RC_CHANNELS across the process boundary."""
        self._rc_monitor = bool(enabled)

    def motor_test(
        self, motor: int, throttle_pct: float, seconds: float, throttle_type: int = 0,
        label: str = "",
    ) -> None:
        """Spin one motor. throttle_type 0 = percent (MOTOR_TEST_THROTTLE_PERCENT).

        `motor` is ArduPilot's motor_test_order (AR_Motors/AP_MotorsUGV.cpp),
        not a physical port number, so the log line is close to meaningless
        on its own — "Motor 3" tells no one which output that is. `label`
        lets the caller say what it actually maps to (e.g. a port name).
        """
        suffix = f" [{label}]" if label else ""
        self._send_command(
            mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST,
            param1=float(motor),
            param2=float(throttle_type),
            param3=float(throttle_pct),
            param4=float(seconds),
            status_text=f"Motor {motor} test: {throttle_pct:g}% for {seconds:g} s.{suffix}",
        )

    def reboot_autopilot(self) -> None:
        self._send_command(
            mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
            param1=1.0,  # 1 = reboot autopilot
            status_text="Autopilot reboot requested.",
        )

    def set_home_here(self) -> None:
        # param1 = 1 tells the vehicle to use its own current position, which
        # avoids having to agree on an altitude frame with the GCS.
        self._send_command(
            mavutil.mavlink.MAV_CMD_DO_SET_HOME,
            param1=1.0,
            status_text="Set home to current vehicle position requested.",
        )

    def _set_mode(self, mode_name: str) -> None:
        if self._master is None:
            self._emit_status(f"No MAVLink vehicle connected. {mode_name} mode ignored.")
            return
        try:
            mode_mapping = self._master.mode_mapping()
            if not mode_mapping or mode_name not in mode_mapping:
                self._emit_status(f"{mode_name} mode is not available on this vehicle.")
                return
            self._master.set_mode(mode_mapping[mode_name])
            self._emit_status(f"{mode_name} mode requested.")
        except Exception as exc:
            self._emit_status(f"Mode change failed: {exc}")

    def _open_connection(self, connection_string: str):
        if connection_string.startswith(("udp:", "tcp:")):
            return mavutil.mavlink_connection(connection_string)

        port_name = connection_string
        baud_rate = 115200
        if "," in connection_string:
            maybe_port, maybe_baud = connection_string.split(",", 1)
            port_name = maybe_port.strip()
            try:
                baud_rate = int(maybe_baud.strip())
            except ValueError:
                raise ValueError(f"Invalid baud rate: {maybe_baud!r}") from None

        return mavutil.mavlink_connection(port_name, baud=baud_rate)

    def _request_telemetry_streams(self) -> None:
        if self._master is None:
            return
        try:
            self._master.mav.request_data_stream_send(
                self._master.target_system,
                self._master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                10,
                1,
            )
            self._emit_status("Telemetry stream request sent.")
        except Exception as exc:
            self._emit_status(f"Telemetry stream request failed: {exc}")

    def _recv_loop(self) -> None:
        while self._running and self._master is not None:
            try:
                message = self._master.recv_match(blocking=True, timeout=1)
            except OSError:
                # _close_master() closed the socket out from under a call
                # that was already blocked in it — a normal race on
                # disconnect/reconnect, not a real failure. self._master is
                # already None or about to be by the time this is seen.
                return
            if message is None:
                continue
            message_type = message.get_type()
            self._telemetry.link_quality_pct = 100
            self._msg_type_counts[message_type] = self._msg_type_counts.get(message_type, 0) + 1

            if message_type in self._MISSION_MESSAGE_TYPES:
                self._mission_queue.put(message)
            elif message_type == "COMMAND_ACK":
                self._handle_command_ack(message)
            elif message_type == "POSITION_TARGET_GLOBAL_INT":
                self._handle_position_target(message)

            if message_type == "GLOBAL_POSITION_INT":
                # ArduPilot streams this before it has a fix, filled with
                # zeros. Taking that at face value plots the boat at 0°N 0°E,
                # in the Gulf of Guinea, which reads as a working position
                # rather than as "no GPS yet".
                if message.lat == 0 and message.lon == 0:
                    self._telemetry.latitude = None
                    self._telemetry.longitude = None
                else:
                    self._telemetry.latitude = message.lat / 1e7
                    self._telemetry.longitude = message.lon / 1e7
                self._telemetry.altitude_amsl_m = message.alt / 1000.0
                self._telemetry.altitude_rel_m = message.relative_alt / 1000.0
                self._telemetry.heading_deg = (
                    (message.hdg / 100.0) if message.hdg != 65535 else self._telemetry.heading_deg
                )
            elif message_type == "ATTITUDE":
                self._telemetry.roll_deg = math.degrees(float(message.roll))
                self._telemetry.pitch_deg = math.degrees(float(message.pitch))
            elif message_type == "VFR_HUD":
                self._telemetry.ground_speed_mps = float(message.groundspeed)
                self._telemetry.heading_deg = float(message.heading)
            elif message_type == "GPS_RAW_INT":
                self._telemetry.fix_type = int(message.fix_type)
            elif message_type == "MISSION_CURRENT":
                self._telemetry.current_waypoint_seq = int(message.seq)
            elif message_type == "MISSION_ITEM_REACHED":
                self._handle_mission_item_reached(message)
            elif message_type == "PARAM_VALUE":
                name = str(message.param_id).strip("\x00")
                value = float(message.param_value)
                # Every PARAM_VALUE is surfaced; ArduPilot also emits one as
                # the acknowledgement of a PARAM_SET, which is how the tuning
                # panel confirms a write actually took.
                self._event_queue.put(("parameter", (name, value)))
                if name == "WP_RADIUS":
                    self._event_queue.put(("wp_radius", value))
                self._record_parameter(message, name, value)
            elif message_type == "NAV_CONTROLLER_OUTPUT":
                self._telemetry.waypoint_distance_m = float(message.wp_dist)
            elif message_type == "SYS_STATUS":
                self._telemetry.battery_voltage_v = (
                    (message.voltage_battery / 1000.0) if message.voltage_battery != 65535 else None
                )
                self._telemetry.battery_current_a = (
                    (message.current_battery / 100.0) if message.current_battery != -1 else None
                )
                self._telemetry.battery_remaining_pct = (
                    int(message.battery_remaining) if message.battery_remaining != -1 else None
                )
                self._telemetry.system_status = self._system_status_name(
                    int(message.onboard_control_sensors_health)
                )
            elif message_type == "HEARTBEAT":
                if not self._is_autopilot_heartbeat(message):
                    continue  # ADSB/companion component — not the vehicle
                try:
                    self._telemetry.mode = mavutil.mode_string_v10(message)
                except Exception:
                    self._telemetry.mode = "UNKNOWN"
                self._telemetry.armed = bool(
                    message.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                )
                self._telemetry.failsafe = self._failsafe_name(int(message.system_status))
                self._telemetry.system_status = self._system_status_enum_name(
                    int(message.system_status)
                )
            elif message_type == "EKF_STATUS_REPORT":
                self._telemetry.ekf_status = self._ekf_status_name(int(message.flags))
            elif message_type == "DISTANCE_SENSOR":
                self._update_depth_sample(message.current_distance / 100.0)
            elif message_type == "NAMED_VALUE_FLOAT" and str(message.name).strip("\x00").lower() in {
                "depth",
                "sonar_depth",
            }:
                self._update_depth_sample(float(message.value))
            elif message_type == "STATUSTEXT":
                self._handle_statustext(message)
            elif message_type == "MAG_CAL_PROGRESS":
                self._handle_mag_cal_progress(message)
            elif message_type == "MAG_CAL_REPORT":
                self._handle_mag_cal_report(message)
            elif message_type == "RC_CHANNELS":
                self._handle_rc_channels(message)
            elif message_type == "COMMAND_LONG":
                self._handle_inbound_command(message)

            now = time.time()
            if now - self._last_push_time >= _TELEMETRY_PUSH_INTERVAL_S:
                self._last_push_time = now
                self._event_queue.put(("telemetry", self._telemetry))

            if self._rate_window_start == 0.0:
                self._rate_window_start = now
            elapsed = now - self._rate_window_start
            if elapsed >= 1.0:
                total = sum(self._msg_type_counts.values())
                breakdown = ", ".join(
                    f"{msg_type}:{count}"
                    for msg_type, count in sorted(
                        self._msg_type_counts.items(), key=lambda item: -item[1]
                    )
                )
                rate_hz = total / elapsed
                attitude_hz = self._msg_type_counts.get("ATTITUDE", 0) / elapsed
                rate_message = (
                    f"MAVLink rate: {rate_hz:.1f} msg/s | ATTITUDE: {attitude_hz:.1f}/s | "
                    f"({breakdown})"
                )
                self._emit_status(rate_message)
                self._event_queue.put(("rate", rate_hz))
                self._msg_type_counts.clear()
                self._rate_window_start = now

    def _handle_mission_item_reached(self, message) -> None:
        """Announce the survey finishing, once, when the last item is reached.

        Slot 0 is home, so the final survey waypoint is at seq count - 1.
        """
        seq = int(message.seq)
        if not self._mission_item_count or self._mission_complete_sent:
            return
        if seq < self._mission_item_count - 1:
            return
        self._mission_complete_sent = True
        self._emit_status("Mission complete — final waypoint reached.")
        self._event_queue.put(("mission_complete", seq))

    def _record_parameter(self, message, name: str, value: float) -> None:
        """Feed a PARAM_VALUE into the in-flight full download, if any.

        ArduPilot answers a PARAM_SET with a PARAM_VALUE too, and marks those
        with index 65535 (UINT16_MAX) rather than a real table position — so
        the value is always kept, but only real indices count as download
        progress.
        """
        index = int(getattr(message, "param_index", 65535))
        count = int(getattr(message, "param_count", 0))
        with self._param_lock:
            self._param_values[name] = value
            self._param_types[name] = int(getattr(message, "param_type", 0))
            if not self._param_download_active:
                return
            self._param_last_rx = time.monotonic()
            if count:
                self._param_expected = count
            if index != 65535:
                self._param_seen_index.add(index)

    def _handle_statustext(self, message) -> None:
        """Surface the vehicle's own words — calibration is driven by them."""
        text = str(message.text).strip("\x00").strip()
        if not text:
            return
        severity = int(getattr(message, "severity", 6))
        self._event_queue.put(("statustext", (severity, text)))
        self._emit_status(f"[vehicle] {text}")

    def _handle_mag_cal_progress(self, message) -> None:
        self._event_queue.put((
            "mag_cal_progress",
            {
                "compass_id": int(message.compass_id),
                "cal_status": int(message.cal_status),
                "attempt": int(message.attempt),
                "completion_pct": int(message.completion_pct),
                "direction": (
                    float(message.direction_x),
                    float(message.direction_y),
                    float(message.direction_z),
                ),
            },
        ))

    def _handle_mag_cal_report(self, message) -> None:
        self._event_queue.put((
            "mag_cal_report",
            {
                "compass_id": int(message.compass_id),
                "cal_status": int(message.cal_status),
                "autosaved": bool(message.autosaved),
                "fitness": float(message.fitness),
                "offsets": (float(message.ofs_x), float(message.ofs_y), float(message.ofs_z)),
            },
        ))

    def _handle_rc_channels(self, message) -> None:
        """Forward raw stick positions, but only while radio cal is watching."""
        if not self._rc_monitor:
            return
        now = time.time()
        if now - self._rc_last_push < 0.05:  # 20 Hz ceiling on the IPC push
            return
        self._rc_last_push = now
        count = min(int(message.chancount), 16)
        channels = [int(getattr(message, f"chan{i}_raw")) for i in range(1, count + 1)]
        self._event_queue.put(("rc_channels", channels))

    def _handle_inbound_command(self, message) -> None:
        """Commands the *vehicle* sends us.

        During a 6-position accel calibration ArduPilot repeatedly broadcasts
        MAV_CMD_ACCELCAL_VEHICLE_POS carrying the pose it wants next, and
        finally SUCCESS/FAILED. That is the whole progress channel for this
        calibration, so it drives the UI directly.
        """
        if int(message.command) != mavutil.mavlink.MAV_CMD_ACCELCAL_VEHICLE_POS:
            return
        step = int(message.param1)
        if step == self._accel_step:
            return  # the vehicle repeats its request until we answer
        self._accel_step = step
        self._event_queue.put(("accel_cal_position", step))

    def _handle_command_ack(self, message) -> None:
        """Report what the vehicle actually did with our reposition request."""
        self._event_queue.put((
            "command_result", (int(message.command), int(message.result))
        ))
        if int(message.command) != mavutil.mavlink.MAV_CMD_DO_REPOSITION:
            return
        result = int(message.result)
        name = self._command_result_name(result)
        if result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
            self._emit_status(f"Go-to ACCEPTED by vehicle ({name}).")
            return
        self._emit_status(f"Go-to REJECTED by vehicle ({name}) — trying Mission Planner path.")
        if self._goto_target is not None:
            self._go_to_fallback(*self._goto_target)

    def _handle_position_target(self, message) -> None:
        """Compare the vehicle's own guided target with the point we asked for."""
        if self._goto_target is None:
            return
        requested_lat, requested_lon = self._goto_target
        target_lat = message.lat_int / 1e7
        target_lon = message.lon_int / 1e7
        offset_m = self._distance_m(requested_lat, requested_lon, target_lat, target_lon)
        current = ""
        if self._telemetry.latitude is not None and self._telemetry.longitude is not None:
            current = (
                f" | VEHICLE CURRENT lat={self._telemetry.latitude:.7f} "
                f"lon={self._telemetry.longitude:.7f}"
            )
        self._emit_status(
            f"Go-to VEHICLE TARGET lat={target_lat:.7f} lon={target_lon:.7f} "
            f"(offset from requested: {offset_m:.1f} m){current}"
        )
        # One report per go-to; the vehicle republishes this at stream rate.
        self._goto_target = None

    @staticmethod
    def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = phi2 - phi1
        d_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(d_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        )
        return 2 * radius * math.asin(min(1.0, math.sqrt(a)))

    @staticmethod
    def _command_result_name(result: int) -> str:
        try:
            return mavutil.mavlink.enums["MAV_RESULT"][result].name
        except Exception:
            return f"result {result}"

    def _update_depth_sample(self, depth_m: float) -> None:
        self._telemetry.depth_m = depth_m
        self._telemetry.last_depth_time = datetime.now()
        self._telemetry.min_depth_m = (
            depth_m if self._telemetry.min_depth_m is None else min(self._telemetry.min_depth_m, depth_m)
        )
        self._telemetry.max_depth_m = (
            depth_m if self._telemetry.max_depth_m is None else max(self._telemetry.max_depth_m, depth_m)
        )
        # A sounding is only meaningful on the map once we know where it was
        # taken; the reading itself still drives the depth tile and alarm.
        if self._telemetry.latitude is None or self._telemetry.longitude is None:
            return
        self._event_queue.put((
            "depth",
            DepthSample(
                latitude=self._telemetry.latitude,
                longitude=self._telemetry.longitude,
                depth_m=depth_m,
                timestamp=self._telemetry.last_depth_time,
            ),
        ))

    def _failsafe_name(self, system_status: int) -> str:
        return self._system_status_enum_name(system_status)

    def _system_status_enum_name(self, system_status: int) -> str:
        try:
            return mavutil.mavlink.enums["MAV_STATE"][system_status].name
        except Exception:
            return "UNKNOWN"

    def _system_status_name(self, _health_flags: int) -> str:
        return "OK"

    def _ekf_status_name(self, flags: int) -> str:
        return "OK" if flags else "UNKNOWN"

    def run(self) -> None:
        while True:
            try:
                command, payload = self._command_queue.get(timeout=0.2)
            except Empty:
                continue

            if command == "stop":
                self._running = False
                return
            elif command == "connect":
                self.connect_vehicle(payload)
            elif command == "disconnect":
                self.disconnect_vehicle()
            elif command == "upload_mission":
                points, speed = payload
                self.upload_mission(points, speed)
            elif command == "start_mission":
                self.start_mission()
            elif command == "stop_mission":
                self.stop_mission()
            elif command == "resume_mission":
                self.resume_mission()
            elif command == "set_speed":
                self.set_speed(payload)
            elif command == "return_to_launch":
                self.return_to_launch()
            elif command == "manual_control":
                throttle, yaw, announce = payload
                self.send_manual_control(throttle, yaw, announce)
            elif command == "release_manual_control":
                self.release_manual_control()
            elif command == "set_mode":
                self._set_mode(payload)
            elif command == "go_to":
                latitude, longitude = payload
                self.go_to(latitude, longitude)
            elif command == "set_home_here":
                self.set_home_here()
            elif command == "request_parameter":
                self.request_parameter(payload)
            elif command == "set_parameter":
                name, value = payload
                self.set_parameter(name, value)
            elif command == "arm":
                self.arm_vehicle()
            elif command == "disarm":
                self.disarm_vehicle()
            elif command == "download_parameters":
                self.download_parameters()
            elif command == "calibrate_gyro":
                self.calibrate_gyro()
            elif command == "calibrate_level":
                self.calibrate_level()
            elif command == "calibrate_accel_simple":
                self.calibrate_accel_simple()
            elif command == "calibrate_baro":
                self.calibrate_baro()
            elif command == "start_accel_calibration":
                self.start_accel_calibration()
            elif command == "confirm_accel_position":
                self.confirm_accel_position(payload)
            elif command == "start_compass_calibration":
                retry, autosave = payload
                self.start_compass_calibration(retry, autosave)
            elif command == "accept_compass_calibration":
                self.accept_compass_calibration()
            elif command == "cancel_compass_calibration":
                self.cancel_compass_calibration()
            elif command == "set_rc_calibrating":
                self.set_rc_calibrating(payload)
            elif command == "set_rc_monitor":
                self.set_rc_monitor(payload)
            elif command == "motor_test":
                motor, throttle_pct, seconds, label = payload
                self.motor_test(motor, throttle_pct, seconds, label=label)
            elif command == "reboot_autopilot":
                self.reboot_autopilot()


def run_worker(command_queue, event_queue) -> None:
    """Process entry point. Must stay a plain module-level function — Windows'
    multiprocessing 'spawn' start method pickles this reference and imports
    it fresh in the child process."""
    _Worker(command_queue, event_queue).run()

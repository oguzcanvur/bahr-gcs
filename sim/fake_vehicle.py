"""Pure-Python ArduRover stand-in for exercising the GCS without Gazebo/SITL.

Speaks MAVLink over UDP exactly as a real vehicle does, so the ground station
connects to it with no changes: pick UDP, host 0.0.0.0, port 14550, Connect.

It is a behavioural stand-in, not a physics engine — the point is to exercise
the GCS's own logic (mission upload and verification, mode changes, guided
targets, joystick overrides, depth rendering) on one machine, quickly. Where
ArduPilot's rules matter for that, they are reproduced: slot 0 of a mission is
home, AUTO refuses to arm, guided targets need GUIDED mode, RC overrides
expire.

    python -m sim.fake_vehicle
    python -m sim.fake_vehicle --fault reject-goto --fault drop-waypoints

Run `--help` for the full list of fault injections.
"""
from __future__ import annotations

import argparse
import math
import time

from pymavlink import mavutil

from sim.vehicle_params import DEFAULT_PARAMS, integer_types

# ArduPilot's own SITL default (CMAC, Canberra), so the map lands where the
# real simulator would put it.
HOME_LAT = -35.3632621
HOME_LON = 149.1652374
HOME_ALT_M = 584.0

TICK_HZ = 20.0
TELEMETRY_HZ = 5.0

# Rover mode numbers, from pymavlink's rover mode map.
MODE_MANUAL = 0
MODE_HOLD = 4
MODE_LOITER = 5
MODE_AUTO = 10
MODE_RTL = 11
MODE_GUIDED = 15
MODE_NAMES = {
    MODE_MANUAL: "MANUAL", MODE_HOLD: "HOLD", MODE_LOITER: "LOITER",
    MODE_AUTO: "AUTO", MODE_RTL: "RTL", MODE_GUIDED: "GUIDED",
}

EARTH_R = 6371000.0
WP_RADIUS_M = 3.0
RC_OVERRIDE_TIMEOUT_S = 1.5

# Commands whose COMMAND_LONG param5/param6 carry a lat/lon and are therefore
# scaled by 1e7 into COMMAND_INT.x/y. Everything else is a plain cast. Mirrors
# GCS_Common.cpp::command_long_stores_location so the simulator converts the
# same way the real autopilot does.
_LOCATION_COMMANDS = {
    mavutil.mavlink.MAV_CMD_DO_SET_HOME,
    mavutil.mavlink.MAV_CMD_DO_SET_ROI,
    mavutil.mavlink.MAV_CMD_DO_SET_ROI_LOCATION,
    mavutil.mavlink.MAV_CMD_DO_REPOSITION,
}

# 6-position accelerometer calibration, in the order ArduPilot asks for them.
ACCEL_POSITIONS = {
    1: "level", 2: "on its LEFT side", 3: "on its RIGHT side",
    4: "nose DOWN", 5: "nose UP", 6: "on its BACK",
}
ACCELCAL_SUCCESS = 16777215
ACCELCAL_FAILED = 16777216


def offset_m(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    return (
        lat + math.degrees(north_m / EARTH_R),
        lon + math.degrees(east_m / (EARTH_R * math.cos(math.radians(lat)))),
    )


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    y = math.sin(d_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    return math.degrees(math.atan2(y, x)) % 360.0


class SeabedModel:
    """Smooth synthetic bathymetry so the depth panel has something real to draw."""

    def __init__(self, base_m: float = 8.0) -> None:
        self._base = base_m

    def depth_at(self, lat: float, lon: float) -> float:
        # Two out-of-phase ripples plus a slope: gives shallows, a channel and
        # a deep pocket rather than a flat sheet.
        north = (lat - HOME_LAT) * 111320.0
        east = (lon - HOME_LON) * 111320.0 * math.cos(math.radians(HOME_LAT))
        # A bounded slope, not a linear one: a plain `+k * east` term runs the
        # depth to zero a few hundred metres out, so everything to one side
        # clamped to the shallow floor and the heat map showed one flat colour.
        slope = 3.0 * math.tanh(east / 250.0)
        depth = (
            self._base
            + 3.5 * math.sin(north / 60.0)
            + 2.5 * math.cos(east / 45.0)
            + slope
        )
        return max(0.4, depth)


class FakeRover:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.link = mavutil.mavlink_connection(
            f"udpout:{args.host}:{args.port}", source_system=1, source_component=1
        )
        self.seabed = SeabedModel(args.depth_base)

        self.lat, self.lon = HOME_LAT, HOME_LON
        self.home_lat, self.home_lon = HOME_LAT, HOME_LON
        self.heading = 0.0
        self.speed = 0.0
        self.target_speed = args.cruise
        self.mode = MODE_MANUAL
        self.armed = False

        self.mission: list[tuple[float, float]] = []   # includes slot 0 (home)
        self.mission_seq = 0
        self.mission_paused = False
        self._expected_items = 0
        self._uploading = False

        self.guided_target: tuple[float, float] | None = None
        self.rc_steering: float | None = None
        self.rc_throttle: float | None = None
        self.rc_last_seen = 0.0

        self._boot_ms = int(time.time() * 1000)
        self._last_telemetry = 0.0
        self._fix_type = 6 if "no-gps" not in args.fault else 0

        # -- setup / calibration -------------------------------------------
        self.params: dict[str, list] = {
            name: [float(value), kind] for name, (value, kind) in DEFAULT_PARAMS.items()
        }
        self._param_names = sorted(self.params)
        self._int_types = integer_types()

        self.accel_cal_step = 0          # 0 = not running, else 1..6
        self._accel_last_request = 0.0
        self.mag_cal_running = False
        self.mag_cal_pct = 0
        self._mag_last_progress = 0.0
        self.rc_calibrating = False
        self._rc_phase = 0.0

    # -- yardimcilar -------------------------------------------------------

    def log(self, message: str) -> None:
        print(f"[sim] {message}", flush=True)

    def _ms(self) -> int:
        return int(time.time() * 1000) - self._boot_ms

    def set_mode(self, mode: int) -> bool:
        if mode == self.mode:
            return True
        name = MODE_NAMES.get(mode, str(mode))
        self.mode = mode
        self.log(f"mode -> {name}")
        if mode == MODE_AUTO and self.mission:
            self.mission_paused = False
        return True

    # -- gelen mesajlar ----------------------------------------------------

    def handle(self, msg) -> None:
        kind = msg.get_type()
        handler = getattr(self, f"_on_{kind.lower()}", None)
        if handler is None:
            return
        try:
            handler(msg)
        except Exception as exc:
            # One malformed packet must not take the simulator down mid-demo;
            # report it and keep flying.
            self.log(f"handler error on {kind}: {type(exc).__name__}: {exc}")

    def _ack(self, command: int, result: int) -> None:
        self.link.mav.command_ack_send(command, result)

    def _statustext(self, text: str, severity: int = 6) -> None:
        """Calibration talks back through STATUSTEXT, so the sim must too."""
        self.link.mav.statustext_send(severity, text.encode("ascii")[:50])
        self.log(text)

    def _on_command_long(self, msg) -> None:
        # Reproduce convert_COMMAND_LONG_to_COMMAND_INT: param5/6 become x/y,
        # scaled by 1e7 only for the commands that carry a location.
        scale = 1e7 if msg.command in _LOCATION_COMMANDS else 1
        x = int(msg.param5 * scale)
        y = int(msg.param6 * scale)
        self._handle_command(msg.command, msg.param1, msg.param2, msg.param3,
                             msg.param4, x, y)

    def _on_command_int(self, msg) -> None:
        self._handle_command(msg.command, msg.param1, msg.param2, msg.param3,
                             msg.param4, msg.x, msg.y)

    def _handle_command(self, command, p1, p2, p3, p4, x, y) -> None:
        m = mavutil.mavlink
        accepted, denied = m.MAV_RESULT_ACCEPTED, m.MAV_RESULT_DENIED

        if command == m.MAV_CMD_DO_SET_MODE:
            self.set_mode(int(p2))
            self._ack(command, accepted)

        elif command == m.MAV_CMD_COMPONENT_ARM_DISARM:
            want = p1 >= 0.5
            if want and self.mode == MODE_AUTO and not self.mission:
                self.log("PreArm: Mode not armable (AUTO with no mission)")
                self._ack(command, denied)
                return
            if want and self._fix_type < 3:
                self.log("PreArm: need GPS fix")
                self._ack(command, denied)
                return
            self.armed = want
            self.log("ARMED" if want else "DISARMED")
            self._ack(command, accepted)

        elif command == m.MAV_CMD_DO_REPOSITION:
            if "reject-goto" in self.args.fault:
                self.log("go-to REJECTED (fault injection)")
                self._ack(command, m.MAV_RESULT_UNSUPPORTED)
                return
            change_mode = int(p2) & 1
            if self.mode != MODE_GUIDED and not change_mode:
                self._ack(command, denied)
                return
            self.set_mode(MODE_GUIDED)
            self.guided_target = (x / 1e7, y / 1e7)
            if p1 > 0:
                self.target_speed = p1
            self.log(f"go-to target {self.guided_target[0]:.7f}, {self.guided_target[1]:.7f}")
            self._ack(command, accepted)

        elif command == m.MAV_CMD_MISSION_START:
            if not self.mission:
                self._ack(command, denied)
                return
            self.mission_seq = 1
            self.mission_paused = False
            self.set_mode(MODE_AUTO)
            self.log(f"mission started, {len(self.mission) - 1} waypoints")
            self._ack(command, accepted)

        elif command == m.MAV_CMD_DO_PAUSE_CONTINUE:
            self.mission_paused = p1 < 0.5
            self.log("mission paused" if self.mission_paused else "mission resumed")
            self._ack(command, accepted)

        elif command == m.MAV_CMD_NAV_RETURN_TO_LAUNCH:
            self.set_mode(MODE_RTL)
            self._ack(command, accepted)

        elif command == m.MAV_CMD_DO_CHANGE_SPEED:
            self.target_speed = max(0.1, p2)
            self.log(f"speed -> {self.target_speed:.1f} m/s")
            self._ack(command, accepted)

        elif command == m.MAV_CMD_DO_SET_HOME:
            if p1 >= 0.5:
                self.home_lat, self.home_lon = self.lat, self.lon
            elif x or y:
                self.home_lat, self.home_lon = x / 1e7, y / 1e7
            self.log(f"home -> {self.home_lat:.7f}, {self.home_lon:.7f}")
            self._ack(command, accepted)

        elif command == m.MAV_CMD_PREFLIGHT_CALIBRATION:
            self._on_preflight_calibration(command, p1, p2, p3, p4, x)

        elif command == m.MAV_CMD_ACCELCAL_VEHICLE_POS:
            self._on_accel_position_confirmed(command, int(p1))

        elif command == m.MAV_CMD_DO_START_MAG_CAL:
            if not self._require_disarmed("compass calibration"):
                self._ack(command, m.MAV_RESULT_FAILED)
                return
            if "cal-fail" in self.args.fault:
                self._statustext("Compass calibration failed to start", 5)
                self._ack(command, m.MAV_RESULT_FAILED)
                return
            self.mag_cal_running = True
            self.mag_cal_pct = 0
            self._mag_last_progress = 0.0
            self._statustext("Compass calibration started", 5)
            self._ack(command, accepted)

        elif command == m.MAV_CMD_DO_ACCEPT_MAG_CAL:
            self.mag_cal_running = False
            self._statustext("Compass calibration accepted", 5)
            self._ack(command, accepted)

        elif command == m.MAV_CMD_DO_CANCEL_MAG_CAL:
            self.mag_cal_running = False
            self.mag_cal_pct = 0
            self._statustext("Compass calibration cancelled", 5)
            self._ack(command, accepted)

        elif command == m.MAV_CMD_DO_MOTOR_TEST:
            if not self.armed and self.params.get("MOT_SAFE_DISARM", [0])[0] < 0.5:
                # Real ArduPilot spins the motor regardless of arm state, but
                # announces it; the loud part is what matters for the operator.
                pass
            self._statustext(f"Motor {int(p1)} test at {p3:g}% for {p4:g}s", 5)
            self._ack(command, accepted)

        elif command == m.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN:
            self._statustext("Rebooting autopilot", 5)
            self._ack(command, accepted)

        else:
            self._ack(command, mavutil.mavlink.MAV_RESULT_UNSUPPORTED)

    # -- kalibrasyon -------------------------------------------------------

    def _require_disarmed(self, what: str) -> bool:
        """Every calibration is refused while armed — GCS_Common.cpp does this."""
        if self.armed:
            self._statustext(f"Disarm to allow {what}", 5)
            return False
        return True

    def _on_preflight_calibration(self, command, p1, p2, p3, p4, x) -> None:
        m = mavutil.mavlink
        if not self._require_disarmed("calibration"):
            self._ack(command, m.MAV_RESULT_FAILED)
            return

        if p1 >= 0.5:
            self._statustext("Calibrating gyros", 5)
            self._statustext("Gyro calibration complete", 5)
            self._ack(command, m.MAV_RESULT_ACCEPTED)
            return

        if p3 >= 0.5:
            self._statustext("Barometer calibration complete", 5)
            self._ack(command, m.MAV_RESULT_ACCEPTED)
            return

        if p4 > 0 or (p4 == 0 and self.rc_calibrating and x == 0 and p1 == 0 and p2 == 0):
            # param4 toggles the vehicle's radio-calibration mode on and off.
            self.rc_calibrating = p4 > 0
            self._statustext(
                "RC calibration started" if self.rc_calibrating else "RC calibration finished", 5
            )
            self._ack(command, m.MAV_RESULT_ACCEPTED)
            return

        if x == 1:      # PREFLIGHT_CALIBRATION_ACCELEROMETER_FULL
            if "cal-fail" in self.args.fault:
                self._statustext("Calibration FAILED", 3)
                self._ack(command, m.MAV_RESULT_FAILED)
                return
            self.accel_cal_step = 1
            self._accel_last_request = 0.0
            self._statustext(f"Place vehicle {ACCEL_POSITIONS[1]} and press any key.", 2)
            self._ack(command, m.MAV_RESULT_ACCEPTED)
            return

        if x == 2:      # ..._TRIM (board level)
            self.params["INS_TRIM_X"][0] = 0.0
            self.params["INS_TRIM_Y"][0] = 0.0
            self._statustext("Level calibration complete", 5)
            self._ack(command, m.MAV_RESULT_ACCEPTED)
            return

        if x == 4:      # ..._SIMPLE
            self._statustext("Simple accel calibration complete", 5)
            self._ack(command, m.MAV_RESULT_ACCEPTED)
            return

        self._ack(command, m.MAV_RESULT_UNSUPPORTED)

    def _on_accel_position_confirmed(self, command, step: int) -> None:
        """The GCS says the boat is in the pose we asked for."""
        m = mavutil.mavlink
        if self.accel_cal_step == 0 or step != self.accel_cal_step:
            self._ack(command, m.MAV_RESULT_FAILED)
            return
        self._ack(command, m.MAV_RESULT_ACCEPTED)

        if self.accel_cal_step >= 6:
            self.accel_cal_step = 0
            for axis in "XYZ":
                self.params[f"INS_ACCOFFS_{axis}"][0] = round(0.01 * (ord(axis) - 87), 4)
                self.params[f"INS_ACCSCAL_{axis}"][0] = 1.0
            self._send_accel_position(ACCELCAL_SUCCESS)
            self._statustext("Calibration successful", 5)
            return

        self.accel_cal_step += 1
        self._accel_last_request = 0.0
        self._statustext(
            f"Place vehicle {ACCEL_POSITIONS[self.accel_cal_step]} and press any key.", 2
        )

    def _send_accel_position(self, step: int) -> None:
        """Ask the GCS for a pose, the way AP_AccelCal does."""
        self.link.mav.command_long_send(255, 0, mavutil.mavlink.MAV_CMD_ACCELCAL_VEHICLE_POS,
                                        0, float(step), 0, 0, 0, 0, 0, 0)

    def _tick_calibration(self, now: float) -> None:
        if self.accel_cal_step and now - self._accel_last_request > 1.0:
            self._accel_last_request = now
            self._send_accel_position(self.accel_cal_step)

        if self.mag_cal_running and now - self._mag_last_progress > 0.3:
            self._mag_last_progress = now
            self.mag_cal_pct = min(100, self.mag_cal_pct + 4)
            m = mavutil.mavlink
            status = m.MAG_CAL_RUNNING_STEP_TWO if self.mag_cal_pct > 50 else \
                m.MAG_CAL_RUNNING_STEP_ONE
            for compass_id in (0, 1):
                self.link.mav.mag_cal_progress_send(
                    compass_id, 0b11, status, 1, self.mag_cal_pct,
                    bytes(10), 0.0, 0.0, 0.0,
                )
            if self.mag_cal_pct >= 100:
                self.mag_cal_running = False
                failed = "cal-fail" in self.args.fault
                for compass_id in (0, 1):
                    # 14 fields: the orientation/scale_factor extensions are
                    # not in this pymavlink build's _send signature.
                    self.link.mav.mag_cal_report_send(
                        compass_id, 0b11,
                        m.MAG_CAL_FAILED if failed else m.MAG_CAL_SUCCESS,
                        0 if failed else 1,
                        22.5 if failed else 3.2,
                        12.0, -8.0, 30.0,
                        1.0, 1.0, 1.0,
                        0.0, 0.0, 0.0,
                    )
                self._statustext(
                    "Compass calibration FAILED" if failed else "Compass calibration successful", 5
                )

    # -- parametre protokolu -----------------------------------------------

    def _send_param(self, name: str, index: int) -> None:
        value, kind = self.params[name]
        self.link.mav.param_value_send(
            name.encode("ascii"), float(value), int(kind),
            len(self._param_names), index,
        )

    def _on_param_request_list(self, msg) -> None:
        del msg
        self.log(f"parameter list requested ({len(self._param_names)} parameters)")
        drop = "drop-params" in self.args.fault
        for index, name in enumerate(self._param_names):
            # Fault injection reproduces a lossy link: the GCS must notice the
            # gaps and re-request them by index.
            if drop and index % 7 == 3:
                continue
            self._send_param(name, index)

    @staticmethod
    def _param_name(raw) -> str:
        """pymavlink hands char[] fields back as str, not bytes, so accept both."""
        if isinstance(raw, bytes):
            raw = raw.decode("ascii", "replace")
        return str(raw).rstrip("\x00")

    def _on_param_request_read(self, msg) -> None:
        name = self._param_name(msg.param_id)
        index = int(msg.param_index)
        if index >= 0 and index < len(self._param_names):
            self._send_param(self._param_names[index], index)
        elif name in self.params:
            self._send_param(name, self._param_names.index(name))

    def _on_param_set(self, msg) -> None:
        name = self._param_name(msg.param_id)
        if name not in self.params:
            self.log(f"unknown parameter write ignored: {name}")
            return
        kind = self.params[name][1]
        value = float(msg.param_value)
        # ArduPilot stores the parameter's own declared type, so an integer
        # parameter truncates whatever float the GCS asked for.
        if kind in self._int_types:
            value = float(int(value))
        self.params[name][0] = value
        self.log(f"{name} = {value:g}")
        self._send_param(name, self._param_names.index(name))

    # -- gorev protokolu ---------------------------------------------------

    def _on_mission_clear_all(self, msg) -> None:
        del msg
        self.mission.clear()
        self.mission_seq = 0

    def _on_mission_count(self, msg) -> None:
        self._expected_items = msg.count
        self._uploading = True
        self.mission = [(0.0, 0.0)] * msg.count
        self.link.mav.mission_request_int_send(255, 0, 0)

    def _on_mission_item_int(self, msg) -> None:
        if not self._uploading:
            return
        if msg.seq < len(self.mission):
            self.mission[msg.seq] = (msg.x / 1e7, msg.y / 1e7)
        nxt = msg.seq + 1
        if nxt < self._expected_items:
            self.link.mav.mission_request_int_send(255, 0, nxt)
        else:
            self._uploading = False
            if "drop-waypoints" in self.args.fault and len(self.mission) > 3:
                removed = self.mission[-2:]
                self.mission = self.mission[:-2]
                self.log(f"silently dropped {len(removed)} waypoints (fault injection)")
            if "corrupt-waypoint" in self.args.fault and len(self.mission) > 2:
                lat, lon = self.mission[2]
                self.mission[2] = (lat + 0.0005, lon)
                self.log("silently corrupted waypoint 2 (fault injection)")
            self.link.mav.mission_ack_send(255, 0, mavutil.mavlink.MAV_MISSION_ACCEPTED)
            self.log(f"mission stored: {len(self.mission)} items (slot 0 = home)")

    def _on_mission_request_list(self, msg) -> None:
        del msg
        self.link.mav.mission_count_send(255, 0, len(self.mission))

    def _on_mission_request_int(self, msg) -> None:
        if self._uploading or msg.seq >= len(self.mission):
            return
        lat, lon = self.mission[msg.seq]
        self.link.mav.mission_item_int_send(
            255, 0, msg.seq,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
            0, 1, 0, 2, 0, float("nan"),
            int(lat * 1e7), int(lon * 1e7), 0,
        )

    def _on_set_position_target_global_int(self, msg) -> None:
        self.set_mode(MODE_GUIDED)
        self.guided_target = (msg.lat_int / 1e7, msg.lon_int / 1e7)
        self.log(f"guided target (position target) {self.guided_target[0]:.7f}, "
                 f"{self.guided_target[1]:.7f}")

    def _on_rc_channels_override(self, msg) -> None:
        def axis(raw):
            if raw in (0, 0xFFFF):
                return None
            return max(-1.0, min(1.0, (raw - 1500) / 400.0))

        self.rc_steering = axis(msg.chan1_raw)
        self.rc_throttle = axis(msg.chan3_raw)
        self.rc_last_seen = time.time()

    # -- hareket -----------------------------------------------------------

    def _active_target(self) -> tuple[float, float] | None:
        if self.mode == MODE_GUIDED:
            return self.guided_target
        if self.mode == MODE_RTL:
            return (self.home_lat, self.home_lon)
        if self.mode == MODE_AUTO and not self.mission_paused:
            if 1 <= self.mission_seq < len(self.mission):
                return self.mission[self.mission_seq]
        return None

    def step(self, dt: float) -> None:
        if not self.armed:
            self.speed = max(0.0, self.speed - 3.0 * dt)
            self._advance(dt)
            return

        # Manual driving wins whenever a fresh RC override is present.
        override_fresh = time.time() - self.rc_last_seen < RC_OVERRIDE_TIMEOUT_S
        if override_fresh and self.rc_throttle is not None:
            desired = self.rc_throttle * self.args.cruise
            self.heading = (self.heading + (self.rc_steering or 0.0)
                            * self.args.turn_rate * dt) % 360.0
            self.speed += max(-3.0 * dt, min(3.0 * dt, desired - self.speed))
            self._advance(dt)
            return

        target = self._active_target()
        if target is None:
            self.speed = max(0.0, self.speed - 2.0 * dt)
            self._advance(dt)
            return

        target_lat, target_lon = target
        remaining = distance_m(self.lat, self.lon, target_lat, target_lon)

        if remaining < WP_RADIUS_M:
            self._arrive()
            return

        # Turn towards the target at a bounded rate, then drive.
        want = bearing_deg(self.lat, self.lon, target_lat, target_lon)
        error = (want - self.heading + 180.0) % 360.0 - 180.0
        max_turn = self.args.turn_rate * dt
        self.heading = (self.heading + max(-max_turn, min(max_turn, error))) % 360.0

        # Slow down for sharp corrections so the track looks like a real boat's.
        cornering = max(0.35, 1.0 - abs(error) / 90.0)
        desired = self.target_speed * cornering
        self.speed += max(-2.0 * dt, min(2.0 * dt, desired - self.speed))
        self._advance(dt)

    def _arrive(self) -> None:
        if self.mode == MODE_AUTO:
            # The GCS keys mission completion off MISSION_ITEM_REACHED, so
            # report each waypoint as it is ticked off.
            self.link.mav.mission_item_reached_send(self.mission_seq)
            self.mission_seq += 1
            if self.mission_seq >= len(self.mission):
                self.log("mission complete")
                self.set_mode(MODE_HOLD)
                self.mission_seq = max(0, len(self.mission) - 1)
        elif self.mode == MODE_GUIDED:
            if self.guided_target is not None:
                self.log("reached destination")
            self.guided_target = None
        elif self.mode == MODE_RTL:
            self.log("reached home")
            self.set_mode(MODE_HOLD)

    def _advance(self, dt: float) -> None:
        step = self.speed * dt
        self.lat, self.lon = offset_m(
            self.lat, self.lon,
            step * math.cos(math.radians(self.heading)),
            step * math.sin(math.radians(self.heading)),
        )

    # -- giden telemetri ---------------------------------------------------

    def send_telemetry(self) -> None:
        m = mavutil.mavlink
        base_mode = m.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
        if self.armed:
            base_mode |= m.MAV_MODE_FLAG_SAFETY_ARMED

        self.link.mav.heartbeat_send(
            m.MAV_TYPE_SURFACE_BOAT, m.MAV_AUTOPILOT_ARDUPILOTMEGA,
            base_mode, self.mode, m.MAV_STATE_ACTIVE,
        )
        if "no-telemetry" in self.args.fault:
            return

        now_ms = self._ms()
        self.link.mav.global_position_int_send(
            now_ms, int(self.lat * 1e7), int(self.lon * 1e7),
            int(HOME_ALT_M * 1000), 0,
            int(self.speed * math.cos(math.radians(self.heading)) * 100),
            int(self.speed * math.sin(math.radians(self.heading)) * 100),
            0, int(self.heading * 100),
        )
        self.link.mav.gps_raw_int_send(
            now_ms * 1000, self._fix_type, int(self.lat * 1e7), int(self.lon * 1e7),
            int(HOME_ALT_M * 1000), 100, 100, int(self.speed * 100),
            int(self.heading * 100), 12,
        )
        self.link.mav.vfr_hud_send(
            self.speed, self.speed, int(self.heading), 0, HOME_ALT_M, 0.0
        )
        # Gentle roll/pitch so the artificial horizon has something to show.
        self.link.mav.attitude_send(
            now_ms,
            math.radians(3.0 * math.sin(time.time() * 0.7)),
            math.radians(1.5 * math.sin(time.time() * 0.4)),
            math.radians(self.heading), 0.0, 0.0, 0.0,
        )
        self.link.mav.sys_status_send(
            0, 0, 0, 250, int(12.4 * 1000), int(8.5 * 100), 78,
            0, 0, 0, 0, 0, 0,
        )
        self.link.mav.mission_current_send(self.mission_seq)

        # What the GCS needs to show real progress rather than guessing.
        target = self._active_target()
        wp_dist = 0 if target is None else int(distance_m(self.lat, self.lon, *target))
        target_bearing = (
            0 if target is None else int(bearing_deg(self.lat, self.lon, *target))
        )
        self.link.mav.nav_controller_output_send(
            0.0, 0.0, int(self.heading), target_bearing, wp_dist, 0.0, 0.0, 0.0
        )

        if not self.args.no_depth:
            depth = self.seabed.depth_at(self.lat, self.lon)
            self.link.mav.distance_sensor_send(
                now_ms, 20, 5000, int(depth * 100),
                m.MAV_DISTANCE_SENSOR_ULTRASOUND, 1,
                m.MAV_SENSOR_ROTATION_PITCH_270, 0,
            )

        self._send_rc_channels(now_ms)

    def _send_rc_channels(self, now_ms: int) -> None:
        """Synthetic stick traffic so radio calibration has something to see.

        Each channel sweeps its full travel at a different rate, which is what
        an operator waggling the sticks produces — the calibration screen can
        then capture genuine min/max values instead of a flat line.
        """
        self._rc_phase += 0.12
        channels = []
        for index in range(8):
            span = 400 if index < 6 else 300
            wave = math.sin(self._rc_phase * (0.7 + 0.13 * index))
            channels.append(int(1500 + span * wave))
        self.link.mav.rc_channels_send(
            now_ms, 8, *channels, *([0] * 10), 200
        )

    # -- ana dongu ---------------------------------------------------------

    def run(self) -> None:
        self.log(f"sending MAVLink to {self.args.host}:{self.args.port}")
        self.log(f"home {HOME_LAT:.7f}, {HOME_LON:.7f}")
        if self.args.fault:
            self.log(f"fault injection: {', '.join(self.args.fault)}")
        self.log("connect the GCS with UDP, host 0.0.0.0, port "
                 f"{self.args.port}")

        tick = 1.0 / TICK_HZ
        telemetry_interval = 1.0 / TELEMETRY_HZ

        # Windows refuses recvfrom() on a UDP socket that has never sent
        # (WinError 10022), so prime it with one heartbeat before listening.
        self.send_telemetry()

        last = time.time()
        while True:
            now = time.time()
            dt = min(0.25, now - last)
            last = now

            while True:
                try:
                    msg = self.link.recv_match(blocking=False)
                except OSError:
                    # No peer yet, or the GCS went away — keep simulating.
                    break
                if msg is None:
                    break
                self.handle(msg)

            self.step(dt)
            try:
                self._tick_calibration(now)
            except Exception as exc:
                # Reported, not fatal — same reasoning as handle(). Keeping the
                # message visible is what surfaces a bug here at all.
                self.log(f"calibration tick error: {type(exc).__name__}: {exc}")

            if now - self._last_telemetry >= telemetry_interval:
                self._last_telemetry = now
                self.send_telemetry()

            time.sleep(tick)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Python ArduRover stand-in for testing the GCS without Gazebo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="where the GCS is listening (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=14550, help="default: 14550")
    parser.add_argument("--cruise", type=float, default=2.5,
                        help="top speed in m/s (default: 2.5)")
    parser.add_argument("--turn-rate", type=float, default=35.0,
                        help="degrees per second (default: 35)")
    parser.add_argument("--depth-base", type=float, default=8.0,
                        help="mean seabed depth in metres (default: 8)")
    parser.add_argument("--no-depth", action="store_true",
                        help="do not emit sonar readings")
    parser.add_argument(
        "--fault", action="append", default=[],
        choices=["reject-goto", "drop-waypoints", "corrupt-waypoint",
                 "no-gps", "no-telemetry", "drop-params", "cal-fail"],
        help="inject a failure; repeat for several",
    )
    args = parser.parse_args()

    try:
        FakeRover(args).run()
    except KeyboardInterrupt:
        print("\n[sim] stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

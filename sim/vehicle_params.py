"""A plausible ArduRover boat parameter table for the Python simulator.

Not the full ~1200-entry ArduPilot table — enough breadth that the setup
window's grouped views, search, and .param round-trip are exercised against
realistic names, types and defaults.

Values are (default, MAV_PARAM_TYPE). ArduPilot stores integers and floats
distinctly and clamps on write, which is exactly the behaviour the setup
screens must cope with, so the types here are real.
"""
from __future__ import annotations

REAL32 = 9
INT8 = 2
INT16 = 4
INT32 = 6

# name -> (value, type)
DEFAULT_PARAMS: dict[str, tuple[float, int]] = {
    # -- frame / identity ---------------------------------------------------
    "FRAME_CLASS": (2, INT8),          # 2 = boat
    "FRAME_TYPE": (0, INT8),
    "SYSID_THISMAV": (1, INT16),
    "SYSID_MYGCS": (255, INT16),
    "BRD_SAFETYENABLE": (1, INT8),
    "BRD_SAFETY_DEFLT": (1, INT8),
    "LOG_BITMASK": (65535, INT32),
    "SCHED_LOOP_RATE": (50, INT16),

    # -- servo / motor outputs ---------------------------------------------
    "SERVO1_FUNCTION": (73, INT8),     # ThrottleLeft
    "SERVO1_MIN": (1100, INT16),
    "SERVO1_MAX": (1900, INT16),
    "SERVO1_TRIM": (1500, INT16),
    "SERVO1_REVERSED": (0, INT8),
    "SERVO3_FUNCTION": (74, INT8),     # ThrottleRight
    "SERVO3_MIN": (1100, INT16),
    "SERVO3_MAX": (1900, INT16),
    "SERVO3_TRIM": (1500, INT16),
    "SERVO3_REVERSED": (0, INT8),
    "SERVO2_FUNCTION": (0, INT8),
    "SERVO4_FUNCTION": (0, INT8),
    "MOT_PWM_TYPE": (0, INT8),
    "MOT_PWM_FREQ": (16, INT16),
    "MOT_SAFE_DISARM": (0, INT8),
    "MOT_THR_MIN": (0, REAL32),
    "MOT_THR_MAX": (100, REAL32),
    "MOT_SLEWRATE": (100, REAL32),
    "MOT_VEC_THR_BASE": (0, REAL32),

    # -- RC input -----------------------------------------------------------
    **{
        f"RC{ch}_{suffix}": (default, kind)
        for ch in range(1, 9)
        for suffix, default, kind in (
            ("MIN", 1100, INT16),
            ("MAX", 1900, INT16),
            ("TRIM", 1500, INT16),
            ("REVERSED", 0, INT8),
            ("DZ", 30 if ch in (1, 3) else 0, INT16),
            ("OPTION", 0, INT16),
        )
    },
    "RCMAP_ROLL": (1, INT8),
    "RCMAP_THROTTLE": (3, INT8),
    "RCMAP_PITCH": (2, INT8),
    "RCMAP_YAW": (4, INT8),
    "RC_OPTIONS": (0, INT16),
    "MODE_CH": (8, INT8),
    "MODE1": (0, INT8),                # MANUAL
    "MODE2": (1, INT8),                # ACRO
    "MODE3": (4, INT8),                # HOLD
    "MODE4": (5, INT8),                # LOITER
    "MODE5": (10, INT8),               # AUTO
    "MODE6": (11, INT8),               # RTL
    "INITIAL_MODE": (0, INT8),

    # -- navigation ---------------------------------------------------------
    "WP_RADIUS": (2.0, REAL32),
    "WP_SPEED": (2.0, REAL32),
    "WP_ACCEL": (1.0, REAL32),
    "WP_JERK": (1.0, REAL32),
    "WP_OVERSHOOT": (2.0, REAL32),
    "WP_PIVOT_ANGLE": (60, INT16),
    "WP_PIVOT_RATE": (60, INT16),
    "WP_PIVOT_DELAY": (0, REAL32),
    "TURN_RADIUS": (0.9, REAL32),
    "TURN_MAX_G": (0.6, REAL32),
    "CRUISE_SPEED": (2.0, REAL32),
    "CRUISE_THROTTLE": (50, INT16),
    "NAVL1_PERIOD": (20.0, REAL32),
    "NAVL1_DAMPING": (0.75, REAL32),

    # -- steering / speed controllers --------------------------------------
    "ATC_STR_RAT_P": (0.2, REAL32),
    "ATC_STR_RAT_I": (0.2, REAL32),
    "ATC_STR_RAT_D": (0.0, REAL32),
    "ATC_STR_RAT_FF": (0.2, REAL32),
    "ATC_STR_RAT_FILT": (10.0, REAL32),
    "ATC_STR_RAT_MAX": (360.0, REAL32),
    "ATC_STR_ACC_MAX": (180.0, REAL32),
    "ATC_SPEED_P": (0.2, REAL32),
    "ATC_SPEED_I": (0.2, REAL32),
    "ATC_SPEED_D": (0.0, REAL32),
    "ATC_ACCEL_MAX": (1.0, REAL32),
    "ATC_DECEL_MAX": (0.0, REAL32),
    "ATC_BRAKE": (0, INT8),
    "ATC_STOP_SPEED": (0.1, REAL32),

    # -- battery ------------------------------------------------------------
    "BATT_MONITOR": (4, INT8),         # 4 = analog voltage and current
    "BATT_CAPACITY": (10000, INT32),
    "BATT_VOLT_PIN": (2, INT8),
    "BATT_CURR_PIN": (3, INT8),
    "BATT_VOLT_MULT": (10.1, REAL32),
    "BATT_AMP_PERVLT": (17.0, REAL32),
    "BATT_AMP_OFFSET": (0.0, REAL32),
    "BATT_LOW_VOLT": (10.5, REAL32),
    "BATT_CRT_VOLT": (10.0, REAL32),
    "BATT_LOW_MAH": (0, INT32),
    "BATT_CRT_MAH": (0, INT32),
    "BATT_FS_LOW_ACT": (0, INT8),
    "BATT_FS_CRT_ACT": (0, INT8),

    # -- failsafe -----------------------------------------------------------
    "FS_ACTION": (2, INT8),            # 2 = Hold
    "FS_TIMEOUT": (5.0, REAL32),
    "FS_THR_ENABLE": (1, INT8),
    "FS_THR_VALUE": (910, INT16),
    "FS_GCS_ENABLE": (0, INT8),
    "FS_CRASH_CHECK": (0, INT8),
    "FS_EKF_ACTION": (1, INT8),
    "FS_EKF_THRESH": (0.8, REAL32),

    # -- rangefinder / sonar (the survey payload) ---------------------------
    "RNGFND1_TYPE": (0, INT8),
    "RNGFND1_MIN_CM": (20, INT16),
    "RNGFND1_MAX_CM": (5000, INT16),
    "RNGFND1_PIN": (-1, INT8),
    "RNGFND1_SCALING": (3.0, REAL32),
    "RNGFND1_OFFSET": (0.0, REAL32),
    "RNGFND1_ORIENT": (25, INT8),      # 25 = down
    "RNGFND1_POS_X": (0.0, REAL32),
    "RNGFND1_POS_Y": (0.0, REAL32),
    "RNGFND1_POS_Z": (0.0, REAL32),

    # -- GPS / EKF ----------------------------------------------------------
    "GPS_TYPE": (1, INT8),
    "GPS_AUTO_CONFIG": (1, INT8),
    "GPS_AUTO_SWITCH": (1, INT8),
    "GPS_MIN_ELEV": (-100, INT8),
    "AHRS_EKF_TYPE": (3, INT8),
    "AHRS_ORIENTATION": (0, INT8),
    "AHRS_GPS_USE": (1, INT8),
    "EK3_ENABLE": (1, INT8),
    "EK3_SRC1_POSXY": (3, INT8),
    "EK3_SRC1_VELXY": (3, INT8),
    "EK3_SRC1_YAW": (1, INT8),

    # -- compass ------------------------------------------------------------
    "COMPASS_ENABLE": (1, INT8),
    "COMPASS_USE": (1, INT8),
    "COMPASS_USE2": (1, INT8),
    "COMPASS_USE3": (0, INT8),
    "COMPASS_AUTODEC": (1, INT8),
    "COMPASS_DEC": (0.0, REAL32),
    "COMPASS_OFS_X": (0.0, REAL32),
    "COMPASS_OFS_Y": (0.0, REAL32),
    "COMPASS_OFS_Z": (0.0, REAL32),
    "COMPASS_OFS2_X": (0.0, REAL32),
    "COMPASS_OFS2_Y": (0.0, REAL32),
    "COMPASS_OFS2_Z": (0.0, REAL32),
    "COMPASS_ORIENT": (0, INT8),
    "COMPASS_LEARN": (0, INT8),

    # -- inertial sensors ---------------------------------------------------
    "INS_ACCOFFS_X": (0.0, REAL32),
    "INS_ACCOFFS_Y": (0.0, REAL32),
    "INS_ACCOFFS_Z": (0.0, REAL32),
    "INS_ACCSCAL_X": (1.0, REAL32),
    "INS_ACCSCAL_Y": (1.0, REAL32),
    "INS_ACCSCAL_Z": (1.0, REAL32),
    "INS_GYROFFS_X": (0.0, REAL32),
    "INS_GYROFFS_Y": (0.0, REAL32),
    "INS_GYROFFS_Z": (0.0, REAL32),
    "INS_TRIM_X": (0.0, REAL32),
    "INS_TRIM_Y": (0.0, REAL32),
    "INS_GYRO_FILTER": (4, INT8),
    "INS_ACCEL_FILTER": (10, INT8),

    # -- arming -------------------------------------------------------------
    "ARMING_CHECK": (1, INT32),
    "ARMING_REQUIRE": (1, INT8),
    "ARMING_RUDDER": (2, INT8),

    # -- telemetry / serial -------------------------------------------------
    "SERIAL0_BAUD": (115, INT16),
    "SERIAL1_BAUD": (57, INT16),
    "SERIAL1_PROTOCOL": (2, INT8),
    "SERIAL2_BAUD": (57, INT16),
    "SERIAL2_PROTOCOL": (2, INT8),
    "SR1_POSITION": (5, INT16),
    "SR1_EXTRA1": (10, INT16),
    "SR1_RAW_SENS": (2, INT16),
}


def integer_types() -> set[int]:
    return {INT8, INT16, INT32}

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class TelemetryData:
    # Everything the vehicle reports starts as None: a ground station must not
    # invent a position, speed or GPS fix it has not actually received.
    latitude: float | None = None
    longitude: float | None = None
    ground_speed_mps: float | None = None
    heading_deg: float | None = None
    roll_deg: float | None = None
    pitch_deg: float | None = None
    # Guided/reposition targets carry an altitude; QGC sends the vehicle's own
    # current AMSL value rather than a literal zero, so we track both frames.
    altitude_amsl_m: float | None = None
    altitude_rel_m: float | None = None
    fix_type: int | None = None
    # Straight from the vehicle: MISSION_CURRENT.seq and
    # NAV_CONTROLLER_OUTPUT.wp_dist. Guessing the active waypoint from
    # proximity picks the wrong lane on a lawnmower path.
    current_waypoint_seq: int | None = None
    waypoint_distance_m: float | None = None
    mode: str = "UNKNOWN"
    battery_voltage_v: float | None = None
    battery_current_a: float | None = None
    battery_remaining_pct: int | None = None
    depth_m: float | None = None
    last_depth_time: datetime | None = None
    min_depth_m: float | None = None
    max_depth_m: float | None = None
    armed: bool = False
    link_quality_pct: int | None = None
    failsafe: str = "UNKNOWN"
    ekf_status: str = "UNKNOWN"
    system_status: str = "UNKNOWN"


@dataclass(slots=True)
class MissionPoint:
    latitude: float
    longitude: float
    altitude_m: float = 50.0
    # Set on the turn-around arcs between lanes. The GCS slows the vehicle
    # through these and restores survey speed on the straight legs.
    is_turn: bool = False


@dataclass(slots=True)
class MissionStats:
    total_waypoints: int = 0
    active_waypoint: int = 0
    remaining_distance_m: float = 0.0
    estimated_time_s: float = 0.0
    total_area_m2: float = 0.0
    total_track_length_m: float = 0.0
    expected_samples: int = 0


@dataclass(slots=True)
class DepthSample:
    latitude: float
    longitude: float
    depth_m: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

from __future__ import annotations

import math
from typing import Iterable

from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Polygon

from gcs.models import MissionPoint

Point2D = tuple[float, float]
Lane = tuple[Point2D, Point2D]


class SurveyPlanner:
    """Boustrophedon (lawnmower) coverage planner for a lat/lon polygon.

    Lanes are swept inside the polygon; consecutive lanes are joined by
    turn-around arcs that bulge outside the polygon, so a vehicle with a
    minimum turning radius can follow the path without overshooting.
    """

    def __init__(self, waypoint_radius_m: float = 2.0) -> None:
        # ArduPilot's WP_RADIUS. Read from the vehicle when one is connected;
        # 2.0 is ArduRover's default and a safe fallback when planning offline.
        self.waypoint_radius_m = waypoint_radius_m

    METERS_PER_DEG_LAT = 110_540.0
    METERS_PER_DEG_LON_EQUATOR = 111_320.0

    # Arcs are sampled by distance, not by angle. A fixed angular step makes
    # the spacing scale with the turn radius: at 20 deg and a 5 m radius the
    # points land 1.75 m apart, inside ArduPilot's 2 m default WP_RADIUS, so
    # the vehicle marks several "reached" at once and never flies the turn.
    _ARC_STEP_DEG = 20.0          # upper bound on angular resolution
    _MIN_ARC_SPACING_FACTOR = 1.5  # keep points this many WP_RADIUS apart
    # Below this fraction of the lane spacing a transition is treated as a
    # straight hop between segments of the same sweep line, not a U-turn.
    _TURN_MIN_OFFSET_RATIO = 0.5

    # -- public API ---------------------------------------------------------

    def generate_survey_path(
        self,
        polygon_points: Iterable[dict],
        line_spacing_m: float,
        heading_deg: float,
        overlap_ratio: float,
        sample_spacing_m: float,
        altitude_m: float = 50.0,
        turn_radius_m: float = 0.0,
    ) -> list[MissionPoint]:
        plan = self._build_plan(polygon_points, line_spacing_m, heading_deg, overlap_ratio)
        if plan is None:
            return []
        lanes, spacing, rotated, centroid, lat0, lon0 = plan

        path: list[Point2D] = []
        # Parallel flags so the GCS can slow the vehicle through the turns and
        # run the survey speed along the lanes.
        is_turn: list[bool] = []
        for index, (start, end) in enumerate(lanes):
            turn: list[Point2D] = []
            if index > 0:
                turn = self._turn_points(lanes[index - 1], start, spacing, float(turn_radius_m))
                path.extend(turn)
                is_turn.extend([True] * len(turn))
            path.append(start)
            path.append(end)
            # The lane entry closes the arc that led into it — but only when
            # an arc was actually emitted. With turn_radius 0 the path is pure
            # lane endpoints and nothing should be treated as a turn, or the
            # vehicle gets slowed for a manoeuvre that does not exist.
            is_turn.extend([bool(turn), False])

        return [
            MissionPoint(
                latitude=latitude,
                longitude=longitude,
                altitude_m=altitude_m,
                is_turn=turn_flag,
            )
            for turn_flag, (latitude, longitude) in zip(
                is_turn,
                self._to_geographic(path, heading_deg, centroid, lat0, lon0),
            )
        ]

    def generate_sample_points(
        self,
        polygon_points: Iterable[dict],
        line_spacing_m: float,
        heading_deg: float,
        overlap_ratio: float,
        sample_spacing_m: float,
    ) -> list[dict[str, float]]:
        plan = self._build_plan(polygon_points, line_spacing_m, heading_deg, overlap_ratio)
        if plan is None:
            return []
        lanes, _spacing, _rotated, centroid, lat0, lon0 = plan

        # Samples belong to the survey lanes only — nothing is measured while
        # the vehicle is turning around outside the polygon.
        densified: list[Point2D] = []
        lane_of_point: list[int] = []
        for lane_index, (start, end) in enumerate(lanes):
            points = self._densify_lane(start, end, sample_spacing_m)
            densified.extend(points)
            lane_of_point.extend([lane_index] * len(points))

        return [
            {"lat": latitude, "lng": longitude, "lane": lane_of_point[index]}
            for index, (latitude, longitude) in enumerate(
                self._to_geographic(densified, heading_deg, centroid, lat0, lon0)
            )
        ]

    # -- lane sweep ---------------------------------------------------------

    def _build_plan(
        self,
        polygon_points: Iterable[dict],
        line_spacing_m: float,
        heading_deg: float,
        overlap_ratio: float,
    ):
        points = list(polygon_points)
        if len(points) < 3:
            return None

        local_polygon, lat0, lon0 = self._to_local_polygon(points)
        if not local_polygon.is_valid:
            local_polygon = local_polygon.buffer(0)
        if local_polygon.is_empty or local_polygon.area <= 0:
            return None

        spacing = max(1.0, float(line_spacing_m) * max(0.05, 1.0 - float(overlap_ratio)))
        centroid = local_polygon.centroid
        rotated = affinity.rotate(local_polygon, -heading_deg, origin=centroid)
        lanes = self._sweep_lanes(rotated, spacing)
        if not lanes:
            return None
        return lanes, spacing, rotated, centroid, lat0, lon0

    def _sweep_lanes(self, rotated: Polygon, spacing: float) -> list[Lane]:
        min_x, min_y, max_x, max_y = rotated.bounds

        rows: list[list[Lane]] = []
        # Inset by half a lane so the first and last sweep line sit inside the
        # polygon instead of grazing its edge and clipping to a single point.
        y = min_y + spacing / 2.0
        while y <= max_y:
            cutter = LineString([(min_x - spacing, y), (max_x + spacing, y)])
            row: list[Lane] = []
            for segment in self._extract_segments(rotated.intersection(cutter)):
                coords = list(segment.coords)
                if len(coords) < 2:
                    continue
                first, last = coords[0], coords[-1]
                if last[0] < first[0]:
                    first, last = last, first
                row.append((first, last))
            if row:
                rows.append(sorted(row, key=lambda lane: lane[0][0]))
            y += spacing

        lanes: list[Lane] = []
        cursor: Point2D | None = None
        for index, row in enumerate(rows):
            # Alternate which side of the polygon each row is entered from, so
            # the sweep snakes instead of flying back across every row.
            ordered = row if index % 2 == 0 else list(reversed(row))
            for start, end in ordered:
                if cursor is not None and self._distance(cursor, end) < self._distance(
                    cursor, start
                ):
                    start, end = end, start
                lanes.append((start, end))
                cursor = end
        return lanes

    # -- turn-around geometry ----------------------------------------------

    def _turn_points(
        self, previous_lane: Lane, entry: Point2D, spacing: float, turn_radius_m: float
    ) -> list[Point2D]:
        """Intermediate waypoints joining the previous lane's exit to `entry`.

        Returned points are strictly between the two lane endpoints; both
        endpoints are emitted by the caller.
        """
        exit_point = previous_lane[1]
        offset = entry[1] - exit_point[1]
        if turn_radius_m <= 0 or abs(offset) < spacing * self._TURN_MIN_OFFSET_RATIO:
            return []

        direction = 1.0 if previous_lane[1][0] >= previous_lane[0][0] else -1.0
        # Both lane ends are pulled out to a common turn line just beyond the
        # outermost of the two, so the arc never cuts back into the polygon.
        turn_line_x = (
            max(exit_point[0], entry[0]) if direction > 0 else min(exit_point[0], entry[0])
        )

        canonical = self._canonical_turn(abs(offset), turn_radius_m)

        sign_y = 1.0 if offset > 0 else -1.0
        points = [
            (turn_line_x + direction * u, exit_point[1] + sign_y * v) for u, v in canonical
        ]

        # Straight run-outs to the turn line, when a lane ends short of it.
        head: list[Point2D] = []
        if abs(turn_line_x - exit_point[0]) > 1e-6:
            head.append((turn_line_x, exit_point[1]))
        tail: list[Point2D] = []
        if abs(turn_line_x - entry[0]) > 1e-6:
            tail.append((turn_line_x, entry[1]))
        return head + points + tail

    def _canonical_turn(self, offset: float, radius: float) -> list[Point2D]:
        """U-turn from (0, 0) heading +u to (0, offset) heading -u, bulging +u.

        Excludes both endpoints.
        """
        if offset >= 2.0 * radius:
            # Lanes are far enough apart for a plain semicircle.
            centre = (0.0, offset / 2.0)
            return self._arc(centre, offset / 2.0, -90.0, 90.0, clockwise=False)

        # Lanes are closer together than the vehicle can turn in, so the path
        # has to swing wide: turn in, loop around the outside, turn back.
        c1 = (0.0, radius)
        c3 = (0.0, offset - radius)
        half_gap = radius - offset / 2.0
        c2 = (math.sqrt(max(0.0, 4.0 * radius * radius - half_gap * half_gap)), offset / 2.0)

        t1 = ((c1[0] + c2[0]) / 2.0, (c1[1] + c2[1]) / 2.0)
        t2 = ((c2[0] + c3[0]) / 2.0, (c2[1] + c3[1]) / 2.0)

        points: list[Point2D] = []
        points += self._arc(c1, radius, -90.0, self._angle(c1, t1), clockwise=False)
        points.append(t1)
        points += self._arc(c2, radius, self._angle(c2, t1), self._angle(c2, t2), clockwise=True)
        points.append(t2)
        points += self._arc(c3, radius, self._angle(c3, t2), 90.0, clockwise=False)
        return points

    def _arc(
        self,
        centre: Point2D,
        radius: float,
        start_deg: float,
        end_deg: float,
        clockwise: bool,
    ) -> list[Point2D]:
        """Points along an arc, excluding both endpoints."""
        sweep = (end_deg - start_deg) % 360.0
        if clockwise:
            sweep = -((start_deg - end_deg) % 360.0)
        if abs(sweep) < 1e-9:
            return []

        # Angular resolution gives the upper bound; the acceptance radius gives
        # the lower one. Points closer than the vehicle can distinguish are
        # worse than useless — it ticks through them without steering.
        steps = max(1, int(math.ceil(abs(sweep) / self._ARC_STEP_DEG)))
        arc_length = abs(math.radians(sweep)) * radius
        min_spacing = self._MIN_ARC_SPACING_FACTOR * max(0.5, self.waypoint_radius_m)
        max_steps = max(1, int(arc_length // min_spacing))
        steps = min(steps, max_steps)

        points: list[Point2D] = []
        for index in range(1, steps):
            angle = math.radians(start_deg + sweep * index / steps)
            points.append(
                (centre[0] + radius * math.cos(angle), centre[1] + radius * math.sin(angle))
            )
        return points

    @staticmethod
    def _angle(centre: Point2D, point: Point2D) -> float:
        return math.degrees(math.atan2(point[1] - centre[1], point[0] - centre[0]))

    @staticmethod
    def _distance(a: Point2D, b: Point2D) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    # -- helpers ------------------------------------------------------------

    def _densify_lane(self, start: Point2D, end: Point2D, sample_spacing_m: float) -> list[Point2D]:
        length = self._distance(start, end)
        spacing = max(1.0, float(sample_spacing_m))
        if length <= spacing:
            return [start, end]

        steps = max(1, int(length // spacing))
        points = [
            (
                start[0] + (end[0] - start[0]) * index / steps,
                start[1] + (end[1] - start[1]) * index / steps,
            )
            for index in range(steps)
        ]
        points.append(end)
        return points

    def _extract_segments(self, geometry) -> list[LineString]:
        if geometry.is_empty:
            return []
        if isinstance(geometry, LineString):
            return [geometry]
        if isinstance(geometry, MultiLineString):
            return sorted(geometry.geoms, key=lambda line: line.centroid.x)
        if hasattr(geometry, "geoms"):
            segments: list[LineString] = []
            for item in geometry.geoms:
                segments.extend(self._extract_segments(item))
            return sorted(segments, key=lambda line: line.centroid.x)
        return []

    def _to_local_polygon(self, points: list[dict]) -> tuple[Polygon, float, float]:
        lat0 = sum(point["lat"] for point in points) / len(points)
        lon0 = sum(point["lng"] for point in points) / len(points)
        meters_per_deg_lon = self.METERS_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0))
        local_points = [
            (
                (point["lng"] - lon0) * meters_per_deg_lon,
                (point["lat"] - lat0) * self.METERS_PER_DEG_LAT,
            )
            for point in points
        ]
        return Polygon(local_points), lat0, lon0

    def _to_geographic(
        self,
        points: list[Point2D],
        heading_deg: float,
        centroid,
        lat0: float,
        lon0: float,
    ) -> list[tuple[float, float]]:
        angle = math.radians(heading_deg)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        ox, oy = centroid.x, centroid.y
        meters_per_deg_lon = self.METERS_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0))

        geographic: list[tuple[float, float]] = []
        for x, y in points:
            dx, dy = x - ox, y - oy
            rx = ox + dx * cos_a - dy * sin_a
            ry = oy + dx * sin_a + dy * cos_a
            geographic.append(
                (lat0 + ry / self.METERS_PER_DEG_LAT, lon0 + rx / meters_per_deg_lon)
            )
        return geographic

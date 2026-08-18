# GCS Architecture

## Overview

This prototype is split into three layers:

1. UI layer
   - Design system (`gcs/theme.py`): colour tokens, spacing/typographic scales,
     generated icons and the global Qt stylesheet — the single source of truth
     for every visual value in the app
   - Component library (`gcs/components.py`): cards, metric tiles, status pills,
     gauges, sparkline, compass strip and the artificial horizon, all built on
     the design tokens
   - Application shell (`gcs/main_window.py`): top command bar, navigation rail
     with a stacked left panel, map pane, tabbed mission panel, status strip and
     a collapsible event console
   - `QWebEngineView` for the map canvas, with floating glass HUD widgets layered
     on top through a `QStackedLayout`
   - Qt WebChannel bridge for Python/JavaScript communication
2. Planning layer
   - Coverage path generation using `shapely` and `numpy`
   - Converts polygon vertices from WGS84 lat/lon into a local metric frame
   - Generates a rotated lawnmower sweep and converts points back to lat/lon
3. Vehicle layer
   - MAVLink transport and mission commands via `pymavlink`
   - Telemetry receiver loop
   - Simulated telemetry fallback when no vehicle is available

## Data Flow

1. User draws a polygon in Leaflet.
2. Leaflet sends polygon coordinates to Python through `MapBridge`.
3. `SurveyPlanner` generates mission waypoints from polygon + survey parameters.
4. Python pushes the generated path back into Leaflet for visualization.
5. User can drag generated waypoints on the map.
6. Updated waypoint positions are sent back to Python.
7. `MavlinkService` uploads the current mission and issues mission commands.

## Modules

- `gcs/theme.py`
  - Design tokens, scales and the global stylesheet (`apply_theme`)
- `gcs/components.py`
  - Reusable, token-driven widgets shared across every panel
- `gcs/main_window.py`
  - Builds the application shell and orchestrates UI state and user actions
- `gcs/map_bridge.py`
  - Exposes slots/signals between JavaScript and Python
- `gcs/mission_planner.py`
  - Implements the coverage path planner
- `gcs/mavlink_service.py`
  - Handles MAVLink connection, telemetry, mission upload, and commands
- `web/map.html`
  - Leaflet map, polygon editing, waypoint rendering, and drag interaction

## Current Scope

- Included
  - Satellite map
  - Polygon drawing
  - Editable generated waypoints
  - Lawn mower survey generation
  - Telemetry panel
  - MAVLink mission upload/start/stop/RTL hooks
- Not yet included
  - Full QGroundControl mission item model
  - Terrain awareness
  - Camera footprint model
  - Offline map asset packaging
  - Vehicle mode management and ack/result decoding

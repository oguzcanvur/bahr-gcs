# BAHR-GCS

**BAHR** — *Bathymetric Autonomous Hydrographic Reconnaissance*
**BAHR-GCS** — Bathymetric Autonomous Hydrographic Reconnaissance Ground Control Station
*Otonom Batimetrik Hidrografik Keşif Yer Kontrol İstasyonu*

BAHR-GCS is a desktop ground control station built with Python and PyQt6 for Pixhawk and other ArduPilot-based MAVLink vehicles, focused on survey boats and rovers. It combines live telemetry, map-based mission planning, survey path generation, bathymetry capture, manual driving, and vehicle tuning in a single interface.

Otonom araç görev planlama, navigasyon, telemetri, haritalama ve hidrografik veri görselleştirme yer kontrol istasyonu.

## Features

- MAVLink connectivity over `UDP`, `TCP`, and `Serial/COM`
- Live telemetry panel for GPS, speed, heading, mode, battery, EKF, failsafe, and depth
- Leaflet-based interactive map embedded in a PyQt6 desktop app
- Vehicle tracking, home point placement (sends `DO_SET_HOME` to the vehicle), heading cone, and measurement tools
- Polygon-based survey planning with auto-generated boustrophedon coverage paths
- Turn-around arcs sized from the vehicle's own `WP_RADIUS`, so waypoints are never packed closer than the vehicle can resolve them
- A warning when the configured turn radius forces the path outside the survey polygon
- Mission upload with automatic verification — the mission is read back from the vehicle and compared point-by-point; a mismatch is reported rather than assumed to have succeeded
- Sample point generation with lane filtering and numbering
- Flight mode control (`MANUAL`, `HOLD`, `LOITER`, `AUTO`, `GUIDED`, `RTL`) with the active mode highlighted and a one-line description of what each does
- Mission control: Start, Hold, Resume, Return home (with confirmation while armed or mid-mission), and a prompt to return home when the mission completes
- **Go to point** — click the map to send the vehicle to a single location. Uses `MAV_CMD_DO_REPOSITION` the way QGroundControl does, falling back to `SET_POSITION_TARGET_GLOBAL_INT` (Mission Planner's approach) if the vehicle rejects it
- Adaptive survey speed — automatically slows the vehicle through turn-around arcs and restores survey speed on the straight lanes, driven by the vehicle's own `MISSION_CURRENT` reports rather than guessed from position
- Standalone speed changes (`DO_CHANGE_SPEED`) without re-uploading the mission
- Virtual joystick for manual driving over `RC_CHANNELS_OVERRIDE` (Mission Planner's mechanism — not `MANUAL_CONTROL`, which is mismapped on ArduRover's skid-steer channels)
- Vehicle tuning panel — read and write ArduPilot parameters (`WP_RADIUS`, `WP_SPEED`, `WP_ACCEL`, `WP_JERK`, `TURN_RADIUS`, `CRUISE_SPEED`, steering rate PIDs, and more) directly from the GCS, with the vehicle's confirmed value shown rather than what was requested
- **Full setup and calibration screen** — a separate window covering what would otherwise send you to Mission Planner (see [Vehicle Setup](#vehicle-setup))
- Depth heatmap rendering from incoming sonar/depth samples, plus a 2D bathymetry view of soundings captured at the *planned* sample points (not the raw track), switchable between geographic (lat/lon) and local Cartesian (metres east/north from the first sounding) coordinates, with CSV export in both frames
- Waypoint coordinate list — the generated mission as a table (index, lat/lon, leg distance) with CSV export
- USB camera preview, snapshot capture, video recording, and timestamp overlay
- Artificial horizon overlay for roll and pitch visualization
- Token-driven dark design system shared by the desktop UI and the embedded map
- A pure-Python vehicle simulator for testing the GCS without Gazebo or SITL (see [Testing Without Gazebo](#testing-without-gazebo))

## Interface

The UI is built on a fixed application shell instead of floating dock windows:

- Top command bar: brand, link state, sliding compass, live speed/heading/depth/battery, active flight mode, arm state, arm/disarm/RTL
- Left rail: `LINK`, `CRAFT`, `POWER`, `PILOT`, `CAM` pages plus a collapsible `LOG` console
- Center: map canvas with a floating glass toolbar, artificial horizon and HUD readout
- Right: mission workspace with `Plan`, `Mission` and `Depth` tabs
- Bottom: status strip showing the latest event, waypoint count and timestamp

Everything is driven by a single design system (`gcs/theme.py`) — colour tokens,
a 4 px spacing scale, a typographic scale and the global stylesheet. The palette is
derived from the application logo: navy `#002048` sets the hue of every surface and
border, cyan `#00A8F0` is the accent for primary actions and active state. See
`DESIGN.md` for the full specification.

## Screens and Modules

### Connection Manager (`LINK`)

- Select connection type: `UDP`, `TCP`, or `Serial`
- Enter host/port or COM/baud settings
- Connect and disconnect from the vehicle
- Controls that need a vehicle (arm, mode changes, mission commands, the joystick) are disabled until connected

### Map and Mission Tools (`CRAFT` rail page + map overlay)

- Draw a survey polygon directly on the map
- Generate survey lines, turn-around arcs, and mission waypoints
- Move generated waypoints from the map
- Set vehicle home position (updates both the map marker and the vehicle's `DO_SET_HOME`)
- Clear track history
- Toggle heading cone and measurement mode
- **Go to point** — a separate "Vehicle command" section, since unlike the view toggles above it, it actually commands the vehicle

### Survey Planning (`Plan` tab)

- Track spacing, sample spacing, survey speed, heading, overlap ratio, turn radius
- A warning when the turn radius will force the coverage path outside the polygon
- "Vehicle tuning" — opens the compact parameter read/write dialog
- "Vehicle setup & calibration" — opens the full setup window (see below)
- "Slow through turns" toggle for the adaptive speed behaviour
- "Vehicle WP_RADIUS" readout once the value has been requested from the connected vehicle
- Upload / Start / Hold / Resume / Return home
- "Coordinates" — opens the generated waypoint list with CSV export

### Telemetry and Vehicle Status (`PILOT` tab)

The UI displays:

- Latitude and longitude
- Ground speed
- Heading
- Roll and pitch
- Flight mode (with the five/six mode buttons and their descriptions)
- Armed state
- GPS fix
- Link quality
- Failsafe state
- EKF status
- Battery voltage, current, and remaining percentage
- Current, minimum, and maximum depth
- Mission progress (active waypoint, remaining distance, ETA), driven by the vehicle's own `MISSION_CURRENT` / `NAV_CONTROLLER_OUTPUT` rather than the nearest-point guess a lawnmower path would mislead

All numeric telemetry shows `—` rather than a fabricated value until real data has arrived from the vehicle.

### Virtual Joystick (`PILOT` tab)

- Spring-centred stick pad: drag to drive, release to return to neutral and hand control back to the vehicle's own RC input
- Streams `RC_CHANNELS_OVERRIDE` at 10 Hz while engaged (ArduPilot expires manual overrides, so a held stick must repeat)
- Requires `MANUAL` mode and an armed vehicle

### Artificial Horizon

The map overlay includes a compact attitude instrument with:

- Rotating horizon based on roll
- Vertical horizon shift based on pitch
- Fixed aircraft marker
- Roll reference ticks
- Compact heading, speed, depth, roll, and pitch metrics

### Depth and Bathymetry (`Depth` tab)

- Current depth, session min/max, sample count, and how many of the *planned* sample points have been covered
- Depth alarm window with a status pill
- "2D map" — opens a plan-view plot of the soundings captured at planned sample points, colour-coded on the shared depth scale, with a scale bar and the survey polygon outline
  - Switch between `Lat / Lon` and `Metres E/N` (local Cartesian, origin at the first sounding) — both the table and the CSV export follow the selected mode

### Camera Panel (`CAM` tab)

- USB camera selection
- Live camera preview
- Snapshot capture
- Video recording
- Timestamp display

## Vehicle Setup

"Vehicle setup & calibration" on the `Plan` tab opens a separate window covering
the work that would otherwise require Mission Planner. It opens on its own so the
map stays usable, and downloads the full parameter table on first open.

Every parameter carries a Turkish explanation of what it actually does, shown by
hovering the `?` marker next to it — including *why* it matters for a survey boat,
not just what the value is. Parameters that only take effect after a reboot are
labelled as such, and the write button warns before sending them.

| Screen | What it does |
|---|---|
| Genel bakış | Ordered checklist and the safety notes for each calibration |
| Gövde ve kimlik | `FRAME_CLASS` / `FRAME_TYPE`, MAVLink system id, safety switch, logging |
| Motor çıkışları | `SERVOn_FUNCTION` output assignment; a **port map** read live from the vehicle (which `SERVOn` is on which physical `MAIN OUT`/`AUX OUT` pin, and what it does — Mission Planner's Motor Test/Servo Output page), and a motor test with a confirmation gate and a clickable catamaran diagram showing the actual port under each motor |
| Kumanda kalibrasyonu | Live per-channel bars from `RC_CHANNELS`; captures min/max as you sweep the sticks and writes `RCn_MIN` / `RCn_MAX` / `RCn_TRIM` |
| İvmeölçer kalibrasyonu | The 6-position calibration, drawn — the vehicle asks for each pose over `MAV_CMD_ACCELCAL_VEHICLE_POS` and the screen shows which way to lay the boat. Also gyro, board level, simple accel and barometer |
| Pusula kalibrasyonu | Per-compass coverage rings driven by `MAG_CAL_PROGRESS`, with the fitness score and offsets from `MAG_CAL_REPORT` |
| Uçuş modları | `MODE1`…`MODE6` and the mode switch channel |
| Seyir / Direksiyon ve hız | Waypoint navigation and the steering/speed controller gains |
| Batarya / Failsafe | Monitor type, capacity, voltage calibration, and the failsafe actions |
| Sonar / derinlik | `RNGFND1_*` — the sensor the bathymetry data comes from |
| GPS ve pusula / Arm koşulları | Receiver type, EKF source selection, board orientation, arming checks |
| Tüm parametreler | Every parameter on the vehicle: search by name *or* by Turkish description, edit any of them, and save/load Mission Planner-compatible `.param` files with a diff preview before applying |

Notes on behaviour that is easy to get wrong:

- **Calibration is refused while armed.** ArduPilot answers with `Disarm to allow
  calibration`; the header shows arm state so this is visible before you try.
- **Radio calibration warns if a stick is not centred** when you finish. The trim
  is taken from the live reading, so writing it with a stick held over would tell
  the vehicle that "hard over" is neutral.
- **Parameter comparison is done at display precision.** MAVLink carries floats as
  `float32`, so a vehicle storing `0.9` reports `0.89999997615814209`; comparing
  strictly would mark untouched rows as edited and write values nobody changed.
- **`DO_MOTOR_TEST`'s "motor number" is not the physical channel.** ArduPilot's
  `motor_test_order` (`AR_Motors/AP_MotorsUGV.cpp`) is 1=general throttle,
  2=steering, 3=throttle-left, 4=throttle-right — fixed meanings tied to which
  `SRV_Channel` function is assigned, not which pin. On a twin-throttle boat
  (`SERVO1_FUNCTION=73` ThrottleLeft, `SERVO3_FUNCTION=74` ThrottleRight) the
  correct numbers are 3 and 4; sending 1/2 targets functions that are not
  assigned and moves nothing. The Motor çıkışları page reads the vehicle's own
  `SERVOn_FUNCTION` values and computes the right number — verified by watching
  the `COMMAND_ACK` for `MAV_CMD_DO_MOTOR_TEST` on a real Cube Orange.
- **Motor test arms the vehicle internally** (`Rover/motor_test.cpp`,
  `AP_Arming::Method::MOTORTEST`) before spinning the output, so it is blocked
  by the same checks as a normal arm — the safety switch, and RC receiver
  failsafe. On a bench-connected board with no transmitter bound, a
  well-formed `DO_MOTOR_TEST` still comes back `FAILED` with `Arm: Radio
  failsafe on`; a transmitter must be powered and bound for the test to
  actually spin anything.

## Project Structure

- `main.py`: application entry point
- `gcs/app.py`: Qt application bootstrap; installs a guard so an unhandled exception in a Qt slot is logged instead of hard-crashing the process
- `gcs/theme.py`: design system — colour tokens, scales, global stylesheet, brand assets
- `gcs/assets/`: brand mark (`logo.png`) and the window/taskbar icon (`app_icon.png`)
- `gcs/components.py`: reusable UI components (cards, metric tiles, pills, gauges, the virtual joystick)
- `gcs/main_window.py`: application shell, overlays, side panels, controls, the waypoint list / bathymetry / vehicle tuning dialogs
- `gcs/setup_window.py`: the setup and calibration window — parameter pages, radio / accelerometer / compass calibration, motor test, `.param` import and export
- `gcs/setup_widgets.py`: the drawn parts of that window — RC channel bars, boat pose diagram, compass coverage rings, motor layout
- `gcs/param_meta.py`: Turkish parameter dictionary — grouped, with per-parameter explanations, units and value tables
- `gcs/servo_ports.py`: output channel → physical port (`MAIN OUT`/`AUX OUT`) and → `DO_MOTOR_TEST` sequence number, verified against ArduPilot's `AR_Motors`/`SRV_Channel` source
- `gcs/serial_ports.py`: serial port discovery — enumerates ports and flags the ones that look like an autopilot
- `gcs/mavlink_service.py`: GUI-side proxy — forwards commands to the MAVLink worker process, drains telemetry/status back into Qt signals
- `gcs/mavlink_worker.py`: MAVLink connection, telemetry parsing, mission upload/verification, parameter read/write, and command handling, run in a separate OS process to avoid GIL contention with the GUI thread
- `gcs/mission_planner.py`: survey path, turn-arc, and sample point generation
- `gcs/map_bridge.py`: Qt WebChannel bridge between Python and Leaflet
- `gcs/models.py`: shared data models
- `web/map.html`: embedded Leaflet map UI
- `sim/fake_vehicle.py`: pure-Python ArduRover stand-in for testing without Gazebo/SITL — see below
- `sim/vehicle_params.py`: the simulator's parameter table (realistic ArduRover names, defaults and types)
- `setup.bat` / `run.bat`: first-time environment setup, and the everyday launcher

## Requirements

The project currently depends on:

- `numpy`
- `PyQt6`
- `PyQt6-WebEngine`
- `pymavlink`
- `pyserial`
- `shapely`

### Quick setup (Windows)

Double-click `setup.bat`, or run it from a terminal:

```powershell
.\setup.bat
```

This creates a fresh `.venv` using whatever Python is installed on the machine and
installs `requirements.txt` into it. Safe to re-run on any computer — it rebuilds
`.venv` from scratch each time, so a broken or copied-over environment never lingers.

### Running it

Double-click `run.bat`. It runs `setup.bat` first if `.venv` is missing, checks that
the app imports cleanly (printing the error and pausing if not), then launches the
GUI with `pythonw.exe` so no console window is left behind.

### Manual setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Moving this project to another computer

Virtual environments are not portable — copying `.venv` to another machine breaks it,
since it hardcodes an absolute path to its base Python interpreter. When copying this
project (USB drive, zip, etc.), skip these folders and just run `setup.bat` on the
target machine instead:

- `.venv/`
- `.qtcreator/` (Qt Creator recreates this automatically per machine)
- `__pycache__/`
- `*.pyproject.user` (Qt Creator's per-machine project settings)

## Running the App

```powershell
.\.venv\Scripts\python.exe main.py
```

## Typical Workflow

1. Start the application.
2. Choose a connection type: `UDP`, `TCP`, or `Serial`.
3. Enter the required connection parameters and connect.
4. Wait for heartbeat/telemetry; the vehicle's `WP_RADIUS` is requested automatically.
5. Draw a polygon on the map.
6. Generate the survey path and sample points.
7. Upload the mission — the GCS reads it back and reports `VERIFIED` or `MISMATCH`.
8. Arm (in `MANUAL`) and Start. Monitor telemetry, map state, depth, camera feed, and artificial horizon.
9. Open the 2D map in the `Depth` tab once soundings start arriving at the planned sample points.

## Testing Without Gazebo

`sim/fake_vehicle.py` is a small, pure-Python stand-in for ArduRover. It speaks real MAVLink over UDP, so the GCS connects to it exactly as it would a real vehicle or SITL — no Gazebo, no Ubuntu machine required. It is a behavioural stand-in, not a physics engine: the goal is to exercise the GCS's own logic (mission upload/verification, mode changes, guided targets, joystick overrides, adaptive speed, depth capture) quickly on one machine.

```powershell
.\.venv\Scripts\python.exe -m sim.fake_vehicle
```

Then in the GCS: `LINK` → `UDP`, host `0.0.0.0`, port `14550` → Connect.

It reproduces the ArduPilot rules the GCS depends on — mission slot 0 is home, `AUTO` refuses to arm without a mission, guided targets require `GUIDED` mode, RC overrides expire — and emits a synthetic seabed (shallows, a channel, a deep pocket) so the depth heatmap and bathymetry view have something real to plot.

It also answers the whole setup and calibration protocol, so the setup window can be exercised end to end with no autopilot hardware: a ~196-entry parameter table with real ArduPilot names and types (integers truncate on write, as the real thing does), the 6-position accelerometer handshake, compass calibration with progress and a report, sweeping `RC_CHANNELS` so radio calibration has genuine stick travel to capture, motor test, and the "Disarm to allow calibration" refusal when armed. `COMMAND_LONG` is converted to `COMMAND_INT` by the same rule the real autopilot uses, so `param5` reaches the handler the same way.

Options:

| Flag | Effect |
|---|---|
| `--host` | Where the GCS is listening (default `127.0.0.1`) |
| `--port` | default `14550` |
| `--cruise` | Top speed in m/s (default `2.5`) |
| `--turn-rate` | Degrees per second (default `35`) |
| `--depth-base` | Mean seabed depth in metres (default `8`) |
| `--no-depth` | Do not emit sonar readings |
| `--fault` | Inject a failure; repeatable. One of `reject-goto`, `drop-waypoints`, `corrupt-waypoint`, `no-gps`, `no-telemetry`, `drop-params`, `cal-fail` |

`drop-params` withholds part of the `PARAM_REQUEST_LIST` burst the way a lossy telemetry link does, which exercises the gap-recovery logic that re-requests missing indices; `cal-fail` makes the calibrations fail so the error paths can be seen.

Example — force the mission-verification mismatch path:

```powershell
.\.venv\Scripts\python.exe -m sim.fake_vehicle --fault corrupt-waypoint
```

For physics-based testing (waves, thruster dynamics, sensor noise) the GCS also connects to ArduPilot SITL running against Gazebo on a separate Linux machine — see ArduPilot's own [SITL with Gazebo](https://ardupilot.org/dev/docs/sitl-with-gazebo.html) documentation for that setup; it is outside this repository.

## Notes

- The `Serial` link type lists the ports actually present, marks the ones that look like an autopilot with `●`, and pre-selects one; `Rescan` re-reads the list after plugging a board in. A board can expose more than one port — a Cube Orange presents both `Cube Orange Mavlink` and `Cube Orange SLCAN`, and only the first speaks MAVLink.
- Pixhawk serial ports must be configured for MAVLink on the flight controller side.
- A flight controller may put several MAVLink components on one link. A Cube Orange also emits an `MAV_TYPE_ADSB` heartbeat from component 0 with `MAV_AUTOPILOT_INVALID`; the GCS ignores heartbeats from non-autopilot components and addresses commands to the autopilot's own component, since taking the first heartbeat that arrives decodes the wrong component's mode bits.
- Before the GPS has a fix, ArduPilot streams `GLOBAL_POSITION_INT` filled with zeros. The GCS reports that as no position rather than plotting the vehicle at 0°N 0°E.
- The app requests telemetry streams after heartbeat, but actual message availability depends on vehicle configuration.
- Mission upload correctness is verified automatically; a `MISMATCH` means the vehicle's stored mission differs from what was sent and should not be trusted.
- The virtual joystick and manual control both require `MANUAL` mode — ArduRover ignores manual axis input in other modes.
- Only one MAVLink ground station should manage the mission at a time — MAVProxy and this GCS both attempting the mission protocol simultaneously will cancel each other's transfer.
- The embedded map uses online Leaflet/CDN assets and map tiles, so internet access is required at runtime.

## Current Status

This project is a functional prototype with mission upload verification, adaptive survey speed, live parameter tuning, and a bathymetry view already in place. Areas that can still be improved:

- richer MAVLink diagnostics and debug logging beyond the current rate/status reporting
- more robust reconnection behavior
- broader autopilot compatibility testing (developed and tested primarily against ArduRover)
- geofence support (`DO_FENCE_ENABLE`) is not yet exposed in the UI

## License

Released under the [MIT License](LICENSE) — Copyright (c) 2026 Oğuzcan VUR.

You may use, copy, modify and distribute this software, including commercially,
provided the copyright notice and the licence text are kept with it. The
software is provided "as is", without warranty of any kind.

MIT Lisansı ile yayımlanmıştır. Telif ve lisans metni korunduğu sürece
yazılımı ticari kullanım dâhil olmak üzere kullanabilir, değiştirebilir ve
dağıtabilirsiniz. Yazılım herhangi bir garanti verilmeksizin "olduğu gibi"
sunulmaktadır.

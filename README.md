# Tello Web Controller

A locally-deployed web application for controlling a DJI Tello drone via browser. React frontend communicates with a FastAPI backend, which drives the drone through the `djitellopy` Python library.

```
Browser (React) ←HTTP/WS→ FastAPI + djitellopy ←UDP→ DJI Tello (192.168.10.1)
```

<img width="800" alt="Tello Web Controller Interface" src="https://github.com/user-attachments/assets/9ba9d593-b2ef-4b7d-b769-9882847af1cb">

Demo video: https://youtube.com/shorts/Ex-KBuxlEQw


## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose (optional)
- DJI Tello drone (or use mock mode for development)

## Quick Start

### 1. Environment Setup

```bash
cp .env.template .env
# Edit .env as needed (mock mode is enabled by default)
```

### 2. Docker (recommended)

```bash
docker compose up --build
```

This starts both services:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000

### 3. Native Development

**Backend:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# With mock drone (no hardware needed)
TELLO_USE_MOCK_DRONE=true uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# With real drone (connect to Tello Wi-Fi first)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Frontend:**
```bash
cd frontend
npm ci
npm run dev    # http://localhost:5173
```

> **Real drone on Linux**: If you need direct UDP access to the drone (192.168.10.1), add `network_mode: host` to the backend service in `docker-compose.yml`. Note that `network_mode: host` does not work on macOS/Windows — run the backend natively instead.

## Flying with the API

```bash
# Connect
curl -X POST http://localhost:8000/api/control/connect

# Check status
curl http://localhost:8000/api/status

# Takeoff
curl -X POST http://localhost:8000/api/control/takeoff

# Move forward 100cm
curl -X POST http://localhost:8000/api/control/move \
  -H 'Content-Type: application/json' \
  -d '{"direction":"forward","distance_cm":100}'

# Rotate 90° clockwise
curl -X POST http://localhost:8000/api/control/rotate \
  -H 'Content-Type: application/json' \
  -d '{"direction":"cw","angle_deg":90}'

# Land
curl -X POST http://localhost:8000/api/control/land

# Emergency stop (kills motors instantly)
curl -X POST http://localhost:8000/api/control/emergency

# Disconnect
curl -X POST http://localhost:8000/api/control/disconnect
```

### WebRTC Video

The web app negotiates a WebRTC video connection automatically after connecting to the drone. Signaling uses the backend HTTP API; media travels directly over UDP. The Docker Compose setup publishes UDP ports `40000-40100` for WebRTC media. Ensure these ports are allowed between the browser and the backend host.

### Telemetry (WebSocket)

```bash
wscat -c ws://localhost:8000/api/ws/telemetry
```

Server pushes telemetry frames at ~4 Hz:

```json
{
  "type": "telemetry",
  "data": {
    "battery": 85,
    "height": 120,
    "flight_time": 42,
    "temperature": { "high": 65, "low": 60 },
    "attitude": { "pitch": 2, "roll": -1, "yaw": 180 },
    "speed": { "x": 0, "y": 10, "z": 0 },
    "barometer": 150.5,
    "tof_distance": 120
  },
  "timestamp": "2026-03-17T10:30:00.123Z"
}
```

Command log events are also pushed over the same connection:

```json
{
  "type": "command_log",
  "data": {
    "command": "move",
    "params": { "direction": "forward", "distance_cm": 100 },
    "result": "ok",
    "timestamp": "2026-03-17T10:30:01.456Z"
  }
}
```

## Running Tests

```bash
cd backend
source .venv/bin/activate
python -m pytest -v    # 54 tests, all use MockTello (no drone needed)
```

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/control/connect` | Connect to drone |
| POST | `/api/control/disconnect` | Disconnect (auto-lands if flying) |
| POST | `/api/control/takeoff` | Take off |
| POST | `/api/control/land` | Land |
| POST | `/api/control/emergency` | Emergency motor kill |
| POST | `/api/control/move` | Move (body: `{direction, distance_cm}`) |
| POST | `/api/control/rotate` | Rotate (body: `{direction, angle_deg}`) |
| POST | `/api/control/flip` | Flip while flying (body: `{direction}`: `forward`, `back`, `left`, or `right`) |
| POST | `/api/video/webrtc/offer` | Exchange a browser SDP offer for an SDP answer and peer ID |
| DELETE | `/api/video/webrtc/{peer_id}` | Close a WebRTC peer |
| POST | `/api/video/stream/start` | Start video stream |
| POST | `/api/video/stream/stop` | Stop video stream |
| POST | `/api/video/snapshot` | Capture single JPEG frame |
| GET | `/api/status` | `{connected, flying, streaming, battery}` |
| GET | `/api/sequences` | List flight sequences (stub) |
| WS | `/api/ws/telemetry` | Telemetry push (~4Hz) + command logs |

### Allowed Values

| Parameter | Values |
|-----------|--------|
| Move direction | `forward`, `back`, `left`, `right`, `up`, `down` |
| Move distance | 20–500 cm |
| Rotate direction | `cw`, `ccw` |
| Rotate angle | 1–360° |

## Configuration

All environment variables are prefixed with `TELLO_`. See `.env.template` for the full list with defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `TELLO_USE_MOCK_DRONE` | `false` | Use fake drone for development |
| `TELLO_HOST` | `192.168.10.1` | Drone IP address (`TELLO_TELLO_HOST` remains supported as a legacy name; `TELLO_HOST` takes precedence) |
| `TELLO_API_PORT` | `8000` | Backend server port |
| `TELLO_FRONTEND_PORT` | `3000` | Frontend server port (Docker) |
| `TELLO_MCP_API_URL` | `http://127.0.0.1:8000` | Backend URL used by the local MCP server |
| `TELLO_MCP_REQUEST_TIMEOUT` | `10.0` | MCP-to-backend request timeout in seconds |
| `TELLO_TELEMETRY_POLL_HZ` | `4.0` | Telemetry polling frequency |
| `TELLO_FLIGHT_LOG_DB_PATH` | `data/flight_logs.sqlite3` | SQLite database for flight sessions, commands, and telemetry |
| `TELLO_FLIGHT_VIDEO_MAX_BYTES` | `524288000` | Maximum size of one saved flight recording (500 MiB) |
| `TELLO_AUTO_RECORD_ON_TAKEOFF` | `false` | Start browser recording before takeoff and stop after a successful land command or telemetry-confirmed landing |
| `TELLO_AUTO_RECORD_LANDING_SPEED_THRESHOLD_CM_S` | `0` | Maximum 3-axis speed for landing confirmation |
| `TELLO_AUTO_RECORD_LANDING_CONFIRMATION_SAMPLES` | `8` | Consecutive landed telemetry samples required before stopping |
| `TELLO_VIDEO_FPS` | `30` | Video stream frame rate |
| `TELLO_VIDEO_JPEG_QUALITY` | `70` | JPEG compression quality |
| `TELLO_WEBRTC_PUBLIC_HOST` | Origin/request host | Hostname/IP advertised in WebRTC ICE candidates |
| `TELLO_WEBRTC_ICE_SERVERS` | `[]` | JSON array of ICE servers shared with the browser (STUN/TURN) |
| `TELLO_CORS_ORIGINS` | `["http://localhost:3000","http://localhost:5173"]` | Allowed CORS origins |

## Flight History

Connected flights are stored in SQLite at `TELLO_FLIGHT_LOG_DB_PATH`. Each session records command results and telemetry snapshots at the configured polling frequency. While connected, use **Record Flight** to capture the WebRTC feed; starting and stopping the recording are also recorded as flight-history events. Stopping places the WebM recording in the browser's IndexedDB queue; uploads and H.264 MP4 conversion run in the background. Only one recording is stored per flight session. Starting the next recording creates a new session without disconnecting or waiting for the previous video to finish saving; the drone must be grounded.

Uploads are processed sequentially. Failed uploads remain queued and show a **Retry** button; reopening the recording view also resumes queued uploads. Keep the app open while uploads complete. Clearing browser data, private browsing cleanup, or storage exhaustion can remove or prevent queued recordings. If the browser cannot store a recording, keep the page open and retry preparing it before starting another flight. Each recording is limited by `TELLO_FLIGHT_VIDEO_MAX_BYTES`. Saved MP4s are stored beside the database, and legacy WebM recordings are converted on first playback.

With `TELLO_AUTO_RECORD_ON_TAKEOFF=true`, real-drone takeoff waits for a connected browser recorder to confirm recording has started. If the recorder is unavailable or fails to start, takeoff is rejected. This setting is ignored when `TELLO_USE_MOCK_DRONE=true`, so mock takeoff does not require a browser recorder. A successful land command triggers recording to stop without waiting for telemetry; a failed land command does not. As a fallback for other landings, recording stops after telemetry confirms the drone rose at least 15 cm above its starting height, then returned to within 5 cm of that height with speed at or below `TELLO_AUTO_RECORD_LANDING_SPEED_THRESHOLD_CM_S` for `TELLO_AUTO_RECORD_LANDING_CONFIRMATION_SAMPLES` consecutive readings. Defaults require zero speed on all three axes for 8 readings (about 2 seconds at 4 Hz). A successful land response does not wait for the browser to finish saving the recording.

Open **Flight History** to play a saved recording with telemetry values synchronized to the playback position. Selecting a command or telemetry event seeks the video to its timestamp. Use **Full-Screen Replay** for a read-only view that mirrors the live HUD positions, with historical telemetry, a command-only timeline that emphasizes the most recent action at the playhead, and flight controls highlighted briefly as recorded commands play. Replay controls cannot send commands to the drone. Sessions without a recording retain the existing event-only timeline.

Command events are timestamped when the drone command is dispatched, rather than when the SDK call completes, so slow responses do not shift the replay timeline.

Docker Compose mounts a named volume at `/app/data` so the default database survives container recreation. For native development, the database path is relative to the backend working directory unless an absolute path is configured.

The history API includes `GET /api/flights`, `GET /api/flights/active`, `GET /api/flights/{flight_id}/events`, `PUT /api/flights/{flight_id}/video`, and `GET /api/flights/{flight_id}/video`. Event pages are ordered chronologically and support pagination.

## WebRTC Video

The browser sends an SDP offer to `POST /api/video/webrtc/offer`; the backend returns an SDP answer and peer ID. The backend sends captured Tello frames using WebRTC, while snapshots remain available through `POST /api/video/snapshot`. The peer is closed automatically when the video component unmounts or the drone disconnects.

WebRTC offer failures are reported in the HTTP response and backend logs, not the drone command log.

In Docker Compose, UDP ports `40000-40100` are mapped to the backend and used for media. The backend advertises the browser's Origin host (or request host when Origin is absent) by default. Set `TELLO_WEBRTC_PUBLIC_HOST` when a reverse proxy or NAT requires a different browser-reachable address, and forward the configured UDP range to the backend. WebRTC requires direct UDP connectivity; opening only the HTTP/API port is not sufficient.

For networks that need ICE traversal, set `TELLO_WEBRTC_ICE_SERVERS` to a JSON array of standard ICE server objects, for example `[{"urls":"stun:stun.example.org:3478"}]`. The same server configuration is returned to the browser and used by the backend. TURN credentials are sent to the browser, so use short-lived credentials rather than embedding permanent secrets in the frontend.

## Gamepad Control

Connect a standard-mapped PS5 or Xbox controller, connect to the drone, and take off. Enable **Gamepad** in the flight controls, then hold **A/Cross (button 0)** as the dead-man control. Releasing it immediately sends neutral input. Only standard-mapped controllers with at least four axes are supported.

The left stick controls left/right and forward/back; the right stick controls yaw and up/down. A 15% dead zone filters small stick movement. Control is disabled when the controller disconnects, the tab becomes hidden, the drone lands, or a sequence starts. Discrete movement commands neutralize RC input first.

The backend exposes this control as `POST /api/control/rc` with integer `lr`, `fb`, `ud`, and `yaw` values, each bounded to `-100..100`. Non-neutral input requires a connected, flying drone. Use mock-drone mode to test the interface without hardware; gamepad commands can physically move a connected drone.

## MCP Server

The MCP server exposes the existing backend API over stdio. Start the backend first, then configure your MCP client to launch `python -m app.mcp_server` from the `backend` directory. For Claude Desktop, use an absolute interpreter path and set `PYTHONPATH` to the absolute `backend` directory:

```json
{
  "mcpServers": {
    "tello": {
      "command": "/absolute/path/to/backend/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/backend",
        "TELLO_MCP_API_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

For Docker Compose, the MCP client can run the stdio process through `docker compose exec -T backend python -m app.mcp_server`, using an absolute `-f` path to this repository's compose file if the client starts in a different working directory. This requires the backend service to be running.

Available tools: read drone status, connect/disconnect, take off, land, emergency stop, move 20–500 cm, and rotate 1–360°. The MCP process forwards all actions to the backend, preserving its validation and flight logging. These tools can physically move the drone; only enable the MCP server in a trusted client and require explicit user intent for flight actions. Use `TELLO_USE_MOCK_DRONE=true` for development without hardware.

## Project Structure

```
├── backend/                        # FastAPI + djitellopy
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py                 # App entry point, lifespan, CORS
│   │   ├── config.py               # Settings via env vars
│   │   ├── routers/                # API endpoints
│   │   ├── services/               # DroneManager, TelemetryService
│   │   └── models/                 # Pydantic schemas
│   └── tests/                      # pytest (44 tests)
├── frontend/                       # React + Vite + TailwindCSS
│   ├── Dockerfile
│   ├── nginx.conf                  # Nginx reverse proxy config
│   └── src/
├── sample_drone_integration/       # djitellopy reference scripts
│   ├── droneeyes.py                # Video streaming example
│   ├── drone_control_simple.py     # Basic flight control example
│   └── drone_control_full.py       # Advanced flight choreography
├── docs/                           # PRD & Architecture docs
├── docker-compose.yml              # Both services orchestration
├── .env.template                   # Environment variable template
└── .env                            # Local environment config (gitignored)
```

## Safety

- Always have clear space around the drone before takeoff
- Keep battery above 30%
- `/api/control/emergency` bypasses all locks — use if anything goes wrong
- Disconnecting while airborne auto-lands first

## Future Implementations

A roadmap of where this project could go, roughly ordered from most practical to most ambitious.

### Phase 1 — Platform Hardening

- **MCP Server** *(implemented)* — Expose status and bounded drone control tools over stdio; see [MCP Server](#mcp-server)
- **Flight Logging & Replay** *(implemented)* — Persist command outcomes and telemetry snapshots in SQLite, save WebRTC recordings beside the database, and replay them with synchronized telemetry and event seeking; see [Flight History](#flight-history)
- **Gamepad Support** *(implemented)* — Map PS5/Xbox controllers via the Gamepad API to `send_rc_control()` for proper analog stick flying; see [Gamepad Control](#gamepad-control)
- **WebRTC Video** *(implemented)* — Stream captured video over a peer-to-peer WebRTC connection; see [WebRTC Video](#webrtc-video)

### Phase 2 — Computer Vision

- **Object Detection Overlay** — Run YOLOv8/v10 on the video stream (on the ground station GPU or via edge TPU) and draw bounding boxes on the HUD
- **Face / Person Tracking** — Detect a target and auto-generate RC commands to keep them centered in frame — "follow me" mode
- **Optical Flow & SLAM** — Estimate drone position drift without GPS using visual odometry, display estimated position on a 2D minimap
- **QR / ArUco Marker Navigation** — Place markers as waypoints; drone reads them mid-flight to self-correct position

### Phase 3 — Autonomous Flight

- **Waypoint Mission Planner** — Draw a flight path on a 2D/3D grid UI, convert to a sequence of `go_xyz_speed()` commands
- **Geofencing & Safety Zones** — Define virtual boundaries the drone can't cross; auto-hover or return if breached
- **Auto-Landing on Low Battery** — Monitor battery in real-time, trigger autonomous return-and-land below a threshold
- **Obstacle Avoidance** — Fuse TOF sensor + video depth estimation to halt forward movement when obstacles detected

### Phase 4 — AI Agent Layer

- **Claude-Powered Mission Planning** — Describe a mission in natural language ("survey this room in a grid pattern"), agent generates and executes the command sequence
- **Voice Control** — Whisper STT → Claude intent parsing → MCP tool call → drone action, full voice-to-flight pipeline
- **Anomaly Narration** — AI watches the video stream and narrates what it sees, flags unusual objects or changes
- **Multi-Modal Reporting** — After a flight, AI auto-generates a summary report with captured images, telemetry charts, and observations

### Phase 5 — Multi-Drone & Swarm

- **Swarm Support** — Leverage `djitellopy.Swarm` with Tello EDUs, manage multiple drones from one UI with individual + synchronized controls
- **Formation Flying** — Define geometric formations (line, V-shape, grid) that maintain relative positions
- **Collaborative Mapping** — Multiple drones scan different zones simultaneously, stitch results into a combined map

### Phase 6 — Hardware & Integration

- **Raspberry Pi Ground Station Image** — Pre-built SD card image with Docker stack, auto-connects to Tello on boot, zero-config
- **Custom Companion Board** — ESP32 or Pi Pico as a relay for additional sensors (LIDAR, gas, thermal) mounted on the Tello
- **Home Assistant Integration** — Trigger drone patrols from HA automations (e.g. "fly a perimeter check when motion is detected at night")
- **3D Print Accessories** — Custom payload mounts, sensor brackets, and landing gear extensions

> The MCP server, flight history, gamepad controls, and WebRTC video complete the Phase 1 platform-hardening work.

## Challenges

### The Networking Problem: Tello WiFi vs. Internet

This is the fundamental challenge. The Tello drone creates its own WiFi access point (`TELLO-XXXXXX` at `192.168.10.1`), and when your machine connects to it, you lose internet access. This is a dealbreaker for production use — you can't reach MCP servers, cloud APIs, or anything else online.

There are a few ways to solve this, each with different trade-offs.

**Option 1: Dual Network Interfaces (simplest and most reliable)**

Use your machine's built-in WiFi to connect to the Tello, and plug in an Ethernet cable for internet. Most laptops and all desktops support this out of the box. Your OS routing table will send traffic to `192.168.10.x` over WiFi and everything else over Ethernet. This "just works" on Linux, macOS, and Windows without any special configuration — the OS prefers the wired interface for default gateway automatically.

**Option 2: USB WiFi Adapter (no Ethernet available)**

If you don't have Ethernet access, grab a cheap USB WiFi dongle. Connect the dongle to the Tello AP, and keep your built-in WiFi on your home/office network. You'd then configure the backend to bind specifically to the USB adapter's interface for Tello UDP traffic. This requires a small amount of OS-level network config but works well.

**Option 3: Dedicated Ground Station Device (best for production)**

Deploy a small dedicated device — a Raspberry Pi 4/5 or an Intel NUC mini PC — as your permanent "ground station." This device connects its WiFi to the Tello drone and its Ethernet to your local network (router). Your webapp runs on this device via Docker, and you access it from any browser on your regular network.

```
                        YOUR LOCAL NETWORK (with internet)
                        ┌──────────────────────────────────┐
                        │                                  │
  ┌──────────┐    WiFi  │   ┌──────────┐     Ethernet      │    ┌──────────┐
  │  Tello   │◄─────────┤   │  Ground  │◄─────────────────►├───►│  Router  │──► Internet
  │  Drone   │  AP mode  │   │  Station │    192.168.1.x    │    │          │
  │192.168.  │          │   │  (Pi/NUC)│                   │    └──────────┘
  │  10.1    │ UDP 8889 │   │          │                   │
  └──────────┘   8890   │   │ Docker:  │     :3000 (UI)    │    ┌──────────┐
               11111   │   │ backend  │◄────────────────────────│ Your     │
                        │   │ frontend │     :8000 (API)    │    │ Laptop/  │
                        │   └──────────┘                   │    │ Desktop  │
                        │                                  │    └──────────┘
                        └──────────────────────────────────┘
```

The beauty of this setup is that the ground station has two network paths simultaneously — WiFi to the drone, Ethernet to your LAN and internet. Your laptop just opens `http://groundstation.local:3000` in a browser. The backend on the ground station can reach both the Tello (via WiFi UDP) and the internet (via Ethernet) for MCP servers, AI APIs, etc.

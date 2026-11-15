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
| POST | `/api/video/webrtc/offer` | Exchange a browser SDP offer for an SDP answer and peer ID |
| DELETE | `/api/video/webrtc/{peer_id}` | Close a WebRTC peer |
| POST | `/api/video/stream/start` | Start video stream |
| POST | `/api/video/stream/stop` | Stop video stream |
| POST | `/api/video/snapshot` | Capture single JPEG frame |
| GET | `/api/status` | `{connected, flying, streaming, battery}` |
| GET | `/api/sequences` | List flight sequences (stub) |
| WS | `/api/ws/telemetry` | Telemetry (~4Hz), command logs, and vision results when enabled |

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
| `TELLO_TELLO_HOST` | `192.168.10.1` | Drone IP address |
| `TELLO_API_PORT` | `8000` | Backend server port |
| `TELLO_FRONTEND_PORT` | `3000` | Frontend server port (Docker) |
| `TELLO_MCP_API_URL` | `http://127.0.0.1:8000` | Backend URL used by the local MCP server |
| `TELLO_MCP_REQUEST_TIMEOUT` | `10.0` | MCP-to-backend request timeout in seconds |
| `TELLO_TELEMETRY_POLL_HZ` | `4.0` | Telemetry polling frequency |
| `TELLO_FLIGHT_LOG_DB_PATH` | `data/flight_logs.sqlite3` | SQLite database for flight sessions, commands, and telemetry |
| `TELLO_VIDEO_FPS` | `30` | Video stream frame rate |
| `TELLO_VIDEO_JPEG_QUALITY` | `70` | JPEG compression quality |
| `TELLO_WEBRTC_PUBLIC_HOST` | Origin/request host | Hostname/IP advertised in WebRTC ICE candidates |
| `TELLO_WEBRTC_ICE_SERVERS` | `[]` | JSON array of ICE servers shared with the browser (STUN/TURN) |
| `TELLO_CORS_ORIGINS` | `["http://localhost:3000","http://localhost:5173"]` | Allowed CORS origins |

## Flight History

Connected flights are stored in SQLite at `TELLO_FLIGHT_LOG_DB_PATH`. Each session records command results and telemetry snapshots at the configured polling frequency. The UI provides a read-only timeline from the Flight History button on the connection screen or command log.

Docker Compose mounts a named volume at `/app/data` so the default database survives container recreation. For native development, the database path is relative to the backend working directory unless an absolute path is configured.

The read-only API is available at `GET /api/flights` and `GET /api/flights/{flight_id}/events`. Both endpoints support pagination; event pages are ordered chronologically.

## WebRTC Video

The browser sends an SDP offer to `POST /api/video/webrtc/offer`; the backend returns an SDP answer and peer ID. The backend sends captured Tello frames using WebRTC, while snapshots remain available through `POST /api/video/snapshot`. The peer is closed automatically when the video component unmounts or the drone disconnects.

In Docker Compose, UDP ports `40000-40100` are mapped to the backend and used for media. The backend advertises the browser's Origin host (or request host when Origin is absent) by default. Set `TELLO_WEBRTC_PUBLIC_HOST` when a reverse proxy or NAT requires a different browser-reachable address, and forward the configured UDP range to the backend. WebRTC requires direct UDP connectivity; opening only the HTTP/API port is not sufficient.

For networks that need ICE traversal, set `TELLO_WEBRTC_ICE_SERVERS` to a JSON array of standard ICE server objects, for example `[{"urls":"stun:stun.example.org:3478"}]`. The same server configuration is returned to the browser and used by the backend. TURN credentials are sent to the browser, so use short-lived credentials rather than embedding permanent secrets in the frontend.

## Vision Runtime

The backend runs one YOLOv8/YOLOv10 ONNX detector at a time against copied snapshots of the latest drone frame, off the FastAPI event loop. Timestamped detections are published over the existing telemetry WebSocket using normalized bounding-box coordinates and drawn over the WebRTC video. Stale results are hidden after 1.5 seconds. Model weights are not bundled.

Export weights in a separate model-preparation environment with Ultralytics installed, for example `yolo export model=yolov8n.pt format=onnx imgsz=640`. For Docker, put the ONNX file in `./models`, set `TELLO_VISION_MODEL_PATH=/models/yolov8n.onnx`, and restart the backend. Standalone backend runs can point `TELLO_VISION_MODEL_PATH` at the local ONNX file. The built-in detector supports Ultralytics YOLOv8 raw detection outputs and YOLOv10 end-to-end outputs exported for a 640x640 input. `TELLO_VISION_MODEL_FORMAT=auto` detects standard COCO outputs; explicitly set it to `yolov8` or `yolov10` for custom models whose output shapes are ambiguous. Standard COCO labels are used by default; set `TELLO_VISION_CLASS_NAMES` to a JSON string array for custom models.

`TELLO_VISION_DEVICE=auto` uses CUDA only when both the OpenCV DNN build and a CUDA device are available, otherwise it uses CPU. `cpu` and `cuda` can be selected explicitly; CUDA selection fails during startup if unavailable. The built-in OpenCV detector does not support MPS or Edge TPU. CUDA in Docker also requires a CUDA-enabled OpenCV build and GPU access in the container. `TELLO_VISION_INFERENCE_HZ` defaults to `5.0` and is capped at `30`; `TELLO_VISION_CONFIDENCE_THRESHOLD` defaults to `0.25`. The service does not queue frames while inference runs, so it resumes with a fresh frame instead of processing stale video.

Person detections receive temporary IDs by matching overlapping boxes between frames. Select a person in the tracking panel to see whether they are left/right or above/below frame center; IDs reset when the backend restarts and may switch if people cross. This is visual guidance only: it never sends RC commands or moves the drone. Keep flight control manual.

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
- **Flight Logging & Replay** *(implemented)* — Persist command outcomes and telemetry snapshots in SQLite with a read-only timeline in the UI; see [Flight History](#flight-history)
- **Gamepad Support** *(implemented)* — Map PS5/Xbox controllers via the Gamepad API to `send_rc_control()` for proper analog stick flying; see [Gamepad Control](#gamepad-control)
- **WebRTC Video** *(implemented)* — Stream captured video over a peer-to-peer WebRTC connection; see [WebRTC Video](#webrtc-video)

### Phase 2 — Computer Vision

- **Vision Runtime Foundation** *(implemented)* — Add a configurable, latest-frame inference service and normalized WebSocket results
- **Object Detection Overlay** *(implemented)* — Run configurable YOLOv8/v10 ONNX inference and draw fresh, normalized detections over the video HUD; see [Vision Runtime](#vision-runtime)
- **Person Tracking Assist** *(visual guidance implemented)* — Assign temporary IDs to detected people and show selected-target position; no flight commands are sent
- **Follow-Me Autopilot** *(deferred)* — Automatic RC control requires a separate flight-safety design and is not part of person tracking assist
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

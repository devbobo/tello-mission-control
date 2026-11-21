import os

# Force mock mode before any app imports
os.environ["TELLO_USE_MOCK_DRONE"] = "true"
# Keep general API tests independent of the developer's local recording setting.
os.environ["TELLO_AUTO_RECORD_ON_TAKEOFF"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.drone_manager import DroneManager, MockTello
from app.services.telemetry_service import TelemetryService


@pytest.fixture
def mock_tello():
    return MockTello()


@pytest.fixture
def drone_manager():
    return DroneManager()


@pytest.fixture
def test_client(tmp_path, monkeypatch):
    """Synchronous test client with fresh DroneManager in mock mode."""
    monkeypatch.setattr(settings, "flight_log_db_path", tmp_path / "flight_logs.sqlite3")
    dm = DroneManager()
    ts = TelemetryService(dm)
    app.state.drone_manager = dm
    app.state.telemetry_service = ts
    with TestClient(app) as client:
        yield client

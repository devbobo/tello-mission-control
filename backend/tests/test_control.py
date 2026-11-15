import pytest
from fastapi.testclient import TestClient


def test_connect(test_client: TestClient):
    resp = test_client.post("/api/control/connect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "connected"
    assert data["battery"] == 85


def test_status_after_connect(test_client: TestClient):
    test_client.post("/api/control/connect")
    resp = test_client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert data["flying"] is False
    assert data["battery"] == 85


def test_takeoff_before_connect_returns_409(test_client: TestClient):
    resp = test_client.post("/api/control/takeoff")
    assert resp.status_code == 409


def test_move_before_connect_returns_409(test_client: TestClient):
    resp = test_client.post(
        "/api/control/move",
        json={"direction": "forward", "distance_cm": 100},
    )
    assert resp.status_code == 409


def test_move_validates_direction(test_client: TestClient):
    test_client.post("/api/control/connect")
    test_client.post("/api/control/takeoff")
    resp = test_client.post(
        "/api/control/move",
        json={"direction": "diagonal", "distance_cm": 100},
    )
    assert resp.status_code == 422


def test_move_validates_distance_min(test_client: TestClient):
    test_client.post("/api/control/connect")
    test_client.post("/api/control/takeoff")
    resp = test_client.post(
        "/api/control/move",
        json={"direction": "forward", "distance_cm": 10},
    )
    assert resp.status_code == 422


def test_move_validates_distance_max(test_client: TestClient):
    test_client.post("/api/control/connect")
    test_client.post("/api/control/takeoff")
    resp = test_client.post(
        "/api/control/move",
        json={"direction": "forward", "distance_cm": 600},
    )
    assert resp.status_code == 422


def test_rotate_validates_angle_range(test_client: TestClient):
    test_client.post("/api/control/connect")
    test_client.post("/api/control/takeoff")
    resp = test_client.post(
        "/api/control/rotate",
        json={"direction": "cw", "angle_deg": 0},
    )
    assert resp.status_code == 422
    resp = test_client.post(
        "/api/control/rotate",
        json={"direction": "cw", "angle_deg": 400},
    )
    assert resp.status_code == 422


def test_rc_control_requires_connection_and_flight(test_client: TestClient):
    body = {"lr": 0, "fb": 50, "ud": 0, "yaw": 0}
    assert test_client.post("/api/control/rc", json=body).status_code == 409

    test_client.post("/api/control/connect")
    assert test_client.post("/api/control/rc", json=body).status_code == 409


def test_rc_control_accepts_bounded_values_when_flying(test_client: TestClient):
    test_client.post("/api/control/connect")
    test_client.post("/api/control/takeoff")
    response = test_client.post(
        "/api/control/rc",
        json={"lr": 40, "fb": -50, "ud": 20, "yaw": -10},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert test_client.app.state.drone_manager.tello.last_rc_control == (40, -50, 20, -10)


def test_rc_control_validates_each_velocity(test_client: TestClient):
    test_client.post("/api/control/connect")
    test_client.post("/api/control/takeoff")
    for channel in ("lr", "fb", "ud", "yaw"):
        body = {"lr": 0, "fb": 0, "ud": 0, "yaw": 0}
        body[channel] = 101
        response = test_client.post("/api/control/rc", json=body)
        assert response.status_code == 422


def test_full_flight_sequence(test_client: TestClient):
    # Connect
    resp = test_client.post("/api/control/connect")
    assert resp.status_code == 200

    # Takeoff
    resp = test_client.post("/api/control/takeoff")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Move forward
    resp = test_client.post(
        "/api/control/move",
        json={"direction": "forward", "distance_cm": 100},
    )
    assert resp.status_code == 200

    # Rotate CW
    resp = test_client.post(
        "/api/control/rotate",
        json={"direction": "cw", "angle_deg": 90},
    )
    assert resp.status_code == 200

    # Land
    resp = test_client.post("/api/control/land")
    assert resp.status_code == 200

    # Disconnect
    resp = test_client.post("/api/control/disconnect")
    assert resp.status_code == 200


def test_emergency_always_returns_200(test_client: TestClient):
    # Emergency works even without connecting
    resp = test_client.post("/api/control/emergency")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_disconnect_when_not_connected(test_client: TestClient):
    resp = test_client.post("/api/control/disconnect")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_move_before_takeoff_returns_409(test_client: TestClient):
    test_client.post("/api/control/connect")
    resp = test_client.post(
        "/api/control/move",
        json={"direction": "forward", "distance_cm": 100},
    )
    assert resp.status_code == 409


def test_status_default(test_client: TestClient):
    resp = test_client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is False
    assert data["flying"] is False
    assert data["streaming"] is False
    assert data["battery"] == 0

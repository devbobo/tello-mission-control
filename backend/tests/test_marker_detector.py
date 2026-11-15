import hashlib

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from app.models.markers import MarkerDetection
from app.services.marker_detector import OpenCVMarkerDetector


def test_detects_qr_payload_and_normalized_bounds():
    qr_image = cv2.QRCodeEncoder_create().encode("WAYPOINT-A")
    qr_image = cv2.resize(qr_image, (240, 240), interpolation=cv2.INTER_NEAREST)
    qr_image = cv2.copyMakeBorder(
        qr_image, 48, 48, 48, 48, cv2.BORDER_CONSTANT, value=255
    )
    frame = cv2.cvtColor(qr_image, cv2.COLOR_GRAY2BGR)

    detections = OpenCVMarkerDetector().detect(frame)

    assert len(detections) == 1
    marker = detections[0]
    assert marker.marker_type == "qr"
    assert marker.marker_id == hashlib.sha256(b"WAYPOINT-A").hexdigest()[:16]
    assert marker.payload == "WAYPOINT-A"
    assert marker.payload_truncated is False
    assert marker.x_min == pytest.approx(68 / 336)
    assert marker.x_max == pytest.approx(268 / 336)


def test_detects_aruco_id_and_configured_dictionary():
    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    marker_image = aruco.generateImageMarker(dictionary, 7, 120)
    canvas = np.full((200, 200), 255, dtype=np.uint8)
    canvas[40:160, 40:160] = marker_image
    frame = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)

    detections = OpenCVMarkerDetector("DICT_4X4_50").detect(frame)

    assert len(detections) == 1
    assert detections[0].marker_type == "aruco"
    assert detections[0].marker_id == "7"
    assert detections[0].payload is None
    assert detections[0].x_min == pytest.approx(0.2)
    assert detections[0].x_max == pytest.approx(0.795)


def test_rejects_unsupported_aruco_dictionary():
    with pytest.raises(ValueError, match="Unsupported ArUco dictionary"):
        OpenCVMarkerDetector("DICT_NOT_A_REAL_DICTIONARY")


def test_marker_bounds_must_be_normalized_and_positive():
    with pytest.raises(ValidationError):
        MarkerDetection(
            marker_type="aruco",
            marker_id="7",
            x_min=0.8,
            y_min=0.2,
            x_max=0.2,
            y_max=0.8,
        )

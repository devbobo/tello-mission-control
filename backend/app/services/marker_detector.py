from __future__ import annotations

import hashlib
from typing import Literal, Sequence

import cv2
import numpy as np
from numpy.typing import NDArray

from app.models.markers import MarkerDetection

MAX_MARKERS_PER_FRAME = 32
MAX_QR_PAYLOAD_LENGTH = 256


class OpenCVMarkerDetector:
    """Detects QR payloads and ArUco IDs without estimating physical distance."""

    def __init__(self, aruco_dictionary: str = "DICT_4X4_50") -> None:
        aruco_module = getattr(cv2, "aruco", None)
        if aruco_module is None:
            raise RuntimeError(
                "ArUco detection requires the opencv-contrib-python package"
            )
        dictionary_id = getattr(aruco_module, aruco_dictionary, None)
        if not isinstance(dictionary_id, int):
            raise ValueError(f"Unsupported ArUco dictionary: {aruco_dictionary}")

        self.aruco_dictionary = aruco_dictionary
        self._qr_detector = cv2.QRCodeDetector()
        self._aruco_dictionary = aruco_module.getPredefinedDictionary(dictionary_id)
        self._aruco_detector = aruco_module.ArucoDetector(self._aruco_dictionary)

    def detect(self, frame: NDArray[np.uint8]) -> Sequence[MarkerDetection]:
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("Marker detector expects a 3-channel BGR frame")
        frame_height, frame_width = frame.shape[:2]
        if frame_width == 0 or frame_height == 0:
            raise ValueError("Marker detector cannot process an empty frame")

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detections = self._detect_qr(gray, frame_width, frame_height)[
            :MAX_MARKERS_PER_FRAME
        ]
        remaining = MAX_MARKERS_PER_FRAME - len(detections)
        if remaining > 0:
            detections.extend(
                self._detect_aruco(gray, frame_width, frame_height)[:remaining]
            )
        return detections

    def _detect_qr(
        self, gray: NDArray[np.uint8], frame_width: int, frame_height: int
    ) -> list[MarkerDetection]:
        found, payloads, corners, _ = self._qr_detector.detectAndDecodeMulti(gray)
        if not found or corners is None:
            return []

        detections = []
        for payload, points in zip(payloads, corners):
            if not payload or not payload.strip():
                continue
            payload_bytes = payload.encode("utf-8", errors="replace")
            marker_id = hashlib.sha256(payload_bytes).hexdigest()[:16]
            detections.append(
                self._to_detection(
                    marker_type="qr",
                    marker_id=marker_id,
                    payload=payload[:MAX_QR_PAYLOAD_LENGTH],
                    payload_truncated=len(payload) > MAX_QR_PAYLOAD_LENGTH,
                    points=points,
                    frame_width=frame_width,
                    frame_height=frame_height,
                )
            )
        return [detection for detection in detections if detection is not None]

    def _detect_aruco(
        self, gray: NDArray[np.uint8], frame_width: int, frame_height: int
    ) -> list[MarkerDetection]:
        corners, ids, _ = self._aruco_detector.detectMarkers(gray)
        if ids is None:
            return []

        detections = []
        for marker_id, points in zip(ids.reshape(-1), corners):
            detections.append(
                self._to_detection(
                    marker_type="aruco",
                    marker_id=str(int(marker_id)),
                    payload=None,
                    payload_truncated=False,
                    points=points,
                    frame_width=frame_width,
                    frame_height=frame_height,
                )
            )
        return [detection for detection in detections if detection is not None]

    @staticmethod
    def _to_detection(
        *,
        marker_type: Literal["qr", "aruco"],
        marker_id: str,
        payload: str | None,
        payload_truncated: bool,
        points: NDArray[np.float32],
        frame_width: int,
        frame_height: int,
    ) -> MarkerDetection | None:
        points = np.asarray(points, dtype=np.float32).reshape(-1, 2)
        if points.shape[0] < 4 or not np.isfinite(points).all():
            return None

        x_min = float(np.clip(points[:, 0].min(), 0, frame_width)) / frame_width
        y_min = float(np.clip(points[:, 1].min(), 0, frame_height)) / frame_height
        x_max = float(np.clip(points[:, 0].max(), 0, frame_width)) / frame_width
        y_max = float(np.clip(points[:, 1].max(), 0, frame_height)) / frame_height
        if x_min >= x_max or y_min >= y_max:
            return None

        return MarkerDetection(
            marker_type=marker_type,
            marker_id=marker_id,
            payload=payload,
            payload_truncated=payload_truncated,
            x_min=x_min,
            y_min=y_min,
            x_max=x_max,
            y_max=y_max,
        )

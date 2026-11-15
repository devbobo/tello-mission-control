from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

MAX_IMAGE_WIDTH = 320
MAX_FEATURES = 250
MIN_TRACKED_FEATURES = 8
MAX_TRACKING_ERROR = 40.0


@dataclass(frozen=True)
class OpticalFlowResult:
    tracking_valid: bool
    delta_x: float
    delta_y: float
    tracked_points: int
    quality: float


class OpticalFlowEstimator:
    """Estimates relative camera displacement from consecutive grayscale frames."""

    def __init__(self) -> None:
        self._previous_gray: NDArray[np.uint8] | None = None
        self._previous_points: NDArray[np.float32] | None = None

    def reset(self) -> None:
        self._previous_gray = None
        self._previous_points = None

    def update(self, frame: NDArray[np.uint8]) -> OpticalFlowResult:
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("Optical flow expects a 3-channel BGR frame")
        frame_height, frame_width = frame.shape[:2]
        if frame_width == 0 or frame_height == 0:
            raise ValueError("Optical flow cannot process an empty frame")

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if frame_width > MAX_IMAGE_WIDTH:
            scaled_height = max(1, round(frame_height * MAX_IMAGE_WIDTH / frame_width))
            gray = cv2.resize(
                gray,
                (MAX_IMAGE_WIDTH, scaled_height),
                interpolation=cv2.INTER_AREA,
            )

        previous_gray = self._previous_gray
        previous_points = self._previous_points
        self._previous_gray = gray
        self._previous_points = cv2.goodFeaturesToTrack(
            gray,
            maxCorners=MAX_FEATURES,
            qualityLevel=0.01,
            minDistance=8,
            blockSize=7,
        )

        if (
            previous_gray is None
            or previous_points is None
            or len(previous_points) < MIN_TRACKED_FEATURES
            or previous_gray.shape != gray.shape
        ):
            return self._invalid_result(
                len(previous_points) if previous_points is not None else 0
            )

        current_points, status, errors = cv2.calcOpticalFlowPyrLK(
            previous_gray,
            gray,
            previous_points,
            None,
            winSize=(21, 21),
            maxLevel=3,
            criteria=(
                cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                30,
                0.01,
            ),
        )
        if current_points is None or status is None:
            return self._invalid_result(0)

        valid = status.reshape(-1).astype(bool)
        if errors is not None:
            error_values = errors.reshape(-1)
            valid &= np.isfinite(error_values) & (error_values <= MAX_TRACKING_ERROR)
        valid &= np.isfinite(current_points.reshape(-1, 2)).all(axis=1)
        valid &= np.isfinite(previous_points.reshape(-1, 2)).all(axis=1)
        flows = (
            current_points.reshape(-1, 2)[valid]
            - previous_points.reshape(-1, 2)[valid]
        )
        if len(flows) < MIN_TRACKED_FEATURES:
            return self._invalid_result(len(flows))

        median_flow = np.median(flows, axis=0)
        distances = np.linalg.norm(flows - median_flow, axis=1)
        median_deviation = float(np.median(distances))
        inliers = flows[distances <= max(2.0, median_deviation * 3.0)]
        if len(inliers) < MIN_TRACKED_FEATURES:
            return self._invalid_result(len(inliers))

        robust_flow = np.median(inliers, axis=0)
        image_height, image_width = gray.shape
        return OpticalFlowResult(
            tracking_valid=True,
            delta_x=-float(robust_flow[0]) / image_width,
            delta_y=float(robust_flow[1]) / image_height,
            tracked_points=len(inliers),
            quality=len(inliers) / len(previous_points),
        )

    @staticmethod
    def _invalid_result(tracked_points: int) -> OpticalFlowResult:
        return OpticalFlowResult(
            tracking_valid=False,
            delta_x=0.0,
            delta_y=0.0,
            tracked_points=tracked_points,
            quality=0.0,
        )

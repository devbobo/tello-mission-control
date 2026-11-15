import cv2
import numpy as np
import pytest

from app.services.optical_flow import OpticalFlowEstimator


def textured_frame():
    rng = np.random.default_rng(42)
    grayscale = rng.integers(0, 256, (240, 320), dtype=np.uint8)
    return cv2.cvtColor(grayscale, cv2.COLOR_GRAY2BGR)


def test_optical_flow_estimates_robust_relative_translation():
    estimator = OpticalFlowEstimator()
    initial = textured_frame()
    transform = np.float32([[1, 0, 5], [0, 1, -3]])
    shifted = cv2.warpAffine(initial, transform, (320, 240))

    first = estimator.update(initial)
    second = estimator.update(shifted)

    assert not first.tracking_valid
    assert second.tracking_valid
    assert second.delta_x == pytest.approx(-5 / 320, abs=0.005)
    assert second.delta_y == pytest.approx(-3 / 240, abs=0.005)
    assert second.tracked_points >= 8
    assert 0 < second.quality <= 1


def test_optical_flow_reacquires_after_reset_and_handles_textureless_frames():
    estimator = OpticalFlowEstimator()
    blank = np.zeros((240, 320, 3), dtype=np.uint8)

    assert not estimator.update(blank).tracking_valid
    estimator.reset()
    assert not estimator.update(textured_frame()).tracking_valid


def test_optical_flow_requires_bgr_frames():
    estimator = OpticalFlowEstimator()

    with pytest.raises(ValueError, match="3-channel BGR"):
        estimator.update(np.zeros((240, 320), dtype=np.uint8))

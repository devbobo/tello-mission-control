import numpy as np
import pytest

from app.services import yolo_detector as yolo_module
from app.services.yolo_detector import YoloOnnxDetector


class FakeNet:
    def __init__(self, output):
        self.output = output
        self.input = None
        self.backend = None
        self.target = None

    def setInput(self, blob):
        self.input = blob

    def forward(self):
        return self.output

    def setPreferableBackend(self, backend):
        self.backend = backend

    def setPreferableTarget(self, target):
        self.target = target


def create_detector(tmp_path, monkeypatch, output, **kwargs):
    model_path = tmp_path / "detector.onnx"
    model_path.touch()
    net = FakeNet(output)
    monkeypatch.setattr(
        YoloOnnxDetector, "_cuda_available", staticmethod(lambda: False)
    )
    monkeypatch.setattr(yolo_module.cv2.dnn, "readNetFromONNX", lambda _: net)
    return YoloOnnxDetector(
        model_path, class_names=("person", "car"), **kwargs
    ), net


def test_yolov8_output_is_letterboxed_decoded_and_suppressed(tmp_path, monkeypatch):
    output = np.zeros((1, 6, 3), dtype=np.float32)
    output[0, :, 0] = (320, 320, 128, 160, 0.9, 0.1)
    output[0, :, 1] = (322, 322, 128, 160, 0.8, 0.1)
    output[0, :, 2] = (100, 200, 50, 50, 0.1, 0.85)
    detector, net = create_detector(tmp_path, monkeypatch, output, device="auto")

    detections = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8))

    assert detector.device == "cpu"
    assert detector.model_name == "detector"
    assert net.input.shape == (1, 3, 640, 640)
    assert net.backend == yolo_module.cv2.dnn.DNN_BACKEND_OPENCV
    assert net.target == yolo_module.cv2.dnn.DNN_TARGET_CPU
    assert [detection.label for detection in detections] == ["person", "car"]
    assert detections[0].confidence == pytest.approx(0.9)
    assert detections[0].x_min == pytest.approx(0.4)
    assert detections[0].y_min == pytest.approx(1 / 3)
    assert detections[0].x_max == pytest.approx(0.6)
    assert detections[0].y_max == pytest.approx(2 / 3)


def test_yolov10_end_to_end_output_maps_boxes_back_to_frame(tmp_path, monkeypatch):
    output = np.array(
        [[[100, 120, 300, 320, 0.8, 0], [20, 20, 30, 30, 0.1, 1]]],
        dtype=np.float32,
    )
    detector, _ = create_detector(
        tmp_path, monkeypatch, output, device="cpu", model_format="yolov10"
    )

    detections = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8))

    assert len(detections) == 1
    assert detections[0].label == "person"
    assert detections[0].x_min == pytest.approx(100 / 640)
    assert detections[0].y_min == pytest.approx(40 / 480)
    assert detections[0].x_max == pytest.approx(300 / 640)
    assert detections[0].y_max == pytest.approx(240 / 480)


def test_yolo_detector_rejects_unavailable_devices_and_missing_models(
    tmp_path, monkeypatch
):
    model_path = tmp_path / "detector.onnx"
    model_path.touch()
    monkeypatch.setattr(
        YoloOnnxDetector, "_cuda_available", staticmethod(lambda: False)
    )

    with pytest.raises(RuntimeError, match="OpenCV DNN CUDA is unavailable"):
        YoloOnnxDetector(model_path, device="cuda")
    with pytest.raises(RuntimeError, match="not MPS"):
        YoloOnnxDetector(model_path, device="mps")
    with pytest.raises(FileNotFoundError, match="Vision model not found"):
        YoloOnnxDetector(tmp_path / "missing.onnx")

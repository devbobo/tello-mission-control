from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal, Sequence

import cv2
import numpy as np
from numpy.typing import NDArray

from app.models.vision import VisionDetection

logger = logging.getLogger(__name__)

INPUT_SIZE = 640
NMS_THRESHOLD = 0.45
COCO_CLASS_NAMES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana",
    "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza",
    "donut", "cake", "chair", "couch", "potted plant", "bed", "dining table",
    "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock",
    "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
)


class YoloOnnxDetector:
    """Runs Ultralytics YOLOv8 raw or YOLOv10 end-to-end ONNX exports via OpenCV."""

    def __init__(
        self,
        model_path: Path,
        device: str = "auto",
        class_names: Sequence[str] = (),
        confidence_threshold: float = 0.25,
        model_format: Literal["auto", "yolov8", "yolov10"] = "auto",
    ) -> None:
        if model_path.suffix.lower() != ".onnx":
            raise ValueError("Vision model must be an ONNX file")
        if not model_path.is_file():
            raise FileNotFoundError(f"Vision model not found: {model_path}")
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("Confidence threshold must be between 0 and 1")
        if model_format not in {"auto", "yolov8", "yolov10"}:
            raise ValueError(f"Unsupported YOLO model format: {model_format}")
        if any(not name.strip() for name in class_names):
            raise ValueError("Class names cannot be empty")

        self._model_path = model_path
        self._class_names = tuple(class_names)
        self._confidence_threshold = confidence_threshold
        self._model_format = model_format
        self._device = self._resolve_device(device)
        self._net = cv2.dnn.readNetFromONNX(str(model_path))
        if self._device == "cuda":
            self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
            self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
        else:
            self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

    @property
    def model_name(self) -> str:
        return self._model_path.stem

    @property
    def device(self) -> str:
        return self._device

    def detect(self, frame: NDArray[np.uint8]) -> Sequence[VisionDetection]:
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("YOLO detector expects a 3-channel BGR frame")
        frame_height, frame_width = frame.shape[:2]
        if frame_width == 0 or frame_height == 0:
            raise ValueError("YOLO detector cannot process an empty frame")

        scale = min(INPUT_SIZE / frame_width, INPUT_SIZE / frame_height)
        resized_width = round(frame_width * scale)
        resized_height = round(frame_height * scale)
        resized = cv2.resize(frame, (resized_width, resized_height))
        pad_left = (INPUT_SIZE - resized_width) // 2
        pad_top = (INPUT_SIZE - resized_height) // 2
        canvas = np.full((INPUT_SIZE, INPUT_SIZE, 3), 114, dtype=np.uint8)
        canvas[
            pad_top : pad_top + resized_height,
            pad_left : pad_left + resized_width,
        ] = resized
        blob = cv2.dnn.blobFromImage(
            canvas,
            scalefactor=1 / 255,
            size=(INPUT_SIZE, INPUT_SIZE),
            swapRB=True,
            crop=False,
        )
        self._net.setInput(blob)
        predictions = self._net.forward()

        return self._decode(
            predictions,
            frame_width,
            frame_height,
            scale,
            pad_left,
            pad_top,
        )

    def _decode(
        self,
        predictions: NDArray[np.float32],
        frame_width: int,
        frame_height: int,
        scale: float,
        pad_left: int,
        pad_top: int,
    ) -> list[VisionDetection]:
        values = np.asarray(predictions)
        if values.ndim == 3:
            if values.shape[0] != 1:
                raise ValueError("YOLO ONNX model must return one inference batch")
            values = values[0]
        if values.ndim != 2:
            raise ValueError(f"Unsupported YOLO ONNX output shape: {values.shape}")

        expected_features = len(self._class_names) + 4
        if values.shape[1] != 6:
            if values.shape[0] == expected_features or values.shape[0] < values.shape[1]:
                values = values.T

        is_end_to_end = self._model_format == "yolov10" or (
            self._model_format == "auto"
            and values.shape[1] == 6
            and expected_features != 6
        )
        if is_end_to_end:
            if values.shape[1] != 6:
                raise ValueError("YOLOv10 ONNX output must contain xyxy, score, and class")
            candidates = self._decode_end_to_end(values, scale, pad_left, pad_top)
        elif values.shape[1] > 4:
            candidates = self._decode_raw(values, scale, pad_left, pad_top)
        else:
            raise ValueError(f"Unsupported YOLO ONNX output shape: {values.shape}")

        return self._suppress_overlaps(candidates, frame_width, frame_height)

    def _decode_end_to_end(
        self,
        values: NDArray[np.float32],
        scale: float,
        pad_left: int,
        pad_top: int,
    ) -> list[tuple[int, float, tuple[float, float, float, float]]]:
        candidates = []
        for row in values:
            if not np.isfinite(row).all():
                continue
            x_min, y_min, x_max, y_max, confidence, class_index = row[:6]
            class_id = int(class_index)
            if not self._valid_candidate(confidence, class_id):
                continue
            box = (
                (float(x_min) - pad_left) / scale,
                (float(y_min) - pad_top) / scale,
                (float(x_max) - pad_left) / scale,
                (float(y_max) - pad_top) / scale,
            )
            candidates.append((class_id, float(confidence), box))
        return candidates

    def _decode_raw(
        self,
        values: NDArray[np.float32],
        scale: float,
        pad_left: int,
        pad_top: int,
    ) -> list[tuple[int, float, tuple[float, float, float, float]]]:
        candidates = []
        for row in values:
            if not np.isfinite(row).all():
                continue
            class_scores = row[4:]
            class_id = int(np.argmax(class_scores))
            confidence = float(class_scores[class_id])
            if not self._valid_candidate(confidence, class_id):
                continue

            center_x, center_y, box_width, box_height = map(float, row[:4])
            box = (
                (center_x - box_width / 2 - pad_left) / scale,
                (center_y - box_height / 2 - pad_top) / scale,
                (center_x + box_width / 2 - pad_left) / scale,
                (center_y + box_height / 2 - pad_top) / scale,
            )
            candidates.append((class_id, confidence, box))
        return candidates

    def _valid_candidate(self, confidence: float, class_id: int) -> bool:
        return (
            np.isfinite(confidence)
            and self._confidence_threshold <= confidence <= 1
            and class_id >= 0
        )

    def _suppress_overlaps(
        self,
        candidates: list[tuple[int, float, tuple[float, float, float, float]]],
        frame_width: int,
        frame_height: int,
    ) -> list[VisionDetection]:
        by_class: dict[int, list[int]] = {}
        boxes: list[list[int]] = []
        clipped_candidates = []
        for class_id, confidence, (x_min, y_min, x_max, y_max) in candidates:
            x_min = float(np.clip(x_min, 0, frame_width))
            y_min = float(np.clip(y_min, 0, frame_height))
            x_max = float(np.clip(x_max, 0, frame_width))
            y_max = float(np.clip(y_max, 0, frame_height))
            left, top = round(x_min), round(y_min)
            width, height = round(x_max) - left, round(y_max) - top
            if width <= 0 or height <= 0:
                continue
            index = len(clipped_candidates)
            clipped_candidates.append(
                (class_id, confidence, (x_min, y_min, x_max, y_max))
            )
            boxes.append([left, top, width, height])
            by_class.setdefault(class_id, []).append(index)

        selected: list[int] = []
        for indices in by_class.values():
            kept = cv2.dnn.NMSBoxes(
                [boxes[index] for index in indices],
                [clipped_candidates[index][1] for index in indices],
                self._confidence_threshold,
                NMS_THRESHOLD,
            )
            selected.extend(indices[index] for index in np.asarray(kept).reshape(-1))

        detections = []
        for index in selected:
            class_id, confidence, (x_min, y_min, x_max, y_max) = (
                clipped_candidates[index]
            )
            detections.append(
                VisionDetection(
                    label=self._label(class_id),
                    confidence=confidence,
                    x_min=x_min / frame_width,
                    y_min=y_min / frame_height,
                    x_max=x_max / frame_width,
                    y_max=y_max / frame_height,
                )
            )
        return sorted(detections, key=lambda detection: detection.confidence, reverse=True)

    def _label(self, class_id: int) -> str:
        if self._class_names:
            if class_id < len(self._class_names):
                return self._class_names[class_id]
            return f"class_{class_id}"
        if class_id < len(COCO_CLASS_NAMES):
            return COCO_CLASS_NAMES[class_id]
        return f"class_{class_id}"

    @staticmethod
    def _cuda_available() -> bool:
        try:
            return (
                cv2.cuda.getCudaEnabledDeviceCount() > 0
                and cv2.dnn.DNN_TARGET_CUDA
                in cv2.dnn.getAvailableTargets(cv2.dnn.DNN_BACKEND_CUDA)
            )
        except cv2.error:
            return False

    @classmethod
    def _resolve_device(cls, requested: str) -> str:
        if requested == "mps":
            raise RuntimeError("OpenCV DNN YOLO inference supports CPU or CUDA, not MPS")
        if requested == "auto":
            resolved = "cuda" if cls._cuda_available() else "cpu"
            if resolved == "cpu":
                logger.info("CUDA DNN unavailable; using CPU for YOLO inference")
            return resolved
        if requested == "cuda":
            if not cls._cuda_available():
                raise RuntimeError(
                    "CUDA inference was requested, but OpenCV DNN CUDA is unavailable"
                )
            return "cuda"
        if requested == "cpu":
            return "cpu"
        raise ValueError(f"Unsupported YOLO inference device: {requested}")

from __future__ import annotations

from dataclasses import dataclass

from app.models.vision import VisionDetection

MIN_TRACK_IOU = 0.3
MAX_MISSED_FRAMES = 2


@dataclass
class _Track:
    detection: VisionDetection
    missed_frames: int = 0


class DetectionTracker:
    """Assigns temporary IDs by matching same-label detections across frames."""

    def __init__(
        self,
        min_iou: float = MIN_TRACK_IOU,
        max_missed_frames: int = MAX_MISSED_FRAMES,
    ) -> None:
        if not 0 <= min_iou <= 1:
            raise ValueError("Track IoU threshold must be between zero and one")
        if max_missed_frames < 0:
            raise ValueError("Maximum missed frames cannot be negative")
        self._min_iou = min_iou
        self._max_missed_frames = max_missed_frames
        self._next_track_id = 1
        self._tracks: dict[int, _Track] = {}

    def update(
        self, detections: list[VisionDetection]
    ) -> list[VisionDetection]:
        assignments: dict[int, int] = {}
        matches = []
        for track_id, track in self._tracks.items():
            for detection_index, detection in enumerate(detections):
                if track.detection.label != detection.label:
                    continue
                overlap = self._iou(track.detection, detection)
                if overlap >= self._min_iou:
                    matches.append((overlap, track_id, detection_index))
        used_tracks: set[int] = set()
        used_detections: set[int] = set()
        track_assignments: dict[int, int] = {}
        for _, track_id, detection_index in sorted(matches, reverse=True):
            if track_id in used_tracks or detection_index in used_detections:
                continue
            assignments[detection_index] = track_id
            track_assignments[track_id] = detection_index
            used_tracks.add(track_id)
            used_detections.add(detection_index)

        updated_tracks: dict[int, _Track] = {}
        for track_id, track in self._tracks.items():
            if track_id in track_assignments:
                detection_index = track_assignments[track_id]
                updated_tracks[track_id] = _Track(detections[detection_index])
            elif track.missed_frames < self._max_missed_frames:
                updated_tracks[track_id] = _Track(
                    track.detection, track.missed_frames + 1
                )

        for detection_index in range(len(detections)):
            if detection_index not in assignments:
                assignments[detection_index] = self._next_track_id
                updated_tracks[self._next_track_id] = _Track(
                    detections[detection_index]
                )
                self._next_track_id += 1

        self._tracks = updated_tracks
        return [
            detection.model_copy(update={"track_id": assignments[index]})
            for index, detection in enumerate(detections)
        ]

    @staticmethod
    def _iou(left: VisionDetection, right: VisionDetection) -> float:
        intersection_width = max(
            0.0, min(left.x_max, right.x_max) - max(left.x_min, right.x_min)
        )
        intersection_height = max(
            0.0, min(left.y_max, right.y_max) - max(left.y_min, right.y_min)
        )
        intersection = intersection_width * intersection_height
        left_area = (left.x_max - left.x_min) * (left.y_max - left.y_min)
        right_area = (right.x_max - right.x_min) * (right.y_max - right.y_min)
        union = left_area + right_area - intersection
        return intersection / union if union else 0.0

import pytest

from app.models.vision import VisionDetection
from app.services.vision_tracking import DetectionTracker


def detection(label="person", x_min=0.1, x_max=0.4):
    return VisionDetection(
        label=label,
        confidence=0.9,
        x_min=x_min,
        y_min=0.2,
        x_max=x_max,
        y_max=0.8,
    )


def test_tracker_keeps_ids_for_overlapping_same_label_detections():
    tracker = DetectionTracker()

    first = tracker.update([detection(), detection("car", 0.6, 0.9)])
    second = tracker.update(
        [detection(x_min=0.12, x_max=0.42), detection("car", 0.58, 0.88)]
    )

    assert [item.track_id for item in first] == [1, 2]
    assert [item.track_id for item in second] == [1, 2]


def test_tracker_expires_missed_targets_and_never_reuses_ids():
    tracker = DetectionTracker(max_missed_frames=1)

    first = tracker.update([detection()])
    tracker.update([])
    tracker.update([])
    returned = tracker.update([detection()])

    assert first[0].track_id == 1
    assert returned[0].track_id == 2


def test_tracker_validates_matching_configuration():
    with pytest.raises(ValueError, match="IoU threshold"):
        DetectionTracker(min_iou=1.1)
    with pytest.raises(ValueError, match="missed frames"):
        DetectionTracker(max_missed_frames=-1)

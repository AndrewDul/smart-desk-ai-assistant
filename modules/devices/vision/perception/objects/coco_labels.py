# modules/devices/vision/perception/objects/coco_labels.py
from __future__ import annotations

# COCO-80 class names in YOLOv8/YOLOv11 canonical index order.
# This ordering is the HEF contract for yolov11m_h10.hef and matches
# ultralytics / mmdetection COCO indexing.
COCO_CLASS_NAMES: tuple[str, ...] = (
    "person",          # 0
    "bicycle",         # 1
    "car",             # 2
    "motorcycle",      # 3
    "airplane",        # 4
    "bus",             # 5
    "train",           # 6
    "truck",           # 7
    "boat",            # 8
    "traffic light",   # 9
    "fire hydrant",    # 10
    "stop sign",       # 11
    "parking meter",   # 12
    "bench",           # 13
    "bird",            # 14
    "cat",             # 15
    "dog",             # 16
    "horse",           # 17
    "sheep",           # 18
    "cow",             # 19
    "elephant",        # 20
    "bear",            # 21
    "zebra",           # 22
    "giraffe",         # 23
    "backpack",        # 24
    "umbrella",        # 25
    "handbag",         # 26
    "tie",             # 27
    "suitcase",        # 28
    "frisbee",         # 29
    "skis",            # 30
    "snowboard",       # 31
    "sports ball",     # 32
    "kite",            # 33
    "baseball bat",    # 34
    "baseball glove",  # 35
    "skateboard",      # 36
    "surfboard",       # 37
    "tennis racket",   # 38
    "bottle",          # 39
    "wine glass",      # 40
    "cup",             # 41
    "fork",            # 42
    "knife",           # 43
    "spoon",           # 44
    "bowl",            # 45
    "banana",          # 46
    "apple",           # 47
    "sandwich",        # 48
    "orange",          # 49
    "broccoli",        # 50
    "carrot",          # 51
    "hot dog",         # 52
    "pizza",           # 53
    "donut",           # 54
    "cake",            # 55
    "chair",           # 56
    "couch",           # 57
    "potted plant",    # 58
    "bed",             # 59
    "dining table",    # 60
    "toilet",          # 61
    "tv",              # 62
    "laptop",          # 63
    "mouse",           # 64
    "remote",          # 65
    "keyboard",        # 66
    "cell phone",      # 67
    "microwave",       # 68
    "oven",            # 69
    "toaster",         # 70
    "sink",            # 71
    "refrigerator",    # 72
    "book",            # 73
    "clock",           # 74
    "vase",            # 75
    "scissors",        # 76
    "teddy bear",      # 77
    "hair drier",      # 78
    "toothbrush",      # 79
)


# Desk-relevant class subsets used by behavior interpreters downstream.
# These tuples are intentionally narrow — the less noise in signals,
# the more stable computer_work / phone_usage detection becomes.

COMPUTER_WORK_LABELS: frozenset[str] = frozenset({
    "laptop",
    "tv",
    "mouse",
    "keyboard",
})

PHONE_LABELS: frozenset[str] = frozenset({
    "cell phone",
})

STUDY_LABELS: frozenset[str] = frozenset({
    "book",
})

DESK_SCENE_LABELS: frozenset[str] = frozenset({
    "cup",
    "bottle",
    "wine glass",
    "bowl",
    "chair",
    "potted plant",
    "clock",
    "scissors",
})


def coco_label_for_index(class_index: int) -> str:
    """
    Return the canonical COCO label for a class index.

    Out-of-range indices return a synthetic 'class_<N>' label rather than
    raising — the pipeline should never crash on an unexpected class id.
    """
    if 0 <= class_index < len(COCO_CLASS_NAMES):
        return COCO_CLASS_NAMES[class_index]
    return f"class_{int(class_index)}"


def is_desk_relevant_label(label: str) -> bool:
    """Return True if the COCO label is meaningful for desk behavior signals."""
    normalized = str(label or "").strip().lower()
    if not normalized:
        return False
    return (
        normalized in COMPUTER_WORK_LABELS
        or normalized in PHONE_LABELS
        or normalized in STUDY_LABELS
        or normalized in DESK_SCENE_LABELS
    )
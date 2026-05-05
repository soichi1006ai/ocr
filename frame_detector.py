from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class FrameCandidate:
    bbox: list[int]
    score: float
    horizontal_line_ratio: float
    vertical_line_ratio: float
    intersections: int
    is_table_like: bool


class FrameDetectionError(Exception):
    """Raised when frame detection fails."""



def detect_frame_candidates(image_path: str | Path) -> list[FrameCandidate]:
    path = Path(image_path).expanduser().resolve()
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FrameDetectionError(f"Failed to load image for frame detection: {path}")

    binary = _binarize(image)
    horizontal = _extract_lines(binary, axis="horizontal")
    vertical = _extract_lines(binary, axis="vertical")
    grid = cv2.addWeighted(horizontal, 1.0, vertical, 1.0, 0.0)

    contours, hierarchy = cv2.findContours(grid, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    page_area = image.shape[0] * image.shape[1]
    candidates: list[FrameCandidate] = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < page_area * 0.003:
            continue
        if area > page_area * 0.92:
            continue
        if w < 80 or h < 50:
            continue

        roi_h = horizontal[y : y + h, x : x + w]
        roi_v = vertical[y : y + h, x : x + w]
        roi_grid = grid[y : y + h, x : x + w]
        horizontal_ratio = float(np.count_nonzero(roi_h)) / float(area)
        vertical_ratio = float(np.count_nonzero(roi_v)) / float(area)
        intersections = int(np.count_nonzero(cv2.bitwise_and(roi_h, roi_v)))
        score = horizontal_ratio + vertical_ratio + min(intersections / 5000.0, 1.0)
        is_table_like = (
            horizontal_ratio > 0.008
            and vertical_ratio > 0.003
            and intersections >= 12
        )
        candidates.append(
            FrameCandidate(
                bbox=[int(x), int(y), int(x + w), int(y + h)],
                score=score,
                horizontal_line_ratio=horizontal_ratio,
                vertical_line_ratio=vertical_ratio,
                intersections=intersections,
                is_table_like=is_table_like,
            )
        )

    candidates.sort(key=lambda item: (not item.is_table_like, -item.score, item.bbox[1], item.bbox[0]))
    return _dedupe_candidates(candidates)



def _binarize(image: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(image, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        15,
    )
    return binary



def _extract_lines(binary: np.ndarray, *, axis: str) -> np.ndarray:
    h, w = binary.shape[:2]
    if axis == "horizontal":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // 40), 1))
    else:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, h // 40)))
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    return cv2.dilate(opened, dilate_kernel, iterations=1)



def _dedupe_candidates(candidates: list[FrameCandidate]) -> list[FrameCandidate]:
    kept: list[FrameCandidate] = []
    for candidate in candidates:
        if any(_iou(candidate.bbox, existing.bbox) > 0.85 for existing in kept):
            continue
        kept.append(candidate)
    return kept



def _iou(a: list[int], b: list[int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union else 0.0

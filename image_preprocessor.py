from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np


class ImagePreprocessingError(Exception):
    """Raised when OCR preprocessing fails."""



def preprocess_image_for_ocr(image_path: str | Path) -> Path:
    path = Path(image_path).expanduser().resolve()
    image = cv2.imread(str(path))
    if image is None:
        raise ImagePreprocessingError(f"Failed to load image for preprocessing: {path}")

    processed = _prepare_binary_image(image)

    with tempfile.NamedTemporaryFile(prefix=f"{path.stem}_pre_", suffix=".png", delete=False) as tmp:
        out_path = Path(tmp.name)

    if not cv2.imwrite(str(out_path), processed):
        raise ImagePreprocessingError(f"Failed to write preprocessed image: {out_path}")
    return out_path



def split_image_for_vertical_ocr(image_path: str | Path) -> list[Path]:
    path = Path(image_path).expanduser().resolve()
    image = cv2.imread(str(path))
    if image is None:
        raise ImagePreprocessingError(f"Failed to load image for preprocessing: {path}")

    processed = _prepare_binary_image(image)
    segments = _segment_vertical_columns(processed)
    if len(segments) <= 1:
        with tempfile.NamedTemporaryFile(prefix=f"{path.stem}_pre_", suffix=".png", delete=False) as tmp:
            out_path = Path(tmp.name)
        if not cv2.imwrite(str(out_path), processed):
            raise ImagePreprocessingError(f"Failed to write preprocessed image: {out_path}")
        return [out_path]

    paths: list[Path] = []
    for index, segment in enumerate(segments, start=1):
        with tempfile.NamedTemporaryFile(prefix=f"{path.stem}_col{index:02d}_", suffix=".png", delete=False) as tmp:
            out_path = Path(tmp.name)
        if not cv2.imwrite(str(out_path), segment):
            raise ImagePreprocessingError(f"Failed to write segmented image: {out_path}")
        paths.append(out_path)
    return paths



def _prepare_binary_image(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    height, width = gray.shape[:2]
    scale = 2.0 if max(height, width) < 2000 else (1.5 if max(height, width) < 3500 else 1.0)
    if scale != 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = _deskew(gray)

    # ノイズ除去（歴史的文書のシミ・汚れに対応）
    gray = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)

    # コントラスト強化（CLAHEパラメータを歴史文書向けに調整）
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(16, 16))
    enhanced = clahe.apply(gray)

    # 適応的二値化（印刷ムラに強い）
    binary = cv2.adaptiveThreshold(
        enhanced, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=10,
    )

    # 細線化した文字の補正
    kernel = np.ones((2, 2), np.uint8)
    return cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)



def _segment_vertical_columns(binary: np.ndarray) -> list[np.ndarray]:
    inverted = 255 - binary
    col_density = (inverted > 0).sum(axis=0)
    threshold = max(15, int(binary.shape[0] * 0.015))
    active = col_density > threshold

    spans: list[tuple[int, int]] = []
    start: int | None = None
    for idx, on in enumerate(active):
        if on and start is None:
            start = idx
        elif not on and start is not None:
            if idx - start >= 40:
                spans.append((start, idx))
            start = None
    if start is not None and len(active) - start >= 40:
        spans.append((start, len(active)))

    if len(spans) <= 1:
        return [binary]

    merged: list[tuple[int, int]] = []
    for span in spans:
        if not merged:
            merged.append(span)
            continue
        prev_start, prev_end = merged[-1]
        cur_start, cur_end = span
        if cur_start - prev_end < 25:
            merged[-1] = (prev_start, cur_end)
        else:
            merged.append(span)

    segments: list[np.ndarray] = []
    pad = 12
    # Vertical Japanese typically reads right-to-left, so preserve that order.
    for start, end in reversed(merged):
        left = max(0, start - pad)
        right = min(binary.shape[1], end + pad)
        segments.append(binary[:, left:right])
    return segments



def _deskew(gray: np.ndarray) -> np.ndarray:
    inverted = cv2.bitwise_not(gray)
    coords = cv2.findNonZero(inverted)
    if coords is None or len(coords) < 100:
        return gray

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) < 0.3:
        return gray

    h, w = gray.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        gray,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )

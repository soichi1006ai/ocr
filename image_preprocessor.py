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

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Light upscale helps small scanned glyphs and thin print.
    height, width = gray.shape[:2]
    scale = 1.5 if max(height, width) < 3500 else 1.0
    if scale != 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = _deskew(gray)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    kernel = np.ones((1, 1), np.uint8)
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    with tempfile.NamedTemporaryFile(prefix=f"{path.stem}_pre_", suffix=".png", delete=False) as tmp:
        out_path = Path(tmp.name)

    if not cv2.imwrite(str(out_path), cleaned):
        raise ImagePreprocessingError(f"Failed to write preprocessed image: {out_path}")
    return out_path



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

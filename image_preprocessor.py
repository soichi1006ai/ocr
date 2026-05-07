from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import numpy as np


class ImagePreprocessingError(Exception):
    """Raised when OCR preprocessing fails."""


def preview_deskew(image_path: str | Path, output_path: str | Path | None = None) -> Path:
    """傾き補正後の画像を保存して確認用に返す。"""
    path = Path(image_path).expanduser().resolve()
    image = cv2.imread(str(path))
    if image is None:
        raise ImagePreprocessingError(f"Failed to load image: {path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    corrected = _deskew(gray)

    out = Path(output_path) if output_path else path.parent / f"{path.stem}_deskewed.png"
    cv2.imwrite(str(out), corrected)
    return out



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



def split_spread_pages(
    image_paths: list[Path],
    output_dir: Path,
) -> list[Path]:
    """見開き画像を左右に分割し、それぞれ独立にdeskewして保存する。

    日本語書籍の読み順（右→左）に従い、右ページを先に返す。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []

    for img_path in image_paths:
        bgr = cv2.imread(str(img_path))
        if bgr is None:
            result.append(img_path)
            continue

        h, w = bgr.shape[:2]
        mid = w // 2
        stem = img_path.stem  # e.g. "page_001"

        for side, half in [("R", bgr[:, :mid]), ("L", bgr[:, mid:])]:
            gray = cv2.cvtColor(half, cv2.COLOR_BGR2GRAY)
            angle = _detect_skew_angle(gray)
            corrected = _rotate_image(half, angle)
            out_path = output_dir / f"{stem}_{side}.png"
            cv2.imwrite(str(out_path), corrected)
            result.append(out_path)

    return result


def _detect_skew_angle(gray: np.ndarray) -> float:
    """投影プロファイル法で傾き角度を検出する（±10°）。"""
    h, w = gray.shape[:2]
    scale = min(1.0, 1000.0 / max(h, w))
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1.0 else gray

    _, binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    sh, sw = small.shape[:2]
    sc = (sw // 2, sh // 2)

    best_angle = 0.0
    best_score = -1.0

    # 粗探索 ±10° (1°刻み)
    for deg in range(-10, 11):
        mat = cv2.getRotationMatrix2D(sc, float(deg), 1.0)
        rot = cv2.warpAffine(binary, mat, (sw, sh), flags=cv2.INTER_NEAREST, borderValue=0)
        score = float(np.var(rot.sum(axis=1)))
        if score > best_score:
            best_score = score
            best_angle = float(deg)

    # 精細探索 ±1° (0.1°刻み)
    fine_best = best_angle
    fine_score = best_score
    for frac in range(-10, 11):
        angle = best_angle + frac * 0.1
        mat = cv2.getRotationMatrix2D(sc, angle, 1.0)
        rot = cv2.warpAffine(binary, mat, (sw, sh), flags=cv2.INTER_NEAREST, borderValue=0)
        score = float(np.var(rot.sum(axis=1)))
        if score > fine_score:
            fine_score = score
            fine_best = angle

    return fine_best


def _rotate_image(image: np.ndarray, angle: float) -> np.ndarray:
    """グレースケール・カラー両対応の回転。0.2°未満はスキップ。"""
    if abs(angle) < 0.2:
        return image
    h, w = image.shape[:2]
    mat = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(image, mat, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _deskew(gray: np.ndarray) -> np.ndarray:
    return _rotate_image(gray, _detect_skew_angle(gray))

"""
pipeline/splitter.py — 見開きスキャン自動検出・左右分割

アスペクト比（横幅/縦幅 > 1.3）で見開きを判定し、中央の綴じ目位置を
縦方向ヒストグラム解析で精密検出して左右に分割する。
- 日本語縦書きの読み順：右ページ → 左ページの順で返す
- 出力ファイル名: `{stem}_R.png`, `{stem}_L.png`
"""
from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

SPREAD_ASPECT_RATIO = 1.3  # 横/縦がこれを超えると見開きと判定


def is_spread_image(image_path: Path) -> bool:
    """
    アスペクト比で見開きスキャンかどうかを判定する。
    横/縦 > SPREAD_ASPECT_RATIO の場合に True を返す。
    """
    with Image.open(image_path) as img:
        w, h = img.size
    return (w / h) > SPREAD_ASPECT_RATIO


def split_spread(
    image_path: Path,
    output_dir: Path,
    *,
    deskew: bool = True,
) -> tuple[Path, Path]:
    """
    見開き画像を左右に分割して保存する。

    Parameters
    ----------
    image_path:
        入力画像（見開きスキャン）
    output_dir:
        分割後の画像を保存するディレクトリ
    deskew:
        各ページを個別に歪み補正する（既存 image_preprocessor を使用）

    Returns
    -------
    (right_path, left_path)
        日本語縦書きの読み順（右 → 左）で返す。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    split_x = _detect_spine(image_path)
    right_path, left_path = _save_halves(image_path, split_x, output_dir, deskew=deskew)

    logger.info(
        "split_spread: %s → R=%s L=%s (split_x=%d)",
        image_path.name, right_path.name, left_path.name, split_x,
    )
    return right_path, left_path


def split_spread_pages(
    image_paths: list[Path],
    output_dir: Path,
    *,
    deskew: bool = True,
    skip_non_spread: bool = True,
) -> list[Path]:
    """
    複数画像を処理して分割結果をフラットなリストで返す。

    見開きでないページは skip_non_spread=True ならそのまま通す。
    返却順序: 各ページの (R, L) を順番に並べたリスト。
    """
    result: list[Path] = []
    for img_path in image_paths:
        if skip_non_spread and not is_spread_image(img_path):
            result.append(img_path)
        else:
            r, l = split_spread(img_path, output_dir, deskew=deskew)
            result.extend([r, l])
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_spine(image_path: Path) -> int:
    """
    縦方向の輝度ヒストグラムから綴じ目（最も暗い縦列）の x 座標を検出する。
    中央 20% の範囲内で探索し、画像の幅方向の中心を返す。
    """
    try:
        import numpy as np
        import cv2

        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"Cannot read image: {image_path}")

        h, w = img.shape
        search_start = int(w * 0.4)
        search_end = int(w * 0.6)
        roi = img[:, search_start:search_end]

        col_mean = roi.mean(axis=0)
        local_min = int(np.argmin(col_mean))
        return search_start + local_min

    except Exception as exc:
        logger.warning("spine detection failed (%s), using center", exc)
        with Image.open(image_path) as img:
            return img.width // 2


def _save_halves(
    image_path: Path,
    split_x: int,
    output_dir: Path,
    *,
    deskew: bool,
) -> tuple[Path, Path]:
    stem = image_path.stem

    with Image.open(image_path) as img:
        w, h = img.size
        right_img = img.crop((0, 0, split_x, h))
        left_img  = img.crop((split_x, 0, w, h))

    right_path = output_dir / f"{stem}_R.png"
    left_path  = output_dir / f"{stem}_L.png"

    right_img.save(right_path)
    left_img.save(left_path)

    if deskew:
        right_path = _deskew_file(right_path)
        left_path  = _deskew_file(left_path)

    return right_path, left_path


def _deskew_file(image_path: Path) -> Path:
    """既存の image_preprocessor の deskew ロジックを適用する"""
    try:
        import cv2
        import numpy as np
        from image_preprocessor import _detect_skew_angle, _rotate_image

        bgr = cv2.imread(str(image_path))
        if bgr is None:
            return image_path
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        angle = _detect_skew_angle(gray)
        if abs(angle) < 0.2:
            return image_path
        corrected = _rotate_image(bgr, angle)
        cv2.imwrite(str(image_path), corrected)
    except Exception as exc:
        logger.warning("deskew failed for %s: %s", image_path.name, exc)
    return image_path

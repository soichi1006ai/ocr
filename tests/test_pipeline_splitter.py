"""Tests for pipeline/splitter.py"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.splitter import (
    is_spread_image,
    split_spread,
    split_spread_pages,
    SPREAD_ASPECT_RATIO,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _create_image(path: Path, width: int, height: int, color=(200, 200, 200)) -> Path:
    img = Image.new("RGB", (width, height), color=color)
    img.save(path)
    return path


@pytest.fixture
def spread_image(tmp_path) -> Path:
    return _create_image(tmp_path / "spread.png", 1400, 800)  # aspect 1.75 > 1.3


@pytest.fixture
def portrait_image(tmp_path) -> Path:
    return _create_image(tmp_path / "portrait.png", 700, 1000)  # aspect 0.7 < 1.3


@pytest.fixture
def square_ish_image(tmp_path) -> Path:
    return _create_image(tmp_path / "square.png", 900, 800)  # aspect 1.125 < 1.3


# ---------------------------------------------------------------------------
# is_spread_image
# ---------------------------------------------------------------------------

def test_is_spread_wide_image(spread_image):
    assert is_spread_image(spread_image) is True


def test_is_spread_portrait_image(portrait_image):
    assert is_spread_image(portrait_image) is False


def test_is_spread_square_ish(square_ish_image):
    assert is_spread_image(square_ish_image) is False


def test_spread_threshold():
    assert SPREAD_ASPECT_RATIO == 1.3


# ---------------------------------------------------------------------------
# split_spread
# ---------------------------------------------------------------------------

def test_split_spread_creates_two_files(spread_image, tmp_path):
    out_dir = tmp_path / "out"
    right, left = split_spread(spread_image, out_dir, deskew=False)
    assert right.exists()
    assert left.exists()


def test_split_spread_filename_convention(spread_image, tmp_path):
    out_dir = tmp_path / "out"
    right, left = split_spread(spread_image, out_dir, deskew=False)
    assert right.name.endswith("_R.png")
    assert left.name.endswith("_L.png")


def test_split_spread_output_dir_created(spread_image, tmp_path):
    out_dir = tmp_path / "new_dir"
    assert not out_dir.exists()
    split_spread(spread_image, out_dir, deskew=False)
    assert out_dir.exists()


def test_split_spread_right_is_left_half_of_image(spread_image, tmp_path):
    out_dir = tmp_path / "out"
    right, left = split_spread(spread_image, out_dir, deskew=False)
    with Image.open(right) as r, Image.open(left) as l, Image.open(spread_image) as orig:
        assert r.width + l.width == orig.width or abs(r.width + l.width - orig.width) <= 2
        assert r.height == orig.height


def test_split_spread_returns_right_before_left(spread_image, tmp_path):
    out_dir = tmp_path / "out"
    right, left = split_spread(spread_image, out_dir, deskew=False)
    assert "_R" in right.name
    assert "_L" in left.name


# ---------------------------------------------------------------------------
# split_spread_pages
# ---------------------------------------------------------------------------

def test_split_spread_pages_non_spread_passes_through(portrait_image, tmp_path):
    out_dir = tmp_path / "out"
    result = split_spread_pages([portrait_image], out_dir, deskew=False, skip_non_spread=True)
    assert result == [portrait_image]


def test_split_spread_pages_spread_splits(spread_image, tmp_path):
    out_dir = tmp_path / "out"
    result = split_spread_pages([spread_image], out_dir, deskew=False)
    assert len(result) == 2
    assert any("_R" in p.name for p in result)
    assert any("_L" in p.name for p in result)


def test_split_spread_pages_mixed(spread_image, portrait_image, tmp_path):
    out_dir = tmp_path / "out"
    result = split_spread_pages(
        [portrait_image, spread_image, portrait_image],
        out_dir, deskew=False
    )
    assert len(result) == 4  # 1 + 2 + 1
    assert result[0] == portrait_image
    assert result[-1] == portrait_image


def test_split_spread_pages_force_all_split(spread_image, portrait_image, tmp_path):
    out_dir = tmp_path / "out"
    result = split_spread_pages(
        [portrait_image], out_dir, deskew=False, skip_non_spread=False
    )
    assert len(result) == 2

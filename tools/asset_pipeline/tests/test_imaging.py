"""Unit tests for resize helpers."""

from PIL import Image

from asset_pipeline.imaging import (
    FitPolicy,
    ResampleMode,
    majority_resize_to_frame,
    resize_to_frame,
    resize_to_frame_with_mode,
)


def test_resize_contain_output_size() -> None:
    src = Image.new("RGB", (100, 50), color="red")
    out = resize_to_frame(src, 32, 48, FitPolicy.contain)
    assert out.size == (32, 48)
    assert out.mode == "RGBA"


def test_resize_cover_output_size() -> None:
    src = Image.new("RGB", (100, 50), color="blue")
    out = resize_to_frame(src, 32, 48, FitPolicy.cover)
    assert out.size == (32, 48)


def test_resize_stretch_output_size() -> None:
    src = Image.new("RGB", (10, 20), color="green")
    out = resize_to_frame(src, 32, 48, FitPolicy.stretch)
    assert out.size == (32, 48)


def test_majority_stretch_picks_mode_color() -> None:
    img = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
    img.putpixel((0, 0), (255, 0, 0, 255))
    img.putpixel((1, 0), (255, 0, 0, 255))
    img.putpixel((0, 1), (255, 0, 0, 255))
    img.putpixel((1, 1), (255, 255, 255, 255))
    out = majority_resize_to_frame(img, 1, 1, FitPolicy.stretch)
    assert out.getpixel((0, 0)) == (255, 0, 0, 255)


def test_resize_to_frame_with_mode_dispatch() -> None:
    src = Image.new("RGBA", (4, 4), (128, 128, 128, 255))
    a = resize_to_frame_with_mode(src, 2, 2, FitPolicy.stretch, ResampleMode.smooth)
    b = resize_to_frame_with_mode(src, 2, 2, FitPolicy.stretch, ResampleMode.majority)
    assert a.size == (2, 2) and b.size == (2, 2)

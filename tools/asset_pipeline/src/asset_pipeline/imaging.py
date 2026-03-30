"""Resize helpers: contain (letterbox), cover (center crop), stretch."""

from __future__ import annotations

import math
from collections import Counter
from enum import Enum

from PIL import Image


class FitPolicy(str, Enum):
    """How to map a source rectangle into a fixed output size."""

    contain = "contain"
    """Scale uniformly so the whole source fits; pad with transparent pixels."""

    cover = "cover"
    """Scale uniformly to fill the output; crop overflow from the center."""

    stretch = "stretch"
    """Stretch non-uniformly to exact output size (may distort)."""


class ResampleMode(str, Enum):
    """How to map source pixels into each output pixel."""

    smooth = "smooth"
    """Lanczos (or equivalent) interpolation via Pillow."""

    majority = "majority"
    """Per output pixel, pick the most frequent source color in the mapped region (box mode)."""


def _intervals_overlap_1d(a0: float, a1: float, b0: float, b1: float) -> bool:
    return max(a0, b0) < min(a1, b1)


def _mode_rgba(samples: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    if not samples:
        return (0, 0, 0, 0)
    counts = Counter(samples)
    # Tie-break: higher count, then lexicographic RGBA (stable, deterministic)
    r, g, b, a = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return (r, g, b, a)


def _pixels_overlapping_region(
    img: Image.Image,
    u0: float,
    u1: float,
    v0: float,
    v1: float,
) -> list[tuple[int, int, int, int]]:
    """Collect RGBA from unit squares [ix,ix+1)×[iy,iy+1) that overlap (u0,u1)×(v0,v1).

    Only scans the bounding box of possibly overlapping indices (not the full image),
    so ``majority`` stays roughly O(output_pixels × local_overlap), not O(output × image).
    """
    iw, ih = img.size
    if u0 >= u1 or v0 >= v1:
        return []

    ix0 = max(0, int(math.floor(u0)))
    ix1 = min(iw, int(math.ceil(u1)))
    iy0 = max(0, int(math.floor(v0)))
    iy1 = min(ih, int(math.ceil(v1)))

    out: list[tuple[int, int, int, int]] = []
    for iy in range(iy0, iy1):
        for ix in range(ix0, ix1):
            if _intervals_overlap_1d(ix, ix + 1, u0, u1) and _intervals_overlap_1d(
                iy, iy + 1, v0, v1
            ):
                out.append(img.getpixel((ix, iy)))
    return out


def majority_resize_to_frame(
    image: Image.Image,
    out_w: int,
    out_h: int,
    fit: FitPolicy,
) -> Image.Image:
    """Map each output pixel to a region in source space (per ``fit``); output is the mode color."""
    img = image.convert("RGBA")
    iw, ih = img.size
    if iw <= 0 or ih <= 0:
        return Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))

    out = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))

    if fit == FitPolicy.stretch:
        for oy in range(out_h):
            for ox in range(out_w):
                u0 = ox * iw / out_w
                u1 = (ox + 1) * iw / out_w
                v0 = oy * ih / out_h
                v1 = (oy + 1) * ih / out_h
                samples = _pixels_overlapping_region(img, u0, u1, v0, v1)
                out.putpixel((ox, oy), _mode_rgba(samples))
        return out

    if fit == FitPolicy.contain:
        scale = min(out_w / iw, out_h / ih)
        sw = iw * scale
        sh = ih * scale
        ox0 = (out_w - sw) / 2.0
        oy0 = (out_h - sh) / 2.0
        for oy in range(out_h):
            for ox in range(out_w):
                x0 = max(float(ox), ox0)
                x1 = min(float(ox + 1), ox0 + sw)
                y0 = max(float(oy), oy0)
                y1 = min(float(oy + 1), oy0 + sh)
                if x0 >= x1 or y0 >= y1:
                    continue
                u0 = (x0 - ox0) / scale
                u1 = (x1 - ox0) / scale
                v0 = (y0 - oy0) / scale
                v1 = (y1 - oy0) / scale
                samples = _pixels_overlapping_region(img, u0, u1, v0, v1)
                out.putpixel((ox, oy), _mode_rgba(samples))
        return out

    # cover
    scale = max(out_w / iw, out_h / ih)
    sw = iw * scale
    sh = ih * scale
    crop_x = (sw - out_w) / 2.0
    crop_y = (sh - out_h) / 2.0
    for oy in range(out_h):
        for ox in range(out_w):
            sx0 = ox + crop_x
            sx1 = ox + 1 + crop_x
            sy0 = oy + crop_y
            sy1 = oy + 1 + crop_y
            u0 = sx0 / scale
            u1 = sx1 / scale
            v0 = sy0 / scale
            v1 = sy1 / scale
            u0i = max(0.0, u0)
            u1i = min(float(iw), u1)
            v0i = max(0.0, v0)
            v1i = min(float(ih), v1)
            if u0i >= u1i or v0i >= v1i:
                continue
            samples = _pixels_overlapping_region(img, u0i, u1i, v0i, v1i)
            out.putpixel((ox, oy), _mode_rgba(samples))
    return out


def resize_to_frame(
    image: Image.Image,
    out_w: int,
    out_h: int,
    fit: FitPolicy,
) -> Image.Image:
    """Resize ``image`` to ``(out_w, out_h)`` using ``fit`` policy. Output is RGBA."""
    img = image.convert("RGBA")
    iw, ih = img.size
    if iw <= 0 or ih <= 0:
        return Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))

    if fit == FitPolicy.stretch:
        return img.resize((out_w, out_h), Image.Resampling.LANCZOS)

    if fit == FitPolicy.contain:
        scale = min(out_w / iw, out_h / ih)
        nw = max(1, int(round(iw * scale)))
        nh = max(1, int(round(ih * scale)))
        resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
        ox = (out_w - nw) // 2
        oy = (out_h - nh) // 2
        canvas.paste(resized, (ox, oy), resized)
        return canvas

    # cover
    scale = max(out_w / iw, out_h / ih)
    nw = max(1, int(round(iw * scale)))
    nh = max(1, int(round(ih * scale)))
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - out_w) // 2
    top = (nh - out_h) // 2
    return resized.crop((left, top, left + out_w, top + out_h))


def resize_to_frame_with_mode(
    image: Image.Image,
    out_w: int,
    out_h: int,
    fit: FitPolicy,
    resample: ResampleMode,
) -> Image.Image:
    """Dispatch to Lanczos path or majority-vote path."""
    if resample == ResampleMode.majority:
        return majority_resize_to_frame(image, out_w, out_h, fit)
    return resize_to_frame(image, out_w, out_h, fit)

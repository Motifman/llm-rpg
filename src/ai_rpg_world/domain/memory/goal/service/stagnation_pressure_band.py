"""停滞感カウンタ → 表出バンドへの写像 (P-U2)。

``StagnationPressureRepository`` が保持する生カウンタを、後続 (P-U3/P-U4) が
本人 / 他者への表出に使う 3 段階のバンドへ変換する純関数。境界値は本モジュールの
定数に集約し、表出側が個別に閾値を持たないようにする。
"""

from __future__ import annotations

STAGNATION_PRESSURE_BAND_NONE = "none"
"""停滞感なし (カウンタ 0)。"""

STAGNATION_PRESSURE_BAND_LIGHT = "light"
"""軽い停滞感 (カウンタ 1〜2)。"""

STAGNATION_PRESSURE_BAND_STRONG = "strong"
"""強い停滞感 (カウンタ 3 以上)。"""

# バンドの境界値。「3 件目の stalled/misaligned で強い停滞感に切り替わる」の
# 1 箇所 SSOT。
STAGNATION_PRESSURE_STRONG_THRESHOLD = 3


def resolve_stagnation_pressure_band(count: int) -> str:
    """停滞感カウンタ ``count`` から表出バンドを決める純関数。

    - ``count == 0`` → ``STAGNATION_PRESSURE_BAND_NONE``
    - ``0 < count < STAGNATION_PRESSURE_STRONG_THRESHOLD`` →
      ``STAGNATION_PRESSURE_BAND_LIGHT``
    - ``count >= STAGNATION_PRESSURE_STRONG_THRESHOLD`` →
      ``STAGNATION_PRESSURE_BAND_STRONG``

    負の ``count`` は呼び出し側の不変条件違反として ``ValueError`` で弾く。
    """
    if not isinstance(count, int) or isinstance(count, bool):
        raise TypeError("count must be int")
    if count < 0:
        raise ValueError("count must be 0 or greater")
    if count == 0:
        return STAGNATION_PRESSURE_BAND_NONE
    if count < STAGNATION_PRESSURE_STRONG_THRESHOLD:
        return STAGNATION_PRESSURE_BAND_LIGHT
    return STAGNATION_PRESSURE_BAND_STRONG


__all__ = [
    "STAGNATION_PRESSURE_BAND_NONE",
    "STAGNATION_PRESSURE_BAND_LIGHT",
    "STAGNATION_PRESSURE_BAND_STRONG",
    "STAGNATION_PRESSURE_STRONG_THRESHOLD",
    "resolve_stagnation_pressure_band",
]

"""現在時刻の派生スナップショット（値オブジェクト）。

DayNightCycleDef.time_of_day_at(tick) で生成される、
ある tick における時刻の派生表現。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimeOfDay:
    """ある tick における時刻スナップショット。

    Attributes:
        ratio: 1日内の進行比率 [0.0, 1.0)。
        phase_name: 該当フェーズの識別子。
        display_text: フェーズの表示文字列。
        ambient_light: 屋外環境光 [0.0, 1.0]。
        is_dark: 屋外暗闇判定 bool。
    """

    ratio: float
    phase_name: str
    display_text: str
    ambient_light: float
    is_dark: bool

    def __post_init__(self) -> None:
        if not 0.0 <= self.ratio < 1.0:
            raise ValueError(f"TimeOfDay.ratio must be in [0.0, 1.0): {self.ratio}")
        if not 0.0 <= self.ambient_light <= 1.0:
            raise ValueError(
                f"TimeOfDay.ambient_light must be in [0.0, 1.0]: {self.ambient_light}"
            )

"""昼夜サイクルのフェーズ定義（値オブジェクト）。

シナリオデータが任意の数・任意の名前のフェーズを宣言できるよう、
フェーズ名は文字列で受け取る（enum 化しない）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DayNightPhaseDef:
    """昼夜サイクルにおける1フェーズの定義。

    Attributes:
        name: フェーズ識別子（"dawn", "noon", "midnight" など。シナリオ自由命名）。
            イベントの from_phase / to_phase に載るため一意であること。
        start_ratio: このフェーズが開始する1日内の比率 [0.0, 1.0)。
            次のフェーズの start_ratio までこのフェーズが継続する。
        display_text: プロンプト等に表示する文字列（"夜明け" など）。
        ambient_light: フェーズ中の屋外環境光 [0.0, 1.0]。
        is_dark: 屋外スポットの暗闇判定に使う bool。
    """

    name: str
    start_ratio: float
    display_text: str
    ambient_light: float
    is_dark: bool

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("DayNightPhaseDef.name must not be empty")
        if not 0.0 <= self.start_ratio < 1.0:
            raise ValueError(
                f"DayNightPhaseDef.start_ratio must be in [0.0, 1.0): {self.start_ratio}"
            )
        if not 0.0 <= self.ambient_light <= 1.0:
            raise ValueError(
                f"DayNightPhaseDef.ambient_light must be in [0.0, 1.0]: {self.ambient_light}"
            )

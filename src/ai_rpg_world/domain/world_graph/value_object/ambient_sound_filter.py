"""環境音の発火条件フィルタ（値オブジェクト）。

各 AmbientSoundDef が「いつ/どこで鳴るか」を表す。
None の項目は「絞り込まない（無条件）」を意味する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    AmbientSoundFilterValidationException,
)


@dataclass(frozen=True)
class AmbientSoundFilter:
    """環境音発火条件のフィルタ。

    Attributes:
        phases: 許可フェーズ名集合。None なら全フェーズ。
        weather_types: 許可天候タイプ名集合（WeatherTypeEnum.value）。
            None なら全天候。
        indoor_only: True なら屋内（is_outdoor=False）でのみ発火。
        outdoor_only: True なら屋外でのみ発火。
            indoor_only と outdoor_only が両方 True なら誰でも鳴らない（仕様上の不正）。
    """

    phases: Optional[FrozenSet[str]] = None
    weather_types: Optional[FrozenSet[str]] = None
    indoor_only: bool = False
    outdoor_only: bool = False

    def __post_init__(self) -> None:
        if self.indoor_only and self.outdoor_only:
            raise AmbientSoundFilterValidationException(
                "AmbientSoundFilter cannot have both indoor_only and outdoor_only set"
            )

    def matches_phase(self, phase_name: Optional[str]) -> bool:
        if self.phases is None:
            return True
        if phase_name is None:
            return False
        return phase_name in self.phases

    def matches_weather(self, weather_type_value: Optional[str]) -> bool:
        if self.weather_types is None:
            return True
        if weather_type_value is None:
            return False
        return weather_type_value in self.weather_types

    def matches_outdoor(self, is_outdoor: bool) -> bool:
        if self.indoor_only and is_outdoor:
            return False
        if self.outdoor_only and not is_outdoor:
            return False
        return True

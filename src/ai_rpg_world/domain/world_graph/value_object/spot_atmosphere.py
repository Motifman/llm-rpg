from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.sound_intensity_enum import (
    SoundIntensityEnum,
)
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum


@dataclass(frozen=True)
class SpotAtmosphere:
    lighting: LightingEnum
    sound_ambient: Optional[str] = None
    temperature: TemperatureEnum = TemperatureEnum.NORMAL
    smell: Optional[str] = None
    # 脱出ゲーム拡張: 環境ハザード
    hazard_level: int = 0
    hazard_description: Optional[str] = None
    # Phase 5: spot の環境音の強さ。default SILENT で「音は無視できる」
    # 後方互換挙動。`sound_ambient` (description) と組み合わせて使う:
    # - sound_intensity が SILENT 以外なら「音がする」観測が発火
    # - sound_ambient (Optional[str]) は人間向けの説明 (例: 「川のせせらぎ」)
    sound_intensity: SoundIntensityEnum = SoundIntensityEnum.SILENT

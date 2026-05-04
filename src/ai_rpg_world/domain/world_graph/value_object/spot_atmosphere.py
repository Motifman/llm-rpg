from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
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

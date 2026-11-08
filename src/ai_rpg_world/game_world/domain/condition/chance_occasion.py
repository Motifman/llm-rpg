from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.effect.effect_path import EffectPath
from ai_rpg_world.game_world.domain.value_object import WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger


@final
@dataclass(frozen=True)
class ChanceOccasion:
    trigger: Trigger
    tick: WorldTick
    position: ConditionPath | EffectPath

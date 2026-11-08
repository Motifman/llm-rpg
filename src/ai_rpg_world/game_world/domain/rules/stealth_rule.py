from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.exception.rules_exception import MissingSightQualityException
from ai_rpg_world.game_world.domain.lighting.sight_quality import SeesClearly, SeesNothing, SeesShapes, SightQuality
from ai_rpg_world.game_world.domain.value_object import Multiplier, Probability

_SIGHT_QUALITIES: tuple[SightQuality, ...] = (SeesClearly(), SeesShapes(), SeesNothing())


def _complete_chances(field: str, chances: Mapping[SightQuality, Probability]) -> Mapping[SightQuality, Probability]:
    missing = [type(sight).__name__ for sight in _SIGHT_QUALITIES if sight not in chances]
    if missing:
        raise MissingSightQualityException(f"StealthRule.{field} lacks {missing}")
    return MappingProxyType(dict(chances))


@final
@dataclass(frozen=True)
class StealthRule:
    notice_by_bystander: Mapping[SightQuality, Probability]
    notice_by_target: Mapping[SightQuality, Probability]
    attentive_bonus: Probability
    duration_multiplier: Multiplier

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "notice_by_bystander", _complete_chances("notice_by_bystander", self.notice_by_bystander)
        )
        object.__setattr__(self, "notice_by_target", _complete_chances("notice_by_target", self.notice_by_target))

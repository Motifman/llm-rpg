from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation
from ai_rpg_world.game_world.domain.exception.rules_exception import (
    ActionDurationNotApplicableException,
    MissingActionDurationException,
)
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueRule
from ai_rpg_world.game_world.domain.rules.hunger_rule import HungerRule
from ai_rpg_world.game_world.domain.rules.stealth_rule import StealthRule
from ai_rpg_world.game_world.domain.rules.tend_rule import NoTending, TendRule
from ai_rpg_world.game_world.domain.sound.hearing_values import HearingValues
from ai_rpg_world.game_world.domain.value_object import Capacity, HitPoints, Ticks

# 移動は通る通路の時間で決まり、話すことと待つことは行っているあいだを作らない
_KINDS_WITHOUT_DEFAULT_DURATION = frozenset(
    {ActionKind.SPEAK, ActionKind.WAIT, ActionKind.TRAVEL, ActionKind.ATTACK_MONSTER}
)
_KINDS_WITH_DEFAULT_DURATION = frozenset(ActionKind) - _KINDS_WITHOUT_DEFAULT_DURATION


@final
@dataclass(frozen=True)
class WorldRules:
    tend: TendRule | NoTending
    fatigue: FatigueRule
    hunger: HungerRule
    death: DeathRule
    departed_persons_act: bool
    name_tags: bool
    hearing: HearingValues
    stealth: StealthRule
    action_durations: Mapping[ActionKind, Ticks]
    person_max_hp: HitPoints
    pack_capacity: Capacity

    def __post_init__(self) -> None:
        missing = sorted(kind.name for kind in _KINDS_WITH_DEFAULT_DURATION - self.action_durations.keys())
        if missing:
            raise MissingActionDurationException(f"WorldRules.action_durations lacks {missing}")
        not_applicable = sorted(kind.name for kind in self.action_durations.keys() & _KINDS_WITHOUT_DEFAULT_DURATION)
        if not_applicable:
            raise ActionDurationNotApplicableException(
                f"WorldRules.action_durations must not declare {not_applicable}, which take no default duration"
            )
        object.__setattr__(self, "action_durations", MappingProxyType(dict(self.action_durations)))

    def allows_tending(self) -> bool:
        return isinstance(self.tend, TendRule)

    def design_flaws(self, at: DesignLocation) -> list[DesignFlaw]:
        if self.allows_tending() and self.death.grace == Ticks(0):
            return [DesignFlaw(at, "a world with tending needs a grace above 0, or no one can be tended before dying")]
        return []

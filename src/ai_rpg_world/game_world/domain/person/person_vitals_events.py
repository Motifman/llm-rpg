from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.eventing.domain_event import DomainEvent
from ai_rpg_world.game_world.domain.person.life_state import FallCause
from ai_rpg_world.game_world.domain.person.status_effect import NoPreviousStatusEffect, StatusEffect
from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueLevel
from ai_rpg_world.game_world.domain.rules.hunger_rule import HungerLevel
from ai_rpg_world.game_world.domain.value_object import Damage, HitPoints, PersonId, WorldTick


@dataclass(frozen=True, kw_only=True)
class PersonVitalsEvent(DomainEvent):
    person: PersonId


@dataclass(frozen=True, kw_only=True)
class PersonDamagedEvent(PersonVitalsEvent):
    amount: Damage
    hp_before: HitPoints
    hp_after: HitPoints
    cause: FallCause


@dataclass(frozen=True, kw_only=True)
class PersonFellEvent(PersonVitalsEvent):
    fell_at: WorldTick
    cause: FallCause


@dataclass(frozen=True, kw_only=True)
class PersonDiedEvent(PersonVitalsEvent):
    died_at: WorldTick


@dataclass(frozen=True, kw_only=True)
class PersonHealedEvent(PersonVitalsEvent):
    hp_before: HitPoints
    hp_after: HitPoints


@dataclass(frozen=True, kw_only=True)
class PersonRevivedEvent(PersonVitalsEvent):
    revived_at: WorldTick
    hp_after: HitPoints


@dataclass(frozen=True, kw_only=True)
class StatusEffectAddedEvent(PersonVitalsEvent):
    effect: StatusEffect
    replaced: StatusEffect | NoPreviousStatusEffect


@dataclass(frozen=True, kw_only=True)
class StatusEffectExpiredEvent(PersonVitalsEvent):
    effect: StatusEffect


@dataclass(frozen=True, kw_only=True)
class HungerLevelChangedEvent(PersonVitalsEvent):
    level_before: HungerLevel
    level_after: HungerLevel


@dataclass(frozen=True, kw_only=True)
class FatigueLevelChangedEvent(PersonVitalsEvent):
    level_before: FatigueLevel
    level_after: FatigueLevel


@final
@dataclass(frozen=True)
class NoPreviousAction:
    pass


@dataclass(frozen=True, kw_only=True)
class PersonBecameBusyEvent(PersonVitalsEvent):
    until: WorldTick
    previous_until: WorldTick | NoPreviousAction

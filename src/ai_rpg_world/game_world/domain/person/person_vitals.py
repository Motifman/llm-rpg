from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING, Any, final

from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.eventing.aggregate_root import AggregateRoot
from ai_rpg_world.game_world.domain.exception.game_world_exception import RepeatedMementoKeyException
from ai_rpg_world.game_world.domain.exception.person_exception import (
    HitPointsDoNotMatchLifeStateException,
    PersonNotAliveException,
    PersonNotDownException,
    PersonStartsFallenException,
    StatusEffectKindRepeatedException,
)
from ai_rpg_world.game_world.domain.person.life_state import (
    Alive,
    Dead,
    Down,
    FallCause,
    LifeState,
    Starvation,
    StruckByPerson,
)
from ai_rpg_world.game_world.domain.person.person_vitals_events import (
    FatigueLevelChangedEvent,
    HungerLevelChangedEvent,
    NoPreviousAction,
    PersonBecameBusyEvent,
    PersonDamagedEvent,
    PersonDiedEvent,
    PersonFellEvent,
    PersonHealedEvent,
    PersonRevivedEvent,
    PersonVitalsEvent,
    StatusEffectAddedEvent,
    StatusEffectExpiredEvent,
)
from ai_rpg_world.game_world.domain.person.status_effect import (
    NoPreviousStatusEffect,
    StatusEffect,
    StatusEffectType,
)
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.rules.fatigue_rule import FatigueRule
from ai_rpg_world.game_world.domain.rules.hunger_rule import HungerRule
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    FatigueAmount,
    HealAmount,
    HitPoints,
    HungerAmount,
    PersonId,
    Rate,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts.occupant import DepartedPerson, Occupant, PersonBody

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True)
class NotBusy:
    pass


@final
@dataclass(frozen=True)
class PersonVitalsMemento:
    person: PersonId
    hp: HitPoints
    life_state: LifeState
    hunger: HungerAmount
    fatigue: FatigueAmount
    status_effects: frozenset[StatusEffect]
    busy_until: WorldTick | NotBusy

    def __post_init__(self) -> None:
        kinds = [effect.kind for effect in self.status_effects]
        if len(set(kinds)) != len(kinds):
            raise RepeatedMementoKeyException(f"{self.person.value} has one kind of status effect more than once")


class PersonVitals(AggregateRoot[PersonVitalsEvent]):
    def __init__(
        self,
        person: PersonId,
        hp: HitPoints,
        life_state: LifeState,
        hunger: HungerAmount,
        fatigue: FatigueAmount,
        status_effects: frozenset[StatusEffect],
        busy_until: WorldTick | NotBusy,
    ) -> None:
        super().__init__()
        has_hit_points = hp.current > 0
        if has_hit_points != isinstance(life_state, Alive):
            raise HitPointsDoNotMatchLifeStateException(
                f"{person.value} cannot have {hp.current} hit points while {life_state}"
            )
        effects = {effect.kind: effect for effect in status_effects}
        if len(effects) != len(status_effects):
            raise StatusEffectKindRepeatedException(f"{person.value} has one kind of status effect more than once")
        self._person = person
        self._hp = hp
        self._life_state = life_state
        self._hunger = hunger
        self._fatigue = fatigue
        self._status_effects = effects
        self._busy_until = busy_until

    @classmethod
    def start(cls, person: PersonId, hp: HitPoints) -> PersonVitals:
        if hp.current == 0:
            raise PersonStartsFallenException(f"{person.value} cannot start with 0 hit points")
        return cls(person, hp, Alive(), HungerAmount(0), FatigueAmount(0), frozenset(), NotBusy())

    @classmethod
    def from_memento(cls, memento: PersonVitalsMemento, design: WorldDesign) -> PersonVitals:
        design.nouns.character_of(memento.person)
        if isinstance(memento.life_state, Down) and isinstance(memento.life_state.cause, StruckByPerson):
            design.nouns.character_of(memento.life_state.cause.person)
        return cls(
            memento.person,
            memento.hp,
            memento.life_state,
            memento.hunger,
            memento.fatigue,
            memento.status_effects,
            memento.busy_until,
        )

    def memento(self) -> PersonVitalsMemento:
        return PersonVitalsMemento(
            person=self._person,
            hp=self._hp,
            life_state=self._life_state,
            hunger=self._hunger,
            fatigue=self._fatigue,
            status_effects=frozenset(self._status_effects.values()),
            busy_until=self._busy_until,
        )

    @property
    def person(self) -> PersonId:
        return self._person

    def take_damage(self, amount: Damage, now: WorldTick, cause: FallCause) -> None:
        self._require_alive("take damage")
        before = self._hp
        self._hp = before.damaged_by(amount)
        self._add(PersonDamagedEvent, amount=amount, hp_before=before, hp_after=self._hp, cause=cause)
        if self._hp.current == 0:
            self._life_state = Down(fell_at=now, cause=cause)
            self._add(PersonFellEvent, fell_at=now, cause=cause)

    def heal(self, amount: HealAmount) -> None:
        self._require_alive("be healed")
        before = self._hp
        self._hp = before.healed_by(amount)
        if self._hp != before:
            self._add(PersonHealedEvent, hp_before=before, hp_after=self._hp)

    def revive(self, hp_rate: Rate, now: WorldTick) -> None:
        if not isinstance(self._life_state, Down):
            raise PersonNotDownException(f"{self._person.value} is not down: {self._life_state}")
        # 起きたのに HP 0 のままにしないよう、率が小さくても 1 は戻す。
        # 100 * 0.29 が 28.99… になって 1 減らないよう、率は書かれた小数のまま掛ける。
        current = max(1, math.floor(self._hp.maximum * Fraction(str(hp_rate.value))))
        self._hp = HitPoints(current=current, maximum=self._hp.maximum)
        self._life_state = Alive()
        self._add(PersonRevivedEvent, revived_at=now, hp_after=self._hp)

    def pass_time(self, now: WorldTick, death: DeathRule, hunger: HungerRule) -> None:
        if isinstance(self._life_state, Alive):
            self._grow_hungry(now, hunger)
        if isinstance(self._life_state, Down) and now >= self._life_state.fell_at + death.grace:
            self._life_state = Dead(died_at=now)
            self._add(PersonDiedEvent, died_at=now)

    def add_status_effect(self, effect: StatusEffect) -> None:
        self._require_alive("receive a status effect")
        replaced = self._status_effects.get(effect.kind, NoPreviousStatusEffect())
        self._status_effects[effect.kind] = effect
        self._add(StatusEffectAddedEvent, effect=effect, replaced=replaced)

    def remove_expired_status_effects(self, now: WorldTick) -> None:
        for kind, effect in list(self._status_effects.items()):
            if effect.has_expired(now):
                del self._status_effects[kind]
                self._add(StatusEffectExpiredEvent, effect=effect)

    def satisfy_hunger(self, amount: HungerAmount, rule: HungerRule) -> None:
        self._require_alive("eat")
        self._change_hunger(HungerAmount(max(0, self._hunger.value - amount.value)), rule)

    def exert(self, rule: FatigueRule) -> None:
        self._require_alive("exert")
        self._change_fatigue(min(self._fatigue + rule.per_exertion, rule.limit), rule)

    def rest(self, amount: FatigueAmount, rule: FatigueRule) -> None:
        self._require_alive("rest")
        self._change_fatigue(FatigueAmount(max(0, self._fatigue.value - amount.value)), rule)

    def start_action(self, until: WorldTick) -> None:
        self._require_alive("start an action")
        previous = NoPreviousAction() if isinstance(self._busy_until, NotBusy) else self._busy_until
        self._busy_until = until
        self._add(PersonBecameBusyEvent, until=until, previous_until=previous)

    def is_busy(self, now: WorldTick) -> bool:
        return isinstance(self._busy_until, WorldTick) and now < self._busy_until

    def hp(self) -> HitPoints:
        return self._hp

    def hunger(self) -> HungerAmount:
        return self._hunger

    def fatigue(self) -> FatigueAmount:
        return self._fatigue

    def can_act(self) -> bool:
        return isinstance(self._life_state, Alive)

    def is_dead(self) -> bool:
        return isinstance(self._life_state, Dead)

    def is_down(self) -> bool:
        return isinstance(self._life_state, Down)

    def occupant_in_world(self, departed_persons_act: bool) -> Occupant:
        if departed_persons_act and self.is_dead():
            return DepartedPerson(self._person)
        return PersonBody(self._person)

    def fatigue_reached_limit(self, rule: FatigueRule) -> bool:
        return self._fatigue >= rule.limit

    def _grow_hungry(self, now: WorldTick, rule: HungerRule) -> None:
        self._change_hunger(min(self._hunger + rule.per_tick, rule.limit), rule)
        if self._hunger >= rule.limit and isinstance(rule.starvation_damage, Damage):
            self.take_damage(rule.starvation_damage, now, Starvation())

    def _change_hunger(self, after: HungerAmount, rule: HungerRule) -> None:
        level_before = rule.level_of(self._hunger)
        self._hunger = after
        level_after = rule.level_of(after)
        if level_after != level_before:
            self._add(HungerLevelChangedEvent, level_before=level_before, level_after=level_after)

    def _change_fatigue(self, after: FatigueAmount, rule: FatigueRule) -> None:
        level_before = rule.level_of(self._fatigue)
        self._fatigue = after
        level_after = rule.level_of(after)
        if level_after != level_before:
            self._add(FatigueLevelChangedEvent, level_before=level_before, level_after=level_after)

    def _require_alive(self, doing: str) -> None:
        if not isinstance(self._life_state, Alive):
            raise PersonNotAliveException(f"{self._person.value} cannot {doing} while {self._life_state}")

    def _add(self, event_type: type[PersonVitalsEvent], **fields: Any) -> None:
        self.add_event(
            event_type(
                **new_event_stamp(),
                person=self._person,
                **fields,
            )
        )

from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.person.life_state import (
    Alive,
    Dead,
    Down,
    FallCause,
    LifeState,
    Starvation,
    StruckByPerson,
    WorldHappening,
)
from ai_rpg_world.game_world.domain.person.person_vitals import NotBusy, PersonVitalsMemento
from ai_rpg_world.game_world.domain.person.status_effect import StatusEffect, StatusEffectType
from ai_rpg_world.game_world.domain.value_object import FatigueAmount, HitPoints, HungerAmount, WorldTick
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    JsonUnion,
    JsonUnionMember,
    distinct_items,
    exact_fields,
    json_int,
    json_str,
    person_id_from_json,
    world_tick_from_json,
)


def _struck_by_person_from_json(raw: object) -> StruckByPerson:
    return StruckByPerson(person_id_from_json(exact_fields(raw, ("person",))["person"]))


_FALL_CAUSE: JsonUnion[FallCause] = JsonUnion(
    JsonUnionMember(
        "struck_by_person", StruckByPerson, lambda cause: {"person": cause.person.value}, _struck_by_person_from_json
    ),
    JsonUnionMember.fieldless("starvation", Starvation()),
    JsonUnionMember.fieldless("world_happening", WorldHappening()),
)


def _down_from_json(raw: object) -> Down:
    fields = exact_fields(raw, ("fell_at", "cause"))
    return Down(fell_at=world_tick_from_json(fields["fell_at"]), cause=_FALL_CAUSE.from_json(fields["cause"]))


def _dead_from_json(raw: object) -> Dead:
    return Dead(died_at=world_tick_from_json(exact_fields(raw, ("died_at",))["died_at"]))


_LIFE_STATE: JsonUnion[LifeState] = JsonUnion(
    JsonUnionMember.fieldless("alive", Alive()),
    JsonUnionMember(
        "down",
        Down,
        lambda down: {"fell_at": down.fell_at.value, "cause": _FALL_CAUSE.to_json(down.cause)},
        _down_from_json,
    ),
    JsonUnionMember("dead", Dead, lambda dead: {"died_at": dead.died_at.value}, _dead_from_json),
)

_BUSY_UNTIL: JsonUnion[WorldTick | NotBusy] = JsonUnion(
    JsonUnionMember("world_tick", WorldTick, lambda tick: tick.value, world_tick_from_json),
    JsonUnionMember.fieldless("not_busy", NotBusy()),
)


def _hit_points_from_json(raw: object) -> HitPoints:
    fields = exact_fields(raw, ("current", "maximum"))
    return HitPoints(current=json_int(fields["current"]), maximum=json_int(fields["maximum"]))


def _status_effect_from_json(raw: object) -> StatusEffect:
    fields = exact_fields(raw, ("kind", "expires_at"))
    return StatusEffect(StatusEffectType(json_str(fields["kind"])), world_tick_from_json(fields["expires_at"]))


@final
class PersonVitalsCodec:
    kind = "person_vitals"
    version = 1
    memento_type = PersonVitalsMemento

    def to_json(self, memento: PersonVitalsMemento) -> object:
        return {
            "person": memento.person.value,
            "hp": {"current": memento.hp.current, "maximum": memento.hp.maximum},
            "life_state": _LIFE_STATE.to_json(memento.life_state),
            "hunger": memento.hunger.value,
            "fatigue": memento.fatigue.value,
            "status_effects": [
                {"kind": effect.kind.value, "expires_at": effect.expires_at.value}
                for effect in sorted(memento.status_effects, key=lambda effect: effect.kind.value)
            ],
            "busy_until": _BUSY_UNTIL.to_json(memento.busy_until),
        }

    def from_json(self, raw: object) -> PersonVitalsMemento:
        fields = exact_fields(raw, ("person", "hp", "life_state", "hunger", "fatigue", "status_effects", "busy_until"))
        return PersonVitalsMemento(
            person=person_id_from_json(fields["person"]),
            hp=_hit_points_from_json(fields["hp"]),
            life_state=_LIFE_STATE.from_json(fields["life_state"]),
            hunger=HungerAmount(json_int(fields["hunger"])),
            fatigue=FatigueAmount(json_int(fields["fatigue"])),
            status_effects=distinct_items(fields["status_effects"], _status_effect_from_json),
            busy_until=_BUSY_UNTIL.from_json(fields["busy_until"]),
        )

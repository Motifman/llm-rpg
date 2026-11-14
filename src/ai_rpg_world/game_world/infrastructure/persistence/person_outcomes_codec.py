from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.person.person_outcomes import (
    Died,
    OutcomeOfPerson,
    PersonOutcomesMemento,
    Undecided,
)
from ai_rpg_world.game_world.domain.value_object import OutcomeId
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    JsonUnion,
    JsonUnionMember,
    exact_fields,
    json_str,
    ordered_items,
    person_id_from_json,
    world_id_from_json,
)

_OUTCOME: JsonUnion[Died | OutcomeId | Undecided] = JsonUnion(
    JsonUnionMember.fieldless("died", Died()),
    JsonUnionMember("outcome_id", OutcomeId, lambda outcome: outcome.value, lambda raw: OutcomeId(json_str(raw))),
    JsonUnionMember.fieldless("undecided", Undecided()),
)


def _outcome_of_person_from_json(raw: object) -> OutcomeOfPerson:
    fields = exact_fields(raw, ("person", "outcome"))
    return OutcomeOfPerson(person_id_from_json(fields["person"]), _OUTCOME.from_json(fields["outcome"]))


@final
class PersonOutcomesCodec:
    kind = "person_outcomes"
    version = 1
    memento_type = PersonOutcomesMemento

    def to_json(self, memento: PersonOutcomesMemento) -> object:
        return {
            "world_id": memento.world_id.value,
            "outcomes": [
                {"person": entry.person.value, "outcome": _OUTCOME.to_json(entry.outcome)} for entry in memento.outcomes
            ],
        }

    def from_json(self, raw: object) -> PersonOutcomesMemento:
        fields = exact_fields(raw, ("world_id", "outcomes"))
        return PersonOutcomesMemento(
            world_id=world_id_from_json(fields["world_id"]),
            outcomes=ordered_items(fields["outcomes"], _outcome_of_person_from_json),
        )

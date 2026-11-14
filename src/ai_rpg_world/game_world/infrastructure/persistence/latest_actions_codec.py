from __future__ import annotations

import json
from typing import final

from ai_rpg_world.game_world.domain.condition.subject import Anyone
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import InteractionId, PersonId
from ai_rpg_world.game_world.domain.world_records import ActionLastDoneAt, LatestActionsMemento
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    JsonUnion,
    JsonUnionMember,
    distinct_items,
    enum_from_json,
    enum_to_json,
    exact_fields,
    json_str,
    person_id_from_json,
    world_id_from_json,
    world_tick_from_json,
)

_WHO: JsonUnion[PersonId | Anyone] = JsonUnion(
    JsonUnionMember("person_id", PersonId, lambda person: person.value, person_id_from_json),
    JsonUnionMember.fieldless("anyone", Anyone()),
)

_ACTION: JsonUnion[ActionKind | InteractionId] = JsonUnion(
    JsonUnionMember("action_kind", ActionKind, enum_to_json, lambda raw: enum_from_json(raw, ActionKind)),
    JsonUnionMember(
        "interaction_id", InteractionId, lambda interaction: interaction.value, lambda raw: InteractionId(json_str(raw))
    ),
)


def _last_done_to_json(done: ActionLastDoneAt) -> dict[str, object]:
    return {"who": _WHO.to_json(done.who), "action": _ACTION.to_json(done.action), "at": done.at.value}


def _last_done_from_json(raw: object) -> ActionLastDoneAt:
    fields = exact_fields(raw, ("who", "action", "at"))
    return ActionLastDoneAt(
        _WHO.from_json(fields["who"]), _ACTION.from_json(fields["action"]), world_tick_from_json(fields["at"])
    )


def _key_order(written: dict[str, object]) -> str:
    return json.dumps([written["who"], written["action"]], sort_keys=True, ensure_ascii=False)


@final
class LatestActionsCodec:
    kind = "latest_actions"
    version = 1
    memento_type = LatestActionsMemento

    def to_json(self, memento: LatestActionsMemento) -> object:
        return {
            "world_id": memento.world_id.value,
            "last_done": sorted((_last_done_to_json(done) for done in memento.last_done), key=_key_order),
        }

    def from_json(self, raw: object) -> LatestActionsMemento:
        fields = exact_fields(raw, ("world_id", "last_done"))
        return LatestActionsMemento(
            world_id=world_id_from_json(fields["world_id"]),
            last_done=distinct_items(fields["last_done"], _last_done_from_json),
        )

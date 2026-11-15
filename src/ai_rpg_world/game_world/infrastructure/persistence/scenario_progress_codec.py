from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.value_object import InteractionId, ObjectId
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.joint_action_id import JointActionId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId
from ai_rpg_world.game_world.domain.world_records import (
    HappeningLastFiredAt,
    JointActionPartDoneBy,
    JointActionProgress,
    ReactionLastTruth,
    ScenarioProgressMemento,
)
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    distinct_items,
    exact_fields,
    json_bool,
    json_str,
    person_id_from_json,
    world_id_from_json,
    world_tick_from_json,
)


def _fired_from_json(raw: object) -> HappeningLastFiredAt:
    fields = exact_fields(raw, ("happening", "at"))
    return HappeningLastFiredAt(HappeningId(json_str(fields["happening"])), world_tick_from_json(fields["at"]))


def _truth_from_json(raw: object) -> ReactionLastTruth:
    fields = exact_fields(raw, ("reaction", "truth"))
    return ReactionLastTruth(ReactionId(json_str(fields["reaction"])), json_bool(fields["truth"]))


def _part_done_to_json(done: JointActionPartDoneBy) -> dict[str, object]:
    return {"object": done.obj.value, "interaction": done.interaction.value, "person": done.person.value}


def _part_done_from_json(raw: object) -> JointActionPartDoneBy:
    fields = exact_fields(raw, ("object", "interaction", "person"))
    return JointActionPartDoneBy(
        ObjectId(json_str(fields["object"])),
        InteractionId(json_str(fields["interaction"])),
        person_id_from_json(fields["person"]),
    )


def _joint_action_to_json(held: JointActionProgress) -> dict[str, object]:
    return {
        "joint": held.joint.value,
        "started_at": held.started_at.value,
        "parts_done": [
            _part_done_to_json(done)
            for done in sorted(held.parts_done, key=lambda done: (done.obj.value, done.interaction.value))
        ],
    }


def _joint_action_from_json(raw: object) -> JointActionProgress:
    fields = exact_fields(raw, ("joint", "started_at", "parts_done"))
    return JointActionProgress(
        JointActionId(json_str(fields["joint"])),
        world_tick_from_json(fields["started_at"]),
        distinct_items(fields["parts_done"], _part_done_from_json),
    )


@final
class ScenarioProgressCodec:
    kind = "scenario_progress"
    version = 2
    memento_type = ScenarioProgressMemento

    def to_json(self, memento: ScenarioProgressMemento) -> object:
        return {
            "world_id": memento.world_id.value,
            "last_fired": [
                {"happening": fired.happening.value, "at": fired.at.value}
                for fired in sorted(memento.last_fired, key=lambda fired: fired.happening.value)
            ],
            "reaction_truths": [
                {"reaction": noted.reaction.value, "truth": noted.truth}
                for noted in sorted(memento.reaction_truths, key=lambda noted: noted.reaction.value)
            ],
            "joint_actions": [
                _joint_action_to_json(held) for held in sorted(memento.joint_actions, key=lambda held: held.joint.value)
            ],
        }

    def from_json(self, raw: object) -> ScenarioProgressMemento:
        fields = exact_fields(raw, ("world_id", "last_fired", "reaction_truths", "joint_actions"))
        return ScenarioProgressMemento(
            world_id=world_id_from_json(fields["world_id"]),
            last_fired=distinct_items(fields["last_fired"], _fired_from_json),
            reaction_truths=distinct_items(fields["reaction_truths"], _truth_from_json),
            joint_actions=distinct_items(fields["joint_actions"], _joint_action_from_json),
        )

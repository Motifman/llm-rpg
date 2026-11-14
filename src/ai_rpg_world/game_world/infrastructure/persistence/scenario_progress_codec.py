from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId
from ai_rpg_world.game_world.domain.world_records import (
    HappeningLastFiredAt,
    ReactionLastTruth,
    ScenarioProgressMemento,
)
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    distinct_items,
    exact_fields,
    json_bool,
    json_str,
    world_id_from_json,
    world_tick_from_json,
)


def _fired_from_json(raw: object) -> HappeningLastFiredAt:
    fields = exact_fields(raw, ("happening", "at"))
    return HappeningLastFiredAt(HappeningId(json_str(fields["happening"])), world_tick_from_json(fields["at"]))


def _truth_from_json(raw: object) -> ReactionLastTruth:
    fields = exact_fields(raw, ("reaction", "truth"))
    return ReactionLastTruth(ReactionId(json_str(fields["reaction"])), json_bool(fields["truth"]))


@final
class ScenarioProgressCodec:
    kind = "scenario_progress"
    version = 1
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
        }

    def from_json(self, raw: object) -> ScenarioProgressMemento:
        fields = exact_fields(raw, ("world_id", "last_fired", "reaction_truths"))
        return ScenarioProgressMemento(
            world_id=world_id_from_json(fields["world_id"]),
            last_fired=distinct_items(fields["last_fired"], _fired_from_json),
            reaction_truths=distinct_items(fields["reaction_truths"], _truth_from_json),
        )

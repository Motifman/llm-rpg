from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.value_object import GroupDecisionId
from ai_rpg_world.game_world.domain.world_progress import Abstain, Ballot, GroupDecisionMemento, VoteFor
from ai_rpg_world.game_world.infrastructure.persistence.json_parts import (
    JsonUnion,
    JsonUnionMember,
    distinct_items,
    exact_fields,
    json_bool,
    json_str,
    person_id_from_json,
)

_CHOICE: JsonUnion[VoteFor | Abstain] = JsonUnion(
    JsonUnionMember(
        "vote_for",
        VoteFor,
        lambda vote: {"person": vote.person.value},
        lambda raw: VoteFor(person_id_from_json(exact_fields(raw, ("person",))["person"])),
    ),
    JsonUnionMember.fieldless("abstain", Abstain()),
)


def _ballot_from_json(raw: object) -> Ballot:
    fields = exact_fields(raw, ("voter", "choice"))
    return Ballot(person_id_from_json(fields["voter"]), _CHOICE.from_json(fields["choice"]))


@final
class GroupDecisionCodec:
    kind = "group_decision"
    version = 1
    memento_type = GroupDecisionMemento

    def to_json(self, memento: GroupDecisionMemento) -> object:
        return {
            "decision_id": memento.decision_id.value,
            "open": memento.open,
            "voters": sorted(person.value for person in memento.voters),
            "choices": sorted(person.value for person in memento.choices),
            "ballots": [
                {"voter": ballot.voter.value, "choice": _CHOICE.to_json(ballot.choice)}
                for ballot in sorted(memento.ballots, key=lambda ballot: ballot.voter.value)
            ],
        }

    def from_json(self, raw: object) -> GroupDecisionMemento:
        fields = exact_fields(raw, ("decision_id", "open", "voters", "choices", "ballots"))
        return GroupDecisionMemento(
            decision_id=GroupDecisionId(json_str(fields["decision_id"])),
            open=json_bool(fields["open"]),
            voters=distinct_items(fields["voters"], person_id_from_json),
            choices=distinct_items(fields["choices"], person_id_from_json),
            ballots=distinct_items(fields["ballots"], _ballot_from_json),
        )

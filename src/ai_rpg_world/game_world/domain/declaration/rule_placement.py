from __future__ import annotations

from dataclasses import dataclass, replace
from typing import final

from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName

_IN_ACTION = frozenset({SubjectKind.ACTOR, SubjectKind.NAMED_PERSON})


@final
@dataclass(frozen=True)
class RulePlacement:
    location: DesignLocation
    subjects: frozenset[SubjectKind]
    arguments: frozenset[ArgumentName]

    @classmethod
    def in_action(cls, location: DesignLocation, arguments: frozenset[ArgumentName]) -> RulePlacement:
        return cls(location=location, subjects=_IN_ACTION, arguments=arguments)

    @classmethod
    def in_person_interaction(cls, location: DesignLocation, arguments: frozenset[ArgumentName]) -> RulePlacement:
        return cls(location=location, subjects=_IN_ACTION | {SubjectKind.TARGET}, arguments=arguments)

    @classmethod
    def in_group_decision_result(cls, location: DesignLocation) -> RulePlacement:
        return cls(
            location=location,
            subjects=frozenset({SubjectKind.CHOSEN_BY_GROUP, SubjectKind.NAMED_PERSON}),
            arguments=frozenset(),
        )

    @classmethod
    def in_world(cls, location: DesignLocation) -> RulePlacement:
        return cls(location=location, subjects=frozenset({SubjectKind.NAMED_PERSON}), arguments=frozenset())

    def at_field(self, field: str) -> RulePlacement:
        return replace(self, location=replace(self.location, field=field))

    def flaws_of(self, requirements: Requirements) -> list[DesignFlaw]:
        unusable_subjects = sorted(kind.name for kind in requirements.subjects - self.subjects)
        undeclared_arguments = sorted(
            argument.value for argument in requirements.uses_action_arguments - self.arguments
        )
        flaws: list[DesignFlaw] = []
        if unusable_subjects:
            flaws.append(DesignFlaw(self.location, f"cannot refer to {unusable_subjects} here"))
        if undeclared_arguments:
            flaws.append(
                DesignFlaw(self.location, f"reads arguments {undeclared_arguments} the action does not declare")
            )
        return flaws

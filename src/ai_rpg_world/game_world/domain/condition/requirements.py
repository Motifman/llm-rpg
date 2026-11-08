from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration, GroupDecisionDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_phase_name import DayPhaseName
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.subject import SubjectKind


@final
@dataclass(frozen=True)
class Requirements:
    subjects: frozenset[SubjectKind]
    uses_chance: bool
    uses_action_arguments: frozenset[ArgumentName]
    waits_for_flags: frozenset[FlagDeclaration]
    reads_world_stage: bool
    reads_day_phases: frozenset[DayPhaseName]
    reads_weather: bool
    raises_flags: frozenset[FlagDeclaration]
    closes_group_decisions: frozenset[GroupDecisionDeclaration]
    may_hide_membership: bool

    @classmethod
    def nothing(cls) -> Requirements:
        return cls(
            subjects=frozenset(),
            uses_chance=False,
            uses_action_arguments=frozenset(),
            waits_for_flags=frozenset(),
            reads_world_stage=False,
            reads_day_phases=frozenset(),
            reads_weather=False,
            raises_flags=frozenset(),
            closes_group_decisions=frozenset(),
            may_hide_membership=False,
        )

    def combined_with(self, other: Requirements) -> Requirements:
        return Requirements(
            subjects=self.subjects | other.subjects,
            uses_chance=self.uses_chance or other.uses_chance,
            uses_action_arguments=self.uses_action_arguments | other.uses_action_arguments,
            waits_for_flags=self.waits_for_flags | other.waits_for_flags,
            reads_world_stage=self.reads_world_stage or other.reads_world_stage,
            reads_day_phases=self.reads_day_phases | other.reads_day_phases,
            reads_weather=self.reads_weather or other.reads_weather,
            raises_flags=self.raises_flags | other.raises_flags,
            closes_group_decisions=self.closes_group_decisions | other.closes_group_decisions,
            may_hide_membership=self.may_hide_membership or other.may_hide_membership,
        )

    def without_subject(self, kind: SubjectKind) -> Requirements:
        return replace(self, subjects=self.subjects - {kind})

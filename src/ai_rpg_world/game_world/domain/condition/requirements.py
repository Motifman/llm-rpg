from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
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

    @classmethod
    def nothing(cls) -> Requirements:
        return cls(
            subjects=frozenset(),
            uses_chance=False,
            uses_action_arguments=frozenset(),
            waits_for_flags=frozenset(),
        )

    def combined_with(self, other: Requirements) -> Requirements:
        return Requirements(
            subjects=self.subjects | other.subjects,
            uses_chance=self.uses_chance or other.uses_chance,
            uses_action_arguments=self.uses_action_arguments | other.uses_action_arguments,
            waits_for_flags=self.waits_for_flags | other.waits_for_flags,
        )

    def without_subject(self, kind: SubjectKind) -> Requirements:
        return replace(self, subjects=self.subjects - {kind})

from __future__ import annotations

from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration
from ai_rpg_world.game_world.domain.value_object import DescriptionText, FlagId

_DOOR_OPENED = FlagDeclaration(FlagId("door_opened"), DescriptionText("扉が開いた"), initially_raised=False)
_BELL_RANG = FlagDeclaration(FlagId("bell_rang"), DescriptionText("鐘が鳴った"), initially_raised=False)


class TestCombinedWith:
    """Requirements.combined_with が、2 つの要求を欄ごとに合わせることを保証する。"""

    def test_each_field_is_combined(self) -> None:
        """行為の人と旗 1 つを要る要求と、相手・偶然・引数・別の旗を要る要求を合わせると、主語の種類と待つ旗は和に、偶然と引数はどちらかが使えば使うになる。"""
        actor_side = Requirements(
            subjects=frozenset({SubjectKind.ACTOR}),
            uses_chance=False,
            uses_action_arguments=False,
            waits_for_flags=frozenset({_DOOR_OPENED}),
        )
        target_side = Requirements(
            subjects=frozenset({SubjectKind.TARGET}),
            uses_chance=True,
            uses_action_arguments=True,
            waits_for_flags=frozenset({_BELL_RANG}),
        )

        combined = actor_side.combined_with(target_side)

        assert combined == Requirements(
            subjects=frozenset({SubjectKind.ACTOR, SubjectKind.TARGET}),
            uses_chance=True,
            uses_action_arguments=True,
            waits_for_flags=frozenset({_DOOR_OPENED, _BELL_RANG}),
        )

    def test_combining_with_nothing_keeps_the_requirements(self) -> None:
        """何も要らない要求 (Requirements.nothing) と合わせても、元の要求は変わらない。"""
        actor_side = Requirements(
            subjects=frozenset({SubjectKind.ACTOR}),
            uses_chance=True,
            uses_action_arguments=False,
            waits_for_flags=frozenset({_DOOR_OPENED}),
        )

        assert actor_side.combined_with(Requirements.nothing()) == actor_side
        assert Requirements.nothing().combined_with(actor_side) == actor_side

    def test_nothing_needs_no_subject_chance_argument_or_flag(self) -> None:
        """Requirements.nothing は、主語も偶然も引数も待つ旗も要らない。"""
        assert Requirements.nothing() == Requirements(
            subjects=frozenset(),
            uses_chance=False,
            uses_action_arguments=False,
            waits_for_flags=frozenset(),
        )

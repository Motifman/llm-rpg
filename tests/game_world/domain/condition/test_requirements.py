from __future__ import annotations

from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration, GroupDecisionDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayPhaseName
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, FlagId, GroupDecisionId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId

_DOOR_OPENED = FlagDeclaration(FlagId("door_opened"), DescriptionText("扉が開いた"), initially_raised=False)
_BELL_RANG = FlagDeclaration(FlagId("bell_rang"), DescriptionText("鐘が鳴った"), initially_raised=False)
_PASSWORD = ArgumentName("password")
_MESSAGE = ArgumentName("message")
_NIGHT = DayPhaseName("night")
_DAWN = DayPhaseName("dawn")
_LANDSLIDE = HappeningId("landslide")
_QUAKE = HappeningId("quake")
_EXILE = GroupDecisionDeclaration(
    decision_id=GroupDecisionId("exile"), name=DisplayName("追放"), abstain_allowed=True, reveals_ballots=False
)


class TestCombinedWith:
    """Requirements.combined_with が、2 つの要求を欄ごとに合わせることを保証する。"""

    def test_each_field_is_combined(self) -> None:
        """行為の人・引数 password・旗 1 つ・段階・夜を読む要求と、相手・偶然・引数 message・別の旗・夜明け・天候・決定の締め・伏せた所属を持つ要求を合わせると、主語・引数・待つ旗・読む昼夜の段階・立てる旗・締める決定・読む出来事は和に、偶然・段階・天候・伏せた所属はどちらかが真なら真になる。"""
        actor_side = Requirements(
            subjects=frozenset({SubjectKind.ACTOR}),
            uses_chance=False,
            uses_action_arguments=frozenset({_PASSWORD}),
            waits_for_flags=frozenset({_DOOR_OPENED}),
            reads_world_stage=True,
            reads_day_phases=frozenset({_NIGHT}),
            reads_weather=False,
            raises_flags=frozenset({_BELL_RANG}),
            closes_group_decisions=frozenset(),
            may_hide_membership=False,
            reads_happenings=frozenset({_LANDSLIDE}),
        )
        target_side = Requirements(
            subjects=frozenset({SubjectKind.TARGET}),
            uses_chance=True,
            uses_action_arguments=frozenset({_MESSAGE}),
            waits_for_flags=frozenset({_BELL_RANG}),
            reads_world_stage=False,
            reads_day_phases=frozenset({_DAWN}),
            reads_weather=True,
            raises_flags=frozenset({_DOOR_OPENED}),
            closes_group_decisions=frozenset({_EXILE}),
            may_hide_membership=True,
            reads_happenings=frozenset({_QUAKE}),
        )

        combined = actor_side.combined_with(target_side)

        assert combined == Requirements(
            subjects=frozenset({SubjectKind.ACTOR, SubjectKind.TARGET}),
            uses_chance=True,
            uses_action_arguments=frozenset({_PASSWORD, _MESSAGE}),
            waits_for_flags=frozenset({_DOOR_OPENED, _BELL_RANG}),
            reads_world_stage=True,
            reads_day_phases=frozenset({_NIGHT, _DAWN}),
            reads_weather=True,
            raises_flags=frozenset({_DOOR_OPENED, _BELL_RANG}),
            closes_group_decisions=frozenset({_EXILE}),
            may_hide_membership=True,
            reads_happenings=frozenset({_LANDSLIDE, _QUAKE}),
        )

    def test_combining_with_nothing_keeps_the_requirements(self) -> None:
        """何も要らない要求 (Requirements.nothing) と合わせても、元の要求は変わらない。"""
        actor_side = Requirements(
            subjects=frozenset({SubjectKind.ACTOR}),
            uses_chance=True,
            uses_action_arguments=frozenset({_PASSWORD}),
            waits_for_flags=frozenset({_DOOR_OPENED}),
            reads_world_stage=False,
            reads_day_phases=frozenset(),
            reads_weather=False,
            raises_flags=frozenset(),
            closes_group_decisions=frozenset(),
            may_hide_membership=False,
            reads_happenings=frozenset(),
        )

        assert actor_side.combined_with(Requirements.nothing()) == actor_side
        assert Requirements.nothing().combined_with(actor_side) == actor_side

    def test_nothing_needs_no_subject_chance_argument_or_flag(self) -> None:
        """Requirements.nothing は、主語も偶然も引数も待つ旗も要らず、段階・昼夜・天候を読まず、旗を立てず、決定を締めず、所属を伏せない。"""
        assert Requirements.nothing() == Requirements(
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
            reads_happenings=frozenset(),
        )


class TestWithoutSubject:
    """Requirements.without_subject が、指した主語の種類だけを外し、ほかの要求を残すことを保証する。"""

    def test_removes_only_each_person(self) -> None:
        """行為の人と「その人」・偶然・引数・旗を要る要求から EACH_PERSON を外すと、行為の人・偶然・引数・旗の要求はそのまま残る。"""
        inside = Requirements(
            subjects=frozenset({SubjectKind.ACTOR, SubjectKind.EACH_PERSON}),
            uses_chance=True,
            uses_action_arguments=frozenset({_PASSWORD}),
            waits_for_flags=frozenset({_DOOR_OPENED}),
            reads_world_stage=False,
            reads_day_phases=frozenset(),
            reads_weather=False,
            raises_flags=frozenset(),
            closes_group_decisions=frozenset(),
            may_hide_membership=False,
            reads_happenings=frozenset(),
        )

        outside = inside.without_subject(SubjectKind.EACH_PERSON)

        assert outside == Requirements(
            subjects=frozenset({SubjectKind.ACTOR}),
            uses_chance=True,
            uses_action_arguments=frozenset({_PASSWORD}),
            waits_for_flags=frozenset({_DOOR_OPENED}),
            reads_world_stage=False,
            reads_day_phases=frozenset(),
            reads_weather=False,
            raises_flags=frozenset(),
            closes_group_decisions=frozenset(),
            may_hide_membership=False,
            reads_happenings=frozenset(),
        )

    def test_removing_an_absent_subject_changes_nothing(self) -> None:
        """要っていない主語の種類を外しても、要求は変わらない。"""
        actor_only = Requirements(
            subjects=frozenset({SubjectKind.ACTOR}),
            uses_chance=False,
            uses_action_arguments=frozenset(),
            waits_for_flags=frozenset(),
            reads_world_stage=False,
            reads_day_phases=frozenset(),
            reads_weather=False,
            raises_flags=frozenset(),
            closes_group_decisions=frozenset(),
            may_hide_membership=False,
            reads_happenings=frozenset(),
        )

        assert actor_only.without_subject(SubjectKind.EACH_PERSON) == actor_only

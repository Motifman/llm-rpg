from __future__ import annotations

from dataclasses import dataclass, replace
from typing import final

from ai_rpg_world.game_world.domain.action.trigger import HappeningFired
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration, WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.world_stage_declaration import AllActionsAllowed
from ai_rpg_world.game_world.domain.declaration.time_and_weather import NoDayNight
from ai_rpg_world.game_world.domain.effect.world_progress_effects import (
    CloseGroupDecisionEffect,
    EnterWorldStageEffect,
    StartGroupDecisionEffect,
)
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    GroupDecisionId,
    WorldStageId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.world_progress import GroupDecisionStartedEvent, WorldStage
from tests.game_world.domain.effect._builders import ALICE, BOB, CAROL, WORLD, EachPersonIsOneOf, FixedTruth
from tests.game_world.support.declarations_for_tests import HappeningForTests
from tests.game_world.support.world_in_memory import WorldInMemory

_DUSK = HappeningFired(HappeningForTests(HappeningId("dusk")))
_EXILE_VOTE = GroupDecisionDeclaration(
    decision_id=GroupDecisionId("exile_vote"),
    name=DisplayName("追放の投票"),
    abstain_allowed=True,
    reveals_ballots=False,
)


def _stage(name: str) -> WorldStageDeclaration:
    return WorldStageDeclaration(
        stage_id=WorldStageId(name),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の説明"),
        allowed_actions=AllActionsAllowed(),
    )


_DAY = _stage("day")
_NIGHT = _stage("night")


@final
@dataclass(frozen=True)
class _VoteRules:
    decision: GroupDecisionDeclaration
    voters: PeopleSelection
    choices: PeopleSelection


def _world() -> WorldInMemory:
    return WorldInMemory(
        world=WORLD,
        people=(ALICE, BOB, CAROL),
        world_stage=WorldStage.open(WORLD, _DAY, WorldTick(0)),
        stage_declarations=(_DAY, _NIGHT),
    )


class TestEnterWorldStageEffect:
    """EnterWorldStageEffect が、今の tick に世界の段階を移すことを保証する。"""

    def test_enters_stage_now(self) -> None:
        """tick 2 に夜へ移すと、世界の段階は夜で、入った tick は 2。"""
        world = _world()
        world.clock().advance(NoDayNight())
        world.clock().advance(NoDayNight())

        EnterWorldStageEffect(_NIGHT).apply(world.facts(), world.aggregates(), _DUSK)

        stage = world.aggregates().world_stage()
        assert stage.current() == _NIGHT.stage_id
        assert stage.entered_at() == WorldTick(2)


class TestStartAndCloseGroupDecisionEffect:
    """集団の決定を始める・締める効果が、規則の選び方で投票する人と候補を選び、GroupDecision に頼むことを保証する。"""

    def test_starts_with_voters_and_choices_selected_by_rules(self) -> None:
        """投票する人を Alice と Bob、候補を Bob と Carol に選ぶ規則で始めると、その顔ぶれで決定が開く。"""
        world = _world()
        rules = _VoteRules(
            _EXILE_VOTE,
            voters=PeopleSelection(EachPersonIsOneOf(frozenset({ALICE, BOB}))),
            choices=PeopleSelection(EachPersonIsOneOf(frozenset({BOB, CAROL}))),
        )

        StartGroupDecisionEffect(rules).apply(world.facts(), world.aggregates(), _DUSK)

        decision = world.group_decision_of(_EXILE_VOTE)
        assert decision.is_open()
        (started,) = decision.get_events()
        assert isinstance(started, GroupDecisionStartedEvent)
        assert started.voters == frozenset({ALICE, BOB})
        assert started.choices == frozenset({BOB, CAROL})

    def test_requires_what_selections_require_outside(self) -> None:
        """要るものは、投票する人と候補の選び方が外に求めるものを合わせたもの (EachPerson は含まない)。"""
        needs_actor = replace(Requirements.nothing(), subjects=frozenset({SubjectKind.ACTOR}))
        rules = _VoteRules(
            _EXILE_VOTE,
            voters=PeopleSelection(EachPersonIsOneOf(frozenset({ALICE}))),
            choices=PeopleSelection(FixedTruth(True, needs_actor)),
        )

        assert StartGroupDecisionEffect(rules).requirements() == needs_actor

    def test_close_tallies_open_decision(self) -> None:
        """開いている追放の投票を締めると、決定は閉じる。"""
        world = _world()
        world.group_decision_of(_EXILE_VOTE).start(frozenset({ALICE}), frozenset({BOB}))

        CloseGroupDecisionEffect(_EXILE_VOTE).apply(world.facts(), world.aggregates(), _DUSK)

        assert not world.group_decision_of(_EXILE_VOTE).is_open()

from __future__ import annotations

import pytest

from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.action.interaction_attempts import ObjectInteractionAttempt
from ai_rpg_world.game_world.domain.action.manner import Openly
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, NoText
from ai_rpg_world.game_world.domain.condition.condition_path import ConditionPath
from ai_rpg_world.game_world.domain.condition.latest_action_conditions import (
    SinceStart,
    SinceWorldStageEntered,
    TicksSinceLastActionAtLeastCondition,
)
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Actor, Anyone, SubjectKind
from ai_rpg_world.game_world.domain.declaration.progress import AllActionsAllowed, WorldStageDeclaration
from ai_rpg_world.game_world.domain.exception.condition_exception import NotDeclaredInThisWorldException
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.value_object import (
    DescriptionText,
    DisplayName,
    InteractionId,
    Ticks,
    WorldStageId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.world_progress import WorldStage
from tests.game_world.domain.condition._builders import ALICE, BOB, WORLD, text, vitals, world
from tests.game_world.domain.whereabouts._builders import thing
from tests.game_world.support.action_attempt_for_tests import ActionAttemptForTests
from tests.game_world.support.declarations_for_tests import InteractionForTests
from tests.game_world.support.world_in_memory import world_in_memory

_PULL_LEVER = InteractionId("pull_lever")
_BY_ALICE = ActionAttemptForTests(actor_id=ALICE)
_ALICE_SEARCHES = ActionAttemptForTests(actor_id=ALICE, action_kind=ActionKind.SEARCH)
_BOB_SEARCHES = ActionAttemptForTests(actor_id=BOB, action_kind=ActionKind.SEARCH)
_BOB_PULLS_LEVER = ObjectInteractionAttempt(
    BOB, thing("lever", "lift_landing"), InteractionForTests(_PULL_LEVER), {}, Openly()
)


def _stage(stage_id: str) -> WorldStageDeclaration:
    return WorldStageDeclaration(
        stage_id=WorldStageId(stage_id),
        name=DisplayName(stage_id),
        description=DescriptionText(f"{stage_id}の段階"),
        allowed_actions=AllActionsAllowed(),
    )


_DAY = _stage("day")
_NIGHT = _stage("night")


def _staged_world() -> WorldSession:
    return world_in_memory(
        world=WORLD,
        people=(ALICE, BOB),
        vitals=(vitals(ALICE), vitals(BOB)),
        world_stage=WorldStage.from_initial_stage(WORLD, _DAY, WorldTick(0)),
        stage_declarations=(_DAY, _NIGHT),
    )


def _at_tick(a_world: WorldSession, tick: int) -> WorldSession:
    while a_world.clock().now() < WorldTick(tick):
        a_world.clock().advance(a_world.facts().day_night())
    return a_world


def _since_lever(ticks: int, since: SinceStart | SinceWorldStageEntered) -> TicksSinceLastActionAtLeastCondition:
    return TicksSinceLastActionAtLeastCondition(
        who=Anyone(), action=_PULL_LEVER, ticks=Ticks(ticks), since=since, failure_text=NoText()
    )


class TestTicksSinceLastActionSinceStart:
    """TicksSinceLastActionAtLeastCondition が、SinceStart のとき、最後に行った tick か、まだなら世界の始まりから数えることを保証する。"""

    def test_anyone_counts_from_the_latest_by_anybody(self) -> None:
        """bob が tick 3 にレバーを引いたら、誰でもが 3 tick 以上引いていない条件は tick 5 で偽、tick 6 で真。"""
        condition = _since_lever(3, SinceStart())
        a_world = world()
        a_world.latest_actions().note(_BOB_PULLS_LEVER, WorldTick(3))

        assert not condition.holds(_at_tick(a_world, 5).facts(), _BY_ALICE)
        assert condition.holds(_at_tick(a_world, 6).facts(), _BY_ALICE)

    def test_not_yet_done_counts_from_the_start_of_the_world(self) -> None:
        """誰もレバーを引いていなければ、4 tick 以上の条件は tick 3 で偽、tick 4 で真。"""
        condition = _since_lever(4, SinceStart())

        assert not condition.holds(_at_tick(world(), 3).facts(), _BY_ALICE)
        assert condition.holds(_at_tick(world(), 4).facts(), _BY_ALICE)

    def test_subject_counts_only_their_own_actions(self) -> None:
        """alice が tick 1、bob が tick 4 に探したら、行う人 (alice) が 3 tick 以上探していない条件は tick 4 で真。bob の探索で数え直さない。"""
        condition = TicksSinceLastActionAtLeastCondition(
            who=Actor(), action=ActionKind.SEARCH, ticks=Ticks(3), since=SinceStart(), failure_text=NoText()
        )
        a_world = world()
        a_world.latest_actions().note(_ALICE_SEARCHES, WorldTick(1))
        a_world.latest_actions().note(_BOB_SEARCHES, WorldTick(4))

        assert condition.holds(_at_tick(a_world, 4).facts(), _BY_ALICE)

    def test_failure_carries_its_own_text(self) -> None:
        """足りないとき、自分の位置と自分の failure_text の文を返す。"""
        condition = TicksSinceLastActionAtLeastCondition(
            who=Anyone(),
            action=_PULL_LEVER,
            ticks=Ticks(3),
            since=SinceStart(),
            failure_text=text("レバーはまだ戻らない"),
        )

        assert condition.failure_reason(world().facts(), _BY_ALICE) == FailureReason(
            failed_part=ConditionPath.root(), text=text("レバーはまだ戻らない").about({})
        )


class TestTicksSinceLastActionSinceWorldStageEntered:
    """SinceWorldStageEntered のとき、今の段階に入る前の行為を数えず、段階に入った tick を起点にすることを保証する。"""

    def test_action_before_entering_the_stage_is_not_counted(self) -> None:
        """tick 2 にレバーを引き、tick 5 に夜へ入ったなら、3 tick 以上の条件は tick 7 で偽、tick 8 で真。"""
        condition = _since_lever(3, SinceWorldStageEntered())
        a_world = _staged_world()
        a_world.latest_actions().note(_BOB_PULLS_LEVER, WorldTick(2))
        _at_tick(a_world, 5)
        a_world.aggregates().world_stage().enter(_NIGHT, WorldTick(5))

        assert not condition.holds(_at_tick(a_world, 7).facts(), _BY_ALICE)
        assert condition.holds(_at_tick(a_world, 8).facts(), _BY_ALICE)

    def test_action_after_entering_the_stage_is_counted(self) -> None:
        """tick 5 に夜へ入り、tick 6 にレバーを引いたなら、3 tick 以上の条件は tick 8 で偽、tick 9 で真。"""
        condition = _since_lever(3, SinceWorldStageEntered())
        a_world = _at_tick(_staged_world(), 5)
        a_world.aggregates().world_stage().enter(_NIGHT, WorldTick(5))
        a_world.latest_actions().note(_BOB_PULLS_LEVER, WorldTick(6))

        assert not condition.holds(_at_tick(a_world, 8).facts(), _BY_ALICE)
        assert condition.holds(_at_tick(a_world, 9).facts(), _BY_ALICE)

    def test_world_without_stages_raises_domain_exception(self) -> None:
        """段階を宣言しない世界で SinceWorldStageEntered を評価すると NotDeclaredInThisWorldException を投げる。"""
        with pytest.raises(NotDeclaredInThisWorldException):
            _since_lever(3, SinceWorldStageEntered()).holds(world().facts(), _BY_ALICE)


class TestTicksSinceLastActionRequirements:
    """TicksSinceLastActionAtLeastCondition の requirements() が、誰についての主語の要求だけを持つことを保証する。"""

    def test_anyone_requires_nothing(self) -> None:
        """誰でもを見る条件は何も要らない。"""
        assert _since_lever(3, SinceStart()).requirements() == Requirements.nothing()

    def test_actor_requires_actor(self) -> None:
        """行う人を見る条件は ACTOR だけを要る。"""
        condition = TicksSinceLastActionAtLeastCondition(
            who=Actor(), action=ActionKind.SEARCH, ticks=Ticks(3), since=SinceStart(), failure_text=NoText()
        )

        assert condition.requirements().subjects == frozenset({SubjectKind.ACTOR})


class TestWhetherTheWorldStageIsRead:
    """TicksSinceLastActionAtLeastCondition が、起点に段階を使うときだけ段階を読むと答えることを保証する。"""

    def test_since_world_stage_entered_reads_the_world_stage(self) -> None:
        """起点が SinceWorldStageEntered なら段階を読み、SinceStart なら読まない。"""
        assert _since_lever(3, SinceWorldStageEntered()).requirements().reads_world_stage
        assert not _since_lever(3, SinceStart()).requirements().reads_world_stage

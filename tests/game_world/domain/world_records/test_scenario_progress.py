from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.world_time_conditions import TickAtLeastCondition
from ai_rpg_world.game_world.domain.declaration.verb.happening_declaration import HappeningDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.happening_notice import NoNotice
from ai_rpg_world.game_world.domain.declaration.verb.reaction_declaration import ReactionDeclaration
from ai_rpg_world.game_world.domain.effect.combined_effects import NoEffect
from ai_rpg_world.game_world.domain.exception.game_world_exception import RepeatedMementoKeyException
from ai_rpg_world.game_world.domain.value_object import Ticks, WorldId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId
from ai_rpg_world.game_world.domain.world_records import (
    HappeningLastFiredAt,
    NeverFired,
    ReactionLastTruth,
    ScenarioProgress,
    ScenarioProgressMemento,
)
from tests.game_world.support.memento_for_tests import rebuilt_from_memento

_WORLD = WorldId("harbor")


def _happening(happening_id: str, *, once: bool) -> HappeningDeclaration:
    return HappeningDeclaration(
        happening_id=HappeningId(happening_id),
        condition=TickAtLeastCondition(tick=WorldTick(0), failure_text=NoText()),
        effect=NoEffect(),
        once=once,
        notice=NoNotice(),
    )


_SHIP_ARRIVES = _happening("ship_arrives", once=True)
_TIDE_TURNS = _happening("tide_turns", once=False)


class TestScenarioProgressHappenings:
    """ScenarioProgress が、出来事の起きた時刻を帳簿に付け、once の出来事を二度起こさないことを保証する。"""

    def test_happening_has_never_fired_at_first(self) -> None:
        """作った直後は、どの出来事も last_fired_at が NeverFired で、once の出来事も起きてよい。"""
        progress = ScenarioProgress.start(_WORLD)

        assert progress.world_id == _WORLD
        assert progress.last_fired_at(_SHIP_ARRIVES.happening_id) == NeverFired()
        assert progress.may_fire(_SHIP_ARRIVES, WorldTick(0))

    def test_once_happening_may_not_fire_after_it_fired(self) -> None:
        """once の出来事 (船の入港) は、tick 3 で一度起きたら、tick 4 以降の may_fire が偽を返す。"""
        progress = ScenarioProgress.start(_WORLD)

        progress.note_happening_fired(_SHIP_ARRIVES, WorldTick(3))

        assert not progress.may_fire(_SHIP_ARRIVES, WorldTick(4))
        assert not progress.may_fire(_SHIP_ARRIVES, WorldTick(100))

    def test_last_fired_at_answers_the_latest_tick(self) -> None:
        """潮の変わり目が tick 2 と tick 7 に起きたら、last_fired_at は tick 7 を返す。"""
        progress = ScenarioProgress.start(_WORLD)

        progress.note_happening_fired(_TIDE_TURNS, WorldTick(2))
        progress.note_happening_fired(_TIDE_TURNS, WorldTick(7))

        assert progress.last_fired_at(_TIDE_TURNS.happening_id) == WorldTick(7)

    def test_firing_one_happening_leaves_others_unfired(self) -> None:
        """潮の変わり目が起きても、船の入港は NeverFired のままで、起きてよい。"""
        progress = ScenarioProgress.start(_WORLD)

        progress.note_happening_fired(_TIDE_TURNS, WorldTick(2))

        assert progress.last_fired_at(_SHIP_ARRIVES.happening_id) == NeverFired()
        assert progress.may_fire(_SHIP_ARRIVES, WorldTick(3))

    def test_happening_may_not_fire_twice_in_the_same_tick(self) -> None:
        """once でない潮の変わり目も、tick 5 に起きたら同じ tick 5 の may_fire は偽、tick 6 では真。"""
        progress = ScenarioProgress.start(_WORLD)

        progress.note_happening_fired(_TIDE_TURNS, WorldTick(5))

        assert not progress.may_fire(_TIDE_TURNS, WorldTick(5))
        assert progress.may_fire(_TIDE_TURNS, WorldTick(6))


def _reaction(reaction_id: str) -> ReactionDeclaration:
    return ReactionDeclaration(
        reaction_id=ReactionId(reaction_id),
        condition=TickAtLeastCondition(tick=WorldTick(0), failure_text=NoText()),
        when_becomes_true=NoEffect(),
        when_becomes_false=NoEffect(),
    )


_DOOR_CLOSED = _reaction("door_closed")
_LAMP_LIT = _reaction("lamp_lit")


class TestScenarioProgressReactions:
    """ScenarioProgress が、反応ごとに前に見た真偽を帳簿に付け、真偽の変わり目だけを変わったと答えることを保証する。"""

    def test_first_truth_seen_is_not_a_change(self) -> None:
        """一度も記録していない反応は、真でも偽でも reaction_changed が偽。世界の始まりには何も変わっていない。"""
        progress = ScenarioProgress.start(_WORLD)

        assert not progress.reaction_changed(_DOOR_CLOSED, True)
        assert not progress.reaction_changed(_DOOR_CLOSED, False)

    def test_truth_different_from_the_noted_one_is_a_change(self) -> None:
        """最初から閉じている扉 (真を記録) は、真のままなら変わっておらず、偽 (開いた) を見たら変わったと答える。"""
        progress = ScenarioProgress.start(_WORLD)

        progress.note_reaction_truth(_DOOR_CLOSED, True)

        assert not progress.reaction_changed(_DOOR_CLOSED, True)
        assert progress.reaction_changed(_DOOR_CLOSED, False)

    def test_closing_again_after_opening_is_a_change(self) -> None:
        """閉じている → 開いた、と記録したあと、また閉じた (真) を見ると変わったと答える。"""
        progress = ScenarioProgress.start(_WORLD)

        progress.note_reaction_truth(_DOOR_CLOSED, True)
        progress.note_reaction_truth(_DOOR_CLOSED, False)

        assert progress.reaction_changed(_DOOR_CLOSED, True)

    def test_noting_one_reaction_leaves_others_unrecorded(self) -> None:
        """扉の反応を記録しても、灯りの反応は一度も記録していないままで、真を見ても変わっていない。"""
        progress = ScenarioProgress.start(_WORLD)

        progress.note_reaction_truth(_DOOR_CLOSED, False)

        assert not progress.reaction_changed(_LAMP_LIT, True)


class TestNeverFired:
    """NeverFired が、一度も起きていない出来事について、経った時間を問われても偽を答えることを保証する。"""

    def test_has_never_passed_any_ticks(self) -> None:
        """NeverFired は、0 tick 経ったかを問われても偽を返す。"""
        assert not NeverFired().has_passed(Ticks(0), WorldTick(10))


class TestScenarioProgressMemento:
    """ScenarioProgress を memento から作り直すと、出来事の最後に起きた tick と反応の前に見た真偽が元と同じになることを保証する。"""

    def test_rebuilt_progress_answers_the_same(self) -> None:
        """船の到着が tick 3、潮の変わりが tick 4 に起き、扉は閉じている (真) と記録したあと作り直すと、同じ答えを返す。"""
        progress = ScenarioProgress.start(_WORLD)
        progress.note_happening_fired(_SHIP_ARRIVES, WorldTick(3))
        progress.note_happening_fired(_TIDE_TURNS, WorldTick(4))
        progress.note_reaction_truth(_DOOR_CLOSED, True)

        rebuilt = rebuilt_from_memento(progress)

        assert rebuilt.memento() == progress.memento()
        assert rebuilt.last_fired_at(HappeningId("ship_arrives")) == WorldTick(3)
        assert not rebuilt.may_fire(_TIDE_TURNS, WorldTick(4))
        assert rebuilt.reaction_changed(_DOOR_CLOSED, False)
        assert not rebuilt.reaction_changed(_LAMP_LIT, True)
        assert rebuilt.world_id == _WORLD


class TestScenarioProgressMementoRefusesRepeatedKey:
    """ScenarioProgressMemento が、同じ出来事や同じ反応を 2 つ持つ memento を作ることを断ることを保証する。"""

    def test_same_happening_fired_at_two_ticks_is_refused(self) -> None:
        """船の到着が tick 3 と tick 5 の 2 つある memento を作ると、RepeatedMementoKeyException を投げる。"""
        ship = HappeningId("ship_arrives")

        with pytest.raises(RepeatedMementoKeyException):
            ScenarioProgressMemento(
                world_id=_WORLD,
                last_fired=frozenset(
                    {HappeningLastFiredAt(ship, WorldTick(3)), HappeningLastFiredAt(ship, WorldTick(5))}
                ),
                reaction_truths=frozenset(),
            )

    def test_same_reaction_with_both_truths_is_refused(self) -> None:
        """扉が閉じている、の反応が真と偽の 2 つある memento を作ると、RepeatedMementoKeyException を投げる。"""
        door = ReactionId("door_closed")

        with pytest.raises(RepeatedMementoKeyException):
            ScenarioProgressMemento(
                world_id=_WORLD,
                last_fired=frozenset(),
                reaction_truths=frozenset({ReactionLastTruth(door, True), ReactionLastTruth(door, False)}),
            )

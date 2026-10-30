"""MonsterAggregate の CHASE 探索フェーズ API の domain 単体テスト (Phase 4b PR b)。

検証対象:
- start_chase_search の no-op 経路 (CHASE 以外 / DEAD / 0 以下)
- is_searching_lost_target の境界 (CHASE 以外で False)
- tick_chase_search_timer の戻り値と timer 減算
- reset_search_timer_on_rediscovery の no-op 経路と挙動
- chase_last_observed_target_spot_id プロパティ
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    BehaviorStateEnum,
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.value_object.attacker_ref import AttackerRef
from ai_rpg_world.domain.monster.value_object.monster_behavior_state import MonsterBehaviorState
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import (
    MonsterTemplateId,
)
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import (
    SkillLoadoutAggregate,
)
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


def _template() -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        base_stats=BaseStats(
            max_hp=20,
            max_mp=0,
            attack=4,
            defense=0,
            speed=1,
            critical_rate=0.0,
            evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(100, True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.NEUTRAL,
        description="A wolf.",
    )


def _aggregate(
    *,
    behavior_state: MonsterBehaviorState | None = None,
) -> MonsterAggregate:
    agg = MonsterAggregate(
        monster_id=MonsterId.create(101),
        template=_template(),
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(1),
            owner_id=101,
            normal_capacity=4,
            awakened_capacity=2,
        ),
        status=MonsterStatusEnum.ALIVE,
        spawned_at_tick=WorldTick(0),
        behavior_state=behavior_state,
    )
    return agg


def _enter_chase(agg: MonsterAggregate) -> None:
    agg.enter_chase_state(
        attacker_ref=AttackerRef.of_player(PlayerId(1)),
        last_observed_target_spot_id=SpotId.create(1),
        current_tick=WorldTick(0),
    )


def _observed_state(agg: MonsterAggregate) -> tuple:
    """拒否要求の直前と直後で比べる公開状態と未配信イベント。"""
    return (
        agg.behavior_state,
        agg.behavior_search_timer,
        agg.chase_attacker_ref(),
        agg.chase_last_observed_target_spot_id,
        agg.chase_started_at_tick,
        agg.persistence_flee_until_tick,
        agg.last_attacker_ref,
        agg.last_attacked_tick,
        agg.get_events(),
    )


class TestStartChaseSearch:
    """start_chase_search の no-op 経路と正常系。"""

    def test_chase_timer(self) -> None:
        """CHASE 中に start_chase_search すると search_timer が設定される。"""
        agg = _aggregate()
        _enter_chase(agg)
        agg.start_chase_search(3)
        assert agg.is_searching_lost_target() is True
        assert agg.behavior_search_timer == 3

    def test_chase_state_op(self) -> None:
        """IDLE で start_chase_search を呼んでも timer は 0 のまま。"""
        agg = _aggregate()
        agg.start_chase_search(3)
        assert agg.behavior_search_timer == 0
        assert agg.is_searching_lost_target() is False

    @pytest.mark.parametrize("was_chasing", [False, True], ids=["dead_idle", "dead_chase"])
    def test_dead_state_op(self, was_chasing: bool) -> None:
        """死亡後はIDLEでもCHASEでも探索を開始せず、既存状態とイベントを保つ。"""
        agg = _aggregate()
        if was_chasing:
            _enter_chase(agg)
            agg.start_chase_search(2)
        agg.apply_damage(agg.hp.value, WorldTick(1))
        assert agg.status == MonsterStatusEnum.DEAD
        assert agg.is_chasing() is was_chasing
        before = _observed_state(agg)

        agg.start_chase_search(3)

        assert _observed_state(agg) == before

    @pytest.mark.parametrize("search_ticks", [0, -1])
    @pytest.mark.parametrize("initial_timer", [0, 3])
    def test_search_ticks_zero_less_op(self, search_ticks: int, initial_timer: int) -> None:
        """0以下の探索期間は、既存の探索時間と追跡情報を変更しない。"""
        agg = _aggregate()
        _enter_chase(agg)
        if initial_timer:
            agg.start_chase_search(initial_timer)
        assert agg.behavior_search_timer == initial_timer
        before = _observed_state(agg)

        agg.start_chase_search(search_ticks)

        assert _observed_state(agg) == before


class TestIsSearchingLostTarget:
    """is_searching_lost_target の境界条件。"""

    def test_chase_search_timer_zero_false(self) -> None:
        """CHASE でも search timer 0 なら False。"""
        agg = _aggregate()
        _enter_chase(agg)
        assert agg.is_searching_lost_target() is False


class TestTickChaseSearchTimer:
    """tick_chase_search_timer の戻り値と境界。"""

    def test_returns_timer_two_true(self) -> None:
        """timer2 を減算して True を返す。"""
        agg = _aggregate()
        _enter_chase(agg)
        agg.start_chase_search(2)
        assert agg.is_searching_lost_target() is True
        result = agg.tick_chase_search_timer()
        assert result is True
        assert agg.behavior_search_timer == 1

    def test_returns_timer_one_false(self) -> None:
        """timer=1 の最後の tick では減算後 False (timer 切れ)。"""
        agg = _aggregate()
        _enter_chase(agg)
        agg.start_chase_search(1)
        result = agg.tick_chase_search_timer()
        assert result is False
        assert agg.behavior_search_timer == 0

    def test_timer_zero_false(self) -> None:
        """timer 0 では 何もせず False。"""
        agg = _aggregate()
        _enter_chase(agg)
        result = agg.tick_chase_search_timer()
        assert result is False

    @pytest.mark.parametrize("search_timer", [0, 2])
    def test_chase_false(self, search_timer: int) -> None:
        """非CHASEでは復元した探索時間が正でも減らさずFalseを返す。"""
        agg = _aggregate(
            behavior_state=MonsterBehaviorState.from_parts(
                state=BehaviorStateEnum.IDLE,
                target_id=None,
                last_known_position=None,
                initial_position=None,
                search_timer=search_timer,
            )
        )
        assert agg.is_chasing() is False
        assert agg.behavior_search_timer == search_timer
        before = _observed_state(agg)

        assert agg.tick_chase_search_timer() is False
        assert _observed_state(agg) == before


class TestResetSearchTimerOnRediscovery:
    """reset_search_timer_on_rediscovery の no-op 経路と挙動。"""

    def test_timer_zero_chase(self) -> None:
        """探索中なら timer を 0 に戻し CHASE は継続。"""
        agg = _aggregate()
        _enter_chase(agg)
        agg.start_chase_search(3)
        agg.reset_search_timer_on_rediscovery()
        assert agg.behavior_search_timer == 0
        assert agg.is_chasing() is True
        # chase_attacker_ref / last_observed_target_spot_id は維持される
        assert agg.chase_attacker_ref() == AttackerRef.of_player(PlayerId(1))
        assert agg.chase_last_observed_target_spot_id == SpotId.create(1)
        before = _observed_state(agg)
        agg.reset_search_timer_on_rediscovery()
        assert _observed_state(agg) == before


class TestChaseLastObservedProperty:
    """chase_last_observed_target_spot_id プロパティ。"""

    @pytest.mark.parametrize("has_previous_chase", [False, True], ids=["idle", "flee_with_spot"])
    def test_idle_none(self, has_previous_chase: bool) -> None:
        """IDLEやFLEEでは、保持中の観測spotがあっても追跡用の取得はNoneになる。"""
        agg = _aggregate()
        if has_previous_chase:
            _enter_chase(agg)
            agg.enter_flee_state(WorldTick(10), duration_ticks=3)
            assert agg.persistence_last_observed_target_spot_id == SpotId(1)
        assert agg.is_chasing() is False
        assert agg.chase_last_observed_target_spot_id is None

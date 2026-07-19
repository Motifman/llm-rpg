"""MonsterAggregate の CHASE 探索フェーズ API の domain 単体テスト (Phase 4b PR b)。

検証対象:
- start_chase_search の no-op 経路 (CHASE 以外 / DEAD / 0 以下)
- is_searching_lost_target の境界 (CHASE 以外で False)
- tick_chase_search_timer の戻り値と timer 減算
- reset_search_timer_on_rediscovery の no-op 経路と挙動
- chase_last_observed_target_spot_id プロパティ
"""

from __future__ import annotations

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    BehaviorStateEnum,
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.value_object.attacker_ref import AttackerRef
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_lifecycle_state import (
    MonsterLifecycleState,
)
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
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


def _template() -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        base_stats=BaseStats(
            max_hp=20, max_mp=0, attack=4,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(100, True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.NEUTRAL,
        description="A wolf.",
    )


def _aggregate(
    *, status: MonsterStatusEnum = MonsterStatusEnum.ALIVE,
) -> MonsterAggregate:
    agg = MonsterAggregate(
        monster_id=MonsterId.create(101),
        template=_template(),
        world_object_id=WorldObjectId.create(9001),
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(1), owner_id=101,
            normal_capacity=4, awakened_capacity=2,
        ),
        status=MonsterStatusEnum.ALIVE,
        spawned_at_tick=WorldTick(0),
    )
    if status != MonsterStatusEnum.ALIVE:
        agg._lifecycle_state = MonsterLifecycleState(
            hp=agg._lifecycle_state.hp,
            mp=agg._lifecycle_state.mp,
            status=status,
            last_death_tick=WorldTick(1),
            spawned_at_tick=WorldTick(0),
            hunger=0.0,
            starvation_timer=0,
        )
    return agg


def _enter_chase(agg: MonsterAggregate) -> None:
    agg.enter_chase_state(
        attacker_ref=AttackerRef.of_player(PlayerId(1)),
        last_observed_target_spot_id=SpotId.create(1),
        current_tick=WorldTick(0),
    )


class TestStartChaseSearch:
    """start_chase_search の no-op 経路と正常系。"""

    def test_chase_timer(self) -> None:
        """CHASE 中に start_chase_search すると search_timer が設定される。"""
        agg = _aggregate()
        _enter_chase(agg)
        agg.start_chase_search(3)
        assert agg.is_searching_lost_target() is True
        assert agg._behavior_state.search_timer == 3

    def test_chase_state_op(self) -> None:
        """IDLE で start_chase_search を呼んでも timer は 0 のまま。"""
        agg = _aggregate()
        agg.start_chase_search(3)
        assert agg._behavior_state.search_timer == 0
        assert agg.is_searching_lost_target() is False

    def test_dead_state_op(self) -> None:
        """DEAD 状態では no op。"""
        agg = _aggregate(status=MonsterStatusEnum.DEAD)
        # DEAD なので enter_chase_state も no-op、結果 IDLE のまま
        _enter_chase(agg)
        agg.start_chase_search(3)
        assert agg._behavior_state.search_timer == 0

    def test_search_ticks_zero_less_op(self) -> None:
        """search_ticks <= 0 は timer 設定しない。"""
        agg = _aggregate()
        _enter_chase(agg)
        agg.start_chase_search(0)
        assert agg._behavior_state.search_timer == 0
        agg.start_chase_search(-1)
        assert agg._behavior_state.search_timer == 0


class TestIsSearchingLostTarget:
    """is_searching_lost_target の境界条件。"""

    def test_idle_false(self) -> None:
        """IDLE で False。"""
        agg = _aggregate()
        assert agg.is_searching_lost_target() is False

    def test_chase_search_timer_zero_false(self) -> None:
        """CHASE でも search timer 0 なら False。"""
        agg = _aggregate()
        _enter_chase(agg)
        assert agg.is_searching_lost_target() is False

    def test_chase_search_timer_two_true(self) -> None:
        """CHASE で search timer 2 なら True。"""
        agg = _aggregate()
        _enter_chase(agg)
        agg.start_chase_search(2)
        assert agg.is_searching_lost_target() is True


class TestTickChaseSearchTimer:
    """tick_chase_search_timer の戻り値と境界。"""

    def test_returns_timer_two_true(self) -> None:
        """timer2 を減算して True を返す。"""
        agg = _aggregate()
        _enter_chase(agg)
        agg.start_chase_search(2)
        result = agg.tick_chase_search_timer()
        assert result is True
        assert agg._behavior_state.search_timer == 1

    def test_returns_timer_one_false(self) -> None:
        """timer=1 の最後の tick では減算後 False (timer 切れ)。"""
        agg = _aggregate()
        _enter_chase(agg)
        agg.start_chase_search(1)
        result = agg.tick_chase_search_timer()
        assert result is False
        assert agg._behavior_state.search_timer == 0

    def test_timer_zero_false(self) -> None:
        """timer 0 では 何もせず False。"""
        agg = _aggregate()
        _enter_chase(agg)
        result = agg.tick_chase_search_timer()
        assert result is False

    def test_chase_false(self) -> None:
        """CHASE でないと False。"""
        agg = _aggregate()
        result = agg.tick_chase_search_timer()
        assert result is False


class TestResetSearchTimerOnRediscovery:
    """reset_search_timer_on_rediscovery の no-op 経路と挙動。"""

    def test_timer_zero_chase(self) -> None:
        """探索中なら timer を 0 に戻し CHASE は継続。"""
        agg = _aggregate()
        _enter_chase(agg)
        agg.start_chase_search(3)
        agg.reset_search_timer_on_rediscovery()
        assert agg._behavior_state.search_timer == 0
        assert agg.is_chasing() is True
        # chase_attacker_ref / last_observed_target_spot_id は維持される
        assert agg.chase_attacker_ref() == AttackerRef.of_player(PlayerId(1))
        assert agg.chase_last_observed_target_spot_id == SpotId.create(1)

    def test_op(self) -> None:
        """CHASE 中だが timer 0 なら何もしない。"""
        agg = _aggregate()
        _enter_chase(agg)
        # timer 0 のまま reset を呼ぶ
        agg.reset_search_timer_on_rediscovery()
        assert agg._behavior_state.search_timer == 0


class TestChaseLastObservedProperty:
    """chase_last_observed_target_spot_id プロパティ。"""

    def test_returns_chase_state_value(self) -> None:
        """CHASE 中は state の値を返す。"""
        agg = _aggregate()
        _enter_chase(agg)
        assert agg.chase_last_observed_target_spot_id == SpotId.create(1)

    def test_idle_none(self) -> None:
        """IDLE では None。"""
        agg = _aggregate()
        assert agg.chase_last_observed_target_spot_id is None

    def test_chase_clear_none(self) -> None:
        """CHASE を clear すると None。"""
        agg = _aggregate()
        _enter_chase(agg)
        agg.clear_behavior_state_to_idle()
        assert agg.chase_last_observed_target_spot_id is None

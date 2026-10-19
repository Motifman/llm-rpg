"""MonsterAggregate の Phase 4a 反撃 / 逃走 state API。

検証対象:
- last_attacker_ref が record_attacked_by_in_spot で記録される
- enter_flee_state / enter_chase_state / clear_behavior_state_to_idle の遷移
- is_fleeing は flee_until_tick 経過で False を返す
- DEAD 状態では state 遷移 API が no-op
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
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


def _template() -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        base_stats=BaseStats(
            max_hp=20, max_mp=0, attack=5,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="A wolf.",
    )


def _aggregate() -> MonsterAggregate:
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
    return agg


def _enter_chase(agg: MonsterAggregate) -> None:
    agg.enter_chase_state(
        attacker_ref=AttackerRef.of_player(PlayerId(7)),
        last_observed_target_spot_id=SpotId(1), current_tick=WorldTick(10),
    )


def _observed_state(agg: MonsterAggregate) -> tuple:
    """拒否要求の直前と直後で比べる公開状態と未配信イベント。"""
    return (
        agg.behavior_state, agg.behavior_search_timer,
        agg.chase_attacker_ref(), agg.chase_last_observed_target_spot_id,
        agg.chase_started_at_tick, agg.persistence_flee_until_tick,
        agg.last_attacker_ref, agg.last_attacked_tick, agg.get_events(),
    )


class TestLastAttackerRef:
    """record_attacked_by_in_spot が attacker_ref を保持する。"""

    def test_attacker_ref_unspecified_none(self) -> None:
        """attacker_ref を渡さずに記録した場合 last_attacker_ref は None のまま。"""
        agg = _aggregate()
        agg.record_attacked_by_in_spot(current_tick=WorldTick(5))
        assert agg.last_attacker_ref is None
        assert agg.last_attacked_tick == WorldTick(5)

    def test_preserves_player_ref(self) -> None:
        """player attacker を渡したら kind=PLAYER の AttackerRef を保持する。"""
        agg = _aggregate()
        ref = AttackerRef.of_player(PlayerId(7))
        agg.record_attacked_by_in_spot(current_tick=WorldTick(5), attacker_ref=ref)
        assert agg.last_attacker_ref == ref

    def test_preserves_monster_ref(self) -> None:
        """monster attacker を渡したら kind=MONSTER の AttackerRef を保持する。"""
        agg = _aggregate()
        ref = AttackerRef.of_monster(MonsterId.create(202))
        agg.record_attacked_by_in_spot(current_tick=WorldTick(5), attacker_ref=ref)
        assert agg.last_attacker_ref == ref

    @pytest.mark.parametrize("had_attack_record", [False, True], ids=["unrecorded", "recorded"])
    def test_dead_state_op_3(self, had_attack_record: bool) -> None:
        """死亡済みなら未記録値も以前の被弾情報も上書きせず、イベントも保つ。"""
        agg = _aggregate()
        if had_attack_record:
            agg.record_attacked_by_in_spot(WorldTick(2), AttackerRef.of_monster(MonsterId(202)))
        agg.apply_damage(agg.hp.value, WorldTick(3))
        assert agg.status == MonsterStatusEnum.DEAD
        before = _observed_state(agg)

        agg.record_attacked_by_in_spot(
            current_tick=WorldTick(5), attacker_ref=AttackerRef.of_player(PlayerId(1)),
        )

        assert _observed_state(agg) == before


class TestFleeState:
    """enter_flee_state / is_fleeing の遷移。"""

    def test_enter_flee_state_flee_true(self) -> None:
        """FLEE 遷移後、現在 tick が flee_until 以内なら is_fleeing が True。"""
        agg = _aggregate()
        agg.enter_flee_state(WorldTick(10), duration_ticks=3)
        assert agg.behavior_state == BehaviorStateEnum.FLEE
        assert agg.is_fleeing(WorldTick(10)) is True
        assert agg.is_fleeing(WorldTick(13)) is True
        assert agg.is_fleeing(WorldTick(14)) is False

    @pytest.mark.parametrize("duration_ticks", [0, -1])
    @pytest.mark.parametrize("was_chasing", [False, True], ids=["idle", "chase"])
    def test_duration_ticks_zero_less(self, duration_ticks: int, was_chasing: bool) -> None:
        """0以下の逃走期間はIDLEや既存のCHASEと追跡情報を変えない。"""
        agg = _aggregate()
        if was_chasing:
            _enter_chase(agg)
        before = _observed_state(agg)

        agg.enter_flee_state(WorldTick(10), duration_ticks=duration_ticks)

        assert _observed_state(agg) == before

    @pytest.mark.parametrize("was_chasing", [False, True], ids=["dead_idle", "dead_chase"])
    def test_dead_state_op_2(self, was_chasing: bool) -> None:
        """死亡後はFLEE要求で状態や残る探索時間、未配信イベントを変えない。"""
        agg = _aggregate()
        if was_chasing:
            _enter_chase(agg)
            agg.start_chase_search(3)
        agg.apply_damage(agg.hp.value, WorldTick(11))
        assert agg.status == MonsterStatusEnum.DEAD
        assert agg.is_chasing() is was_chasing
        before = _observed_state(agg)

        agg.enter_flee_state(WorldTick(12), duration_ticks=3)

        assert _observed_state(agg) == before


class TestChaseState:
    """enter_chase_state / is_chasing / chase_attacker_ref。"""

    def test_enter_chase_state_chase_attacker_ref(self) -> None:
        """CHASE 遷移後、is_chasing と chase_attacker_ref が一致する。"""
        agg = _aggregate()
        ref = AttackerRef.of_player(PlayerId(7))
        agg.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SpotId.create(1), current_tick=WorldTick(0))
        assert agg.is_chasing() is True
        assert agg.chase_attacker_ref() == ref
        assert agg.chase_last_observed_target_spot_id == SpotId(1)
        assert agg.chase_started_at_tick == WorldTick(0)

    @pytest.mark.parametrize("had_attack_record", [False, True], ids=["unrecorded", "recorded"])
    def test_chase_attacker_ref_none(self, had_attack_record: bool) -> None:
        """IDLEでは被弾者を覚えていても追跡相手はNoneを返す。"""
        agg = _aggregate()
        if had_attack_record:
            ref = AttackerRef.of_player(PlayerId(7))
            agg.record_attacked_by_in_spot(WorldTick(5), ref)
            assert agg.last_attacker_ref == ref
        assert agg.behavior_state == BehaviorStateEnum.IDLE
        assert agg.chase_attacker_ref() is None

    def test_chase_attacker_ref_last_attacker_ref(self) -> None:
        """第三者の被弾情報を更新しても、追跡相手・開始tick・観測spotは維持する。"""
        agg = _aggregate()
        _enter_chase(agg)
        intruder = AttackerRef.of_monster(MonsterId(999))

        agg.record_attacked_by_in_spot(WorldTick(20), intruder)

        assert agg.chase_attacker_ref() == AttackerRef.of_player(PlayerId(7))
        assert agg.last_attacker_ref == intruder
        assert agg.last_attacked_tick == WorldTick(20)
        assert agg.chase_started_at_tick == WorldTick(10)
        assert agg.chase_last_observed_target_spot_id == SpotId(1)

    @pytest.mark.parametrize("was_fleeing", [False, True], ids=["dead_idle", "dead_flee"])
    def test_dead_state_op(self, was_fleeing: bool) -> None:
        """死亡後はCHASE要求で以前の状態・逃走期限・未配信イベントを変えない。"""
        agg = _aggregate()
        if was_fleeing:
            agg.enter_flee_state(WorldTick(10), duration_ticks=3)
        agg.apply_damage(agg.hp.value, WorldTick(11))
        assert agg.status == MonsterStatusEnum.DEAD
        assert agg.behavior_state == (BehaviorStateEnum.FLEE if was_fleeing else BehaviorStateEnum.IDLE)
        before = _observed_state(agg)

        agg.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(8)),
            last_observed_target_spot_id=SpotId(2), current_tick=WorldTick(12),
        )

        assert _observed_state(agg) == before


class TestClearBehaviorState:
    """clear_behavior_state_to_idle で FLEE / CHASE が解除される。"""

    def test_flee_idle(self) -> None:
        """FLEE 状態を clear すると IDLE に戻る。"""
        agg = _aggregate()
        agg.enter_flee_state(WorldTick(10), duration_ticks=3)
        agg.clear_behavior_state_to_idle()
        assert agg.behavior_state == BehaviorStateEnum.IDLE
        assert agg.is_fleeing(WorldTick(10)) is False

    def test_chase_idle(self) -> None:
        """CHASE → clear → IDLE。chase_attacker_ref も None に戻る。"""
        agg = _aggregate()
        agg.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
            last_observed_target_spot_id=SpotId.create(1),
            current_tick=WorldTick(0),
        )
        agg.start_chase_search(3)
        agg.clear_behavior_state_to_idle()
        assert agg.behavior_state == BehaviorStateEnum.IDLE
        assert agg.is_chasing() is False
        assert agg.chase_attacker_ref() is None
        assert agg.chase_last_observed_target_spot_id is None
        assert agg.chase_started_at_tick is None
        assert agg.behavior_search_timer == 0

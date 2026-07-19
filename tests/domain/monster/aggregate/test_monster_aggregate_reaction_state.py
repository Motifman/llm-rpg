"""MonsterAggregate の Phase 4a 反撃 / 逃走 state API。

検証対象:
- last_attacker_ref が record_attacked_by_in_spot で記録される
- enter_flee_state / enter_chase_state / clear_behavior_state_to_idle の遷移
- is_fleeing は flee_until_tick 経過で False を返す
- DEAD 状態では state 遷移 API が no-op
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
            max_hp=20, max_mp=0, attack=5,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="A wolf.",
    )


def _aggregate(*, status: MonsterStatusEnum = MonsterStatusEnum.ALIVE) -> MonsterAggregate:
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

    def test_dead_state_op_3(self) -> None:
        """死亡済みなら attacker_ref も tick も更新されない。"""
        agg = _aggregate(status=MonsterStatusEnum.DEAD)
        agg.record_attacked_by_in_spot(
            current_tick=WorldTick(5),
            attacker_ref=AttackerRef.of_player(PlayerId(1)),
        )
        assert agg.last_attacker_ref is None
        assert agg.last_attacked_tick is None


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

    def test_duration_ticks_zero_less(self) -> None:
        """duration_ticks <= 0 は no-op として扱う。"""
        agg = _aggregate()
        agg.enter_flee_state(WorldTick(10), duration_ticks=0)
        assert agg.behavior_state != BehaviorStateEnum.FLEE

    def test_dead_state_op_2(self) -> None:
        """死亡済みなら state 遷移しない。"""
        agg = _aggregate(status=MonsterStatusEnum.DEAD)
        agg.enter_flee_state(WorldTick(10), duration_ticks=3)
        assert agg.behavior_state != BehaviorStateEnum.FLEE


class TestChaseState:
    """enter_chase_state / is_chasing / chase_attacker_ref。"""

    def test_enter_chase_state_chase_attacker_ref(self) -> None:
        """CHASE 遷移後、is_chasing と chase_attacker_ref が一致する。"""
        agg = _aggregate()
        ref = AttackerRef.of_player(PlayerId(7))
        agg.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SpotId.create(1), current_tick=WorldTick(0))
        assert agg.is_chasing() is True
        assert agg.chase_attacker_ref() == ref

    def test_chase_attacker_ref_none(self) -> None:
        """CHASE 状態でない場合は chase_attacker_ref が None を返す。"""
        agg = _aggregate()
        assert agg.chase_attacker_ref() is None

    def test_chase_attacker_ref_last_attacker_ref(self) -> None:
        """CHASE 開始後に新しい attacker から殴られても chase_attacker_ref は固定。"""
        agg = _aggregate()
        original_ref = AttackerRef.of_player(PlayerId(7))
        agg.enter_chase_state(
            attacker_ref=original_ref, last_observed_target_spot_id=SpotId.create(1),
            current_tick=WorldTick(10),
        )
        # 第三者から殴られて last_attacker_ref が上書きされる
        agg.record_attacked_by_in_spot(
            current_tick=WorldTick(20),
            attacker_ref=AttackerRef.of_monster(MonsterId.create(999)),
        )
        # CHASE の追跡対象は変わらない
        assert agg.chase_attacker_ref() == original_ref
        assert agg.last_attacker_ref != original_ref

    def test_dead_state_op(self) -> None:
        """死亡済みなら CHASE 遷移しない。"""
        agg = _aggregate(status=MonsterStatusEnum.DEAD)
        agg.enter_chase_state(
            attacker_ref=AttackerRef.of_player(PlayerId(7)),
            last_observed_target_spot_id=SpotId.create(1),
            current_tick=WorldTick(0),
        )
        assert agg.is_chasing() is False


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
        agg.clear_behavior_state_to_idle()
        assert agg.behavior_state == BehaviorStateEnum.IDLE
        assert agg.is_chasing() is False
        assert agg.chase_attacker_ref() is None

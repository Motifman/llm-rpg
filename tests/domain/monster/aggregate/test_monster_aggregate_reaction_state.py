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

    def test_attacker_ref_未指定なら_None_のまま(self) -> None:
        """attacker_ref を渡さずに記録した場合 last_attacker_ref は None のまま。"""
        agg = _aggregate()
        agg.record_attacked_by_in_spot(current_tick=WorldTick(5))
        assert agg.last_attacker_ref is None
        assert agg.last_attacked_tick == WorldTick(5)

    def test_player_ref_を_保持する(self) -> None:
        """player attacker を渡したら kind=PLAYER の AttackerRef を保持する。"""
        agg = _aggregate()
        ref = AttackerRef.of_player(PlayerId(7))
        agg.record_attacked_by_in_spot(current_tick=WorldTick(5), attacker_ref=ref)
        assert agg.last_attacker_ref == ref

    def test_monster_ref_を_保持する(self) -> None:
        """monster attacker を渡したら kind=MONSTER の AttackerRef を保持する。"""
        agg = _aggregate()
        ref = AttackerRef.of_monster(MonsterId.create(202))
        agg.record_attacked_by_in_spot(current_tick=WorldTick(5), attacker_ref=ref)
        assert agg.last_attacker_ref == ref

    def test_DEAD_状態では_no_op(self) -> None:
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

    def test_enter_flee_state_で_FLEE_に_遷移し_期限内は_True(self) -> None:
        """FLEE 遷移後、現在 tick が flee_until 以内なら is_fleeing が True。"""
        agg = _aggregate()
        agg.enter_flee_state(WorldTick(10), duration_ticks=3)
        assert agg.behavior_state == BehaviorStateEnum.FLEE
        assert agg.is_fleeing(WorldTick(10)) is True
        assert agg.is_fleeing(WorldTick(13)) is True
        assert agg.is_fleeing(WorldTick(14)) is False

    def test_duration_ticks_0_以下では_遷移しない(self) -> None:
        """duration_ticks <= 0 は no-op として扱う。"""
        agg = _aggregate()
        agg.enter_flee_state(WorldTick(10), duration_ticks=0)
        assert agg.behavior_state != BehaviorStateEnum.FLEE

    def test_DEAD_状態では_no_op(self) -> None:
        """死亡済みなら state 遷移しない。"""
        agg = _aggregate(status=MonsterStatusEnum.DEAD)
        agg.enter_flee_state(WorldTick(10), duration_ticks=3)
        assert agg.behavior_state != BehaviorStateEnum.FLEE


class TestChaseState:
    """enter_chase_state / is_chasing / chase_target_id。"""

    def test_enter_chase_state_で_CHASE_に_遷移し_target_を_保持(self) -> None:
        """CHASE 遷移後、is_chasing と chase_target_id が一致する。"""
        agg = _aggregate()
        target = WorldObjectId.create(7777)
        agg.enter_chase_state(target_id=target, last_known_spot_id=SpotId.create(1))
        assert agg.is_chasing() is True
        assert agg.chase_target_id() == target

    def test_chase_中でないとき_chase_target_id_は_None(self) -> None:
        """CHASE 状態でない場合は chase_target_id が None を返す。"""
        agg = _aggregate()
        assert agg.chase_target_id() is None

    def test_DEAD_状態では_no_op(self) -> None:
        """死亡済みなら CHASE 遷移しない。"""
        agg = _aggregate(status=MonsterStatusEnum.DEAD)
        agg.enter_chase_state(
            target_id=WorldObjectId.create(7777),
            last_known_spot_id=SpotId.create(1),
        )
        assert agg.is_chasing() is False


class TestClearBehaviorState:
    """clear_behavior_state_to_idle で FLEE / CHASE が解除される。"""

    def test_FLEE_を_IDLE_に_クリアする(self) -> None:
        """FLEE → clear → IDLE。"""
        agg = _aggregate()
        agg.enter_flee_state(WorldTick(10), duration_ticks=3)
        agg.clear_behavior_state_to_idle()
        assert agg.behavior_state == BehaviorStateEnum.IDLE
        assert agg.is_fleeing(WorldTick(10)) is False

    def test_CHASE_を_IDLE_に_クリアする(self) -> None:
        """CHASE → clear → IDLE。"""
        agg = _aggregate()
        agg.enter_chase_state(
            target_id=WorldObjectId.create(7777),
            last_known_spot_id=SpotId.create(1),
        )
        agg.clear_behavior_state_to_idle()
        assert agg.behavior_state == BehaviorStateEnum.IDLE
        assert agg.is_chasing() is False

"""MonsterReactionHandler の multi-spot CHASE 統合テスト (PR (a))。

target が他 spot に居る場合、BFS で next hop を計算し 1 spot 移動する挙動を
検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.monster.services.monster_reaction_handler import (
    MonsterReactionHandler,
)
from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    BehaviorStateEnum,
    MonsterFactionEnum,
    MonsterStatusEnum,
    ReactionPolicyEnum,
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
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAttackedPlayerInSpotEvent,
    MonsterPredatedMonsterInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)
SPOT_B = SpotId.create(2)
SPOT_C = SpotId.create(3)


def _node(spot_id: SpotId) -> SpotNode:
    return SpotNode(
        spot_id=spot_id, name=f"spot{spot_id.value}", description="",
        category=SpotCategoryEnum.OTHER, parent_id=None,
        atmosphere=SpotAtmosphere(
            lighting=LightingEnum.BRIGHT, sound_ambient=None,
            temperature=TemperatureEnum.NORMAL, smell=None,
        ),
    )


def _conn(connection_id: int, from_id: SpotId, to_id: SpotId) -> SpotConnection:
    return SpotConnection(
        connection_id=ConnectionId.create(connection_id),
        from_spot_id=from_id, to_spot_id=to_id,
        name="edge", description="", travel_ticks=1,
        is_bidirectional=False, passage=Passage.open(),
    )


def _three_spot_chain_graph() -> SpotGraphAggregate:
    """A → B → C の直線グラフ。"""
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(_node(SPOT_A))
    g.add_spot(_node(SPOT_B))
    g.add_spot(_node(SPOT_C))
    g.add_connection(_conn(10, SPOT_A, SPOT_B))
    g.add_connection(_conn(20, SPOT_B, SPOT_C))
    g.add_connection(_conn(30, SPOT_B, SPOT_A))  # reverse
    g.add_connection(_conn(40, SPOT_C, SPOT_B))
    return g


def _template(
    *,
    reaction: ReactionPolicyEnum = ReactionPolicyEnum.ALWAYS_RETALIATE,
    flee_grace_ticks: int = 10,
) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        base_stats=BaseStats(
            max_hp=20, max_mp=0, attack=4,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.NEUTRAL,
        description="A wolf.",
        reaction_to_attack=reaction,
        flee_grace_ticks=flee_grace_ticks,
    )


def _monster() -> MonsterAggregate:
    return MonsterAggregate(
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


def _player(player_id_value: int = 1):
    p = MagicMock()
    p.player_id = PlayerId(player_id_value)
    type(p).is_down = property(lambda self: False)
    p.apply_damage.side_effect = lambda damage: None
    return p


def _make_handler(*, player=None, world_flags=frozenset()):
    monster_repo = MagicMock()
    player_repo = MagicMock()
    if player is not None:
        player_repo.find_by_id.return_value = player
    spot_repo = MagicMock()
    orchestrator = SpotAttackOrchestrator(
        spot_graph_repository=spot_repo,
        monster_repository=monster_repo,
        player_status_repository=player_repo,
    )
    handler = MonsterReactionHandler(
        monster_repository=monster_repo,
        player_status_repository=player_repo,
        attack_orchestrator=orchestrator,
        force_wander_fn=MagicMock(return_value=False),
        world_flags_provider=lambda: world_flags,
    )
    return handler, monster_repo


class TestMultiSpotChasePlayer:
    """target が player で他 spot に居る場合、BFS で 1 hop 進む。"""

    def test_隣接_spot_の_player_に_向かって_1hop_移動する(self) -> None:
        """A に居る monster が、B に居る player を CHASE 中なら 1 tick で B へ移動。"""
        player = _player(player_id_value=7)
        handler, monster_repo = _make_handler(player=player)
        monster = _monster()
        ref = AttackerRef.of_player(player.player_id)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_A)

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.place_entity(EntityId.create(player.player_id.value), SPOT_B)

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        assert result is not None
        assert result.executed is False
        assert result.reason == "chasing_to_other_spot"
        # monster が B へ 1 hop 移動
        assert graph.get_monster_spot(monster.monster_id) == SPOT_B
        # CHASE 継続
        assert monster.is_chasing() is True
        # state 永続化
        assert monster_repo.save.called

    def test_2hop_先の_player_に_向かって_1tick_目は_中継_spot_に移動(self) -> None:
        """A に居る monster が C に居る player を CHASE → 1 tick 目で B に移動。"""
        player = _player(player_id_value=7)
        handler, _ = _make_handler(player=player)
        monster = _monster()
        ref = AttackerRef.of_player(player.player_id)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_A)

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.place_entity(EntityId.create(player.player_id.value), SPOT_C)

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        assert result is not None
        # 中継 B へ移動
        assert graph.get_monster_spot(monster.monster_id) == SPOT_B
        assert monster.is_chasing() is True

    def test_target_が_graph_に_居なければ_IDLE_に_戻る(self) -> None:
        """player が graph 上のどこにも居なければ追跡諦める。"""
        handler, _ = _make_handler(player=None)
        monster = _monster()
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_A)

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        # player を graph に配置しない

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        assert result is None
        assert monster.is_chasing() is False
        # monster は同 spot に留まる
        assert graph.get_monster_spot(monster.monster_id) == SPOT_A


class TestMultiSpotChaseLastKnownUpdate:
    """multi-spot 移動時に `last_observed_target_spot_id` が更新される。"""

    def test_1hop_移動後の_last_observed_target_spot_id_は_target_spot_を_指す(self) -> None:
        """A→B 移動後、state.last_observed_target_spot_id は target が居る B (or 探索先) を指す。

        現実装では `update_chase_last_observed_target_spot(target_spot)` を呼ぶため
        `B` (target が居る spot) が記録される。"""
        player = _player(player_id_value=7)
        handler, _ = _make_handler(player=player)
        monster = _monster()
        ref = AttackerRef.of_player(player.player_id)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_A)

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.place_entity(EntityId.create(player.player_id.value), SPOT_B)

        handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        # 内部 state の last_observed_target_spot_id が B を指す
        assert monster._behavior_state.last_observed_target_spot_id == SPOT_B


class TestMultiSpotChaseAttackOnSameSpot:
    """target が同 spot に居る場合は移動せず攻撃する (既存挙動の維持)。"""

    def test_同_spot_の_player_には_攻撃_event_が_発火し_移動しない(self) -> None:
        player = _player(player_id_value=7)
        handler, _ = _make_handler(player=player)
        # ENEMY faction が必要
        monster = MonsterAggregate(
            monster_id=MonsterId.create(101),
            template=MonsterTemplate(
                template_id=MonsterTemplateId.create(1),
                name="Wolf",
                base_stats=BaseStats(
                    max_hp=20, max_mp=0, attack=4,
                    defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
                ),
                reward_info=RewardInfo(exp=1, gold=1),
                respawn_info=RespawnInfo(100, True),
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="A wolf.",
                reaction_to_attack=ReactionPolicyEnum.ALWAYS_RETALIATE,
                flee_grace_ticks=10,
            ),
            world_object_id=WorldObjectId.create(9001),
            skill_loadout=SkillLoadoutAggregate.create(
                SkillLoadoutId(1), owner_id=101,
                normal_capacity=4, awakened_capacity=2,
            ),
            status=MonsterStatusEnum.ALIVE,
            spawned_at_tick=WorldTick(0),
        )
        ref = AttackerRef.of_player(player.player_id)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_A)

        graph = _three_spot_chain_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.place_entity(EntityId.create(player.player_id.value), SPOT_A)
        graph.clear_events()

        result = handler.try_react(monster, graph, SPOT_A, WorldTick(10))

        assert result is not None
        # 攻撃 event が発火、monster は同 spot に留まる
        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAttackedPlayerInSpotEvent)
        ]
        assert len(events) == 1
        assert graph.get_monster_spot(monster.monster_id) == SPOT_A

class TestMultiSpotChaseMonster:
    """target が monster (player ではなく) でも multi-spot 追跡できる。"""

    def test_隣接_spot_の_monster_に_向かって_1hop_移動する(self) -> None:
        """A に居る attacker が、B に居る target_monster を CHASE 中なら B へ 1 hop 移動。"""
        handler, monster_repo = _make_handler(player=None)
        attacker = _monster()
        # target も同じ template だが別 monster_id
        target = MonsterAggregate(
            monster_id=MonsterId.create(202),
            template=_template(),
            world_object_id=WorldObjectId.create(9202),
            skill_loadout=SkillLoadoutAggregate.create(
                SkillLoadoutId(202), owner_id=202,
                normal_capacity=4, awakened_capacity=2,
            ),
            status=MonsterStatusEnum.ALIVE,
            spawned_at_tick=WorldTick(0),
        )
        ref = AttackerRef.of_monster(target.monster_id)
        attacker.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        attacker.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_A)

        graph = _three_spot_chain_graph()
        graph.place_monster(attacker.monster_id, SPOT_A)
        graph.place_monster(target.monster_id, SPOT_B)

        result = handler.try_react(attacker, graph, SPOT_A, WorldTick(10))

        assert result is not None
        assert result.executed is False
        assert result.reason == "chasing_to_other_spot"
        # attacker が B へ 1 hop 移動
        assert graph.get_monster_spot(attacker.monster_id) == SPOT_B
        assert attacker.is_chasing() is True

    def test_target_monster_が_graph_に_居なければ_IDLE_に_戻る(self) -> None:
        """target_monster が graph 上に居なければ追跡諦める。"""
        handler, _ = _make_handler(player=None)
        attacker = _monster()
        ref = AttackerRef.of_monster(MonsterId.create(999))  # 居ない monster
        attacker.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        attacker.enter_chase_state(attacker_ref=ref, last_observed_target_spot_id=SPOT_A)

        graph = _three_spot_chain_graph()
        graph.place_monster(attacker.monster_id, SPOT_A)
        # target を graph に配置しない

        result = handler.try_react(attacker, graph, SPOT_A, WorldTick(10))

        assert result is None
        assert attacker.is_chasing() is False
        assert graph.get_monster_spot(attacker.monster_id) == SPOT_A

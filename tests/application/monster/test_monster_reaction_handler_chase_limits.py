"""MonsterReactionHandler の CHASE 距離 / tick 上限テスト (Phase 4b PR c)。

検証範囲:
- `chase_max_distance` を超える target は追跡不可 → IDLE
- `chase_max_distance=0` は無制限と扱われる
- `chase_max_ticks` 超過で CHASE 状態を諦める
- `chase_max_ticks=0` は無制限と扱われる
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
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)


def _node(spot_id_int: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(spot_id_int),
        name=f"spot{spot_id_int}", description="",
        category=SpotCategoryEnum.OTHER, parent_id=None,
        atmosphere=SpotAtmosphere(
            lighting=LightingEnum.BRIGHT, sound_ambient=None,
            temperature=TemperatureEnum.NORMAL, smell=None,
        ),
    )


def _conn(connection_id: int, from_id: int, to_id: int) -> SpotConnection:
    return SpotConnection(
        connection_id=ConnectionId.create(connection_id),
        from_spot_id=SpotId.create(from_id), to_spot_id=SpotId.create(to_id),
        name="edge", description="", travel_ticks=1,
        is_bidirectional=False, passage=Passage.open(),
    )


def _long_chain_graph(num_spots: int) -> SpotGraphAggregate:
    """1 → 2 → 3 → ... → num_spots の直線グラフ。"""
    g = SpotGraphAggregate.empty(GRAPH_ID)
    for i in range(1, num_spots + 1):
        g.add_spot(_node(i))
    cid = 100
    for i in range(1, num_spots):
        g.add_connection(_conn(cid, i, i + 1))
        cid += 1
    return g


def _template(
    *,
    chase_max_distance: int = 5,
    chase_max_ticks: int = 20,
) -> MonsterTemplate:
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
        reaction_to_attack=ReactionPolicyEnum.ALWAYS_RETALIATE,
        flee_grace_ticks=999,  # この PR では grace に引っかからないよう大きく
        chase_search_ticks=0,  # search phase は分離してテスト済みなので無効化
        chase_max_distance=chase_max_distance,
        chase_max_ticks=chase_max_ticks,
    )


def _monster(template: MonsterTemplate) -> MonsterAggregate:
    return MonsterAggregate(
        monster_id=MonsterId.create(101),
        template=template,
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


def _make_handler(*, player=None):
    monster_repo = MagicMock()
    player_repo = MagicMock()
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
        world_flags_provider=lambda: frozenset(),
    )
    return handler, monster_repo


class TestChaseMaxDistance:
    """chase_max_distance を超える target は追跡できない。"""

    def test_2hop_max_distance_one_bfs_idle(self) -> None:
        """1 → 2 → 3 のグラフで monster は 1、target は 3、max_distance=1
        では到達不可と判定 → CHASE 解除。"""
        player = _player(player_id_value=7)
        handler, _ = _make_handler(player=player)
        monster = _monster(_template(chase_max_distance=1))
        ref = AttackerRef.of_player(player.player_id)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(
            attacker_ref=ref,
            last_observed_target_spot_id=SpotId.create(1),
            current_tick=WorldTick(9),
        )

        graph = _long_chain_graph(3)
        graph.place_monster(monster.monster_id, SpotId.create(1))
        graph.place_entity(EntityId.create(player.player_id.value), SpotId.create(3))

        result = handler.try_react(
            monster, graph, SpotId.create(1), WorldTick(10),
        )

        assert result is None
        assert monster.is_chasing() is False
        # monster は移動していない
        assert graph.get_monster_spot(monster.monster_id) == SpotId.create(1)

    def test_advances_2hop_max_distance_two_1hop(self) -> None:
        """同じグラフで max_distance=2 なら BFS 成功 → 中継 spot へ 1 hop。"""
        player = _player(player_id_value=7)
        handler, _ = _make_handler(player=player)
        monster = _monster(_template(chase_max_distance=2))
        ref = AttackerRef.of_player(player.player_id)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(
            attacker_ref=ref,
            last_observed_target_spot_id=SpotId.create(1),
            current_tick=WorldTick(9),
        )

        graph = _long_chain_graph(3)
        graph.place_monster(monster.monster_id, SpotId.create(1))
        graph.place_entity(EntityId.create(player.player_id.value), SpotId.create(3))

        result = handler.try_react(
            monster, graph, SpotId.create(1), WorldTick(10),
        )

        assert result is not None
        assert result.reason == "chasing_to_other_spot"
        # 1 hop 進んで中継 spot 2 に居る
        assert graph.get_monster_spot(monster.monster_id) == SpotId.create(2)

    def test_max_distance_zero(self) -> None:
        """max_distance=0 を指定すると BFS が無制限で全 spot を探索する。"""
        player = _player(player_id_value=7)
        handler, _ = _make_handler(player=player)
        monster = _monster(_template(chase_max_distance=0))
        ref = AttackerRef.of_player(player.player_id)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(9), attacker_ref=ref,
        )
        monster.enter_chase_state(
            attacker_ref=ref,
            last_observed_target_spot_id=SpotId.create(1),
            current_tick=WorldTick(9),
        )

        # 5 hop 離れていても無制限なので追跡できる
        graph = _long_chain_graph(6)
        graph.place_monster(monster.monster_id, SpotId.create(1))
        graph.place_entity(EntityId.create(player.player_id.value), SpotId.create(6))

        result = handler.try_react(
            monster, graph, SpotId.create(1), WorldTick(10),
        )

        assert result is not None
        assert result.reason == "chasing_to_other_spot"
        assert graph.get_monster_spot(monster.monster_id) == SpotId.create(2)


class TestChaseMaxTicks:
    """chase_max_ticks 超過で CHASE 状態を諦める。"""

    def test_chase_after_max_ticks_idle(self) -> None:
        """`enter_chase_state` で開始 tick=10、`chase_max_ticks=5`、現 tick=16
        → 経過 6 > 5 で諦めて IDLE。"""
        player = _player(player_id_value=7)
        handler, _ = _make_handler(player=player)
        monster = _monster(_template(chase_max_ticks=5))
        ref = AttackerRef.of_player(player.player_id)
        # last_attacked_tick は更新せず flee_grace_ticks には引っかからないよう。
        # その代わり grace_ticks=999 なので grace は事実上発動しない。
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(10), attacker_ref=ref,
        )
        monster.enter_chase_state(
            attacker_ref=ref,
            last_observed_target_spot_id=SpotId.create(1),
            current_tick=WorldTick(10),  # CHASE 開始 tick
        )

        graph = _long_chain_graph(2)
        graph.place_monster(monster.monster_id, SpotId.create(1))
        graph.place_entity(EntityId.create(player.player_id.value), SpotId.create(2))

        # chase_max_ticks=5、開始 tick=10、現 tick=16 → 経過 6 > 5
        result = handler.try_react(
            monster, graph, SpotId.create(1), WorldTick(16),
        )

        assert result is None
        assert monster.is_chasing() is False

    def test_chase_after_tick(self) -> None:
        """開始 tick=10、現 tick=11、max_ticks=5 → 経過 1 で継続。"""
        player = _player(player_id_value=7)
        handler, _ = _make_handler(player=player)
        monster = _monster(_template(chase_max_ticks=5))
        ref = AttackerRef.of_player(player.player_id)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(10), attacker_ref=ref,
        )
        monster.enter_chase_state(
            attacker_ref=ref,
            last_observed_target_spot_id=SpotId.create(1),
            current_tick=WorldTick(10),
        )

        graph = _long_chain_graph(2)
        graph.place_monster(monster.monster_id, SpotId.create(1))
        graph.place_entity(EntityId.create(player.player_id.value), SpotId.create(2))

        result = handler.try_react(
            monster, graph, SpotId.create(1), WorldTick(11),
        )

        # 1 hop 追跡継続
        assert result is not None
        assert result.reason == "chasing_to_other_spot"
        assert monster.is_chasing() is True

    def test_boundary_max_ticks(self) -> None:
        """`chase_max_ticks=5`、開始 tick=10、現 tick=15 (経過ちょうど 5) は
        まだ CHASE 継続 (`>` で実装しているため)。"""
        player = _player(player_id_value=7)
        handler, _ = _make_handler(player=player)
        monster = _monster(_template(chase_max_ticks=5))
        ref = AttackerRef.of_player(player.player_id)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(10), attacker_ref=ref,
        )
        monster.enter_chase_state(
            attacker_ref=ref,
            last_observed_target_spot_id=SpotId.create(1),
            current_tick=WorldTick(10),
        )

        graph = _long_chain_graph(2)
        graph.place_monster(monster.monster_id, SpotId.create(1))
        graph.place_entity(EntityId.create(player.player_id.value), SpotId.create(2))

        result = handler.try_react(
            monster, graph, SpotId.create(1), WorldTick(15),
        )

        assert result is not None
        assert result.reason == "chasing_to_other_spot"
        assert monster.is_chasing() is True

    def test_search_max_ticks_exceeds_idle(self) -> None:
        """探索フェーズ (chase_search_ticks=3) 中に `chase_max_ticks=4` を
        超えたら諦める。"""
        handler, _ = _make_handler(player=None)
        # search 中に超過する設定: chase_max_ticks=4
        template = MonsterTemplate(
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
            reaction_to_attack=ReactionPolicyEnum.ALWAYS_RETALIATE,
            flee_grace_ticks=999,
            chase_search_ticks=10,  # 探索フェーズを長くして max_ticks に先に当てる
            chase_max_distance=5,
            chase_max_ticks=4,
        )
        monster = _monster(template)
        ref = AttackerRef.of_player(PlayerId(7))
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(10), attacker_ref=ref,
        )
        monster.enter_chase_state(
            attacker_ref=ref,
            last_observed_target_spot_id=SpotId.create(1),
            current_tick=WorldTick(10),
        )
        # 既に探索フェーズ中の状態にする
        monster.start_chase_search(8)  # まだ timer 残ってる

        graph = _long_chain_graph(2)
        graph.place_monster(monster.monster_id, SpotId.create(1))
        # player は graph に居ない (= search 経路に入る)

        # max_ticks=4、開始 tick=10、現 tick=15 → 経過 5 > 4 で IDLE
        result = handler.try_react(
            monster, graph, SpotId.create(1), WorldTick(15),
        )

        assert result is None
        assert monster.is_chasing() is False

    def test_chase_max_ticks_zero(self) -> None:
        """`chase_max_ticks=0` なら経過 100 tick でも CHASE 継続。"""
        player = _player(player_id_value=7)
        handler, _ = _make_handler(player=player)
        monster = _monster(_template(chase_max_ticks=0))
        ref = AttackerRef.of_player(player.player_id)
        monster.record_attacked_by_in_spot(
            current_tick=WorldTick(10), attacker_ref=ref,
        )
        monster.enter_chase_state(
            attacker_ref=ref,
            last_observed_target_spot_id=SpotId.create(1),
            current_tick=WorldTick(10),
        )

        graph = _long_chain_graph(2)
        graph.place_monster(monster.monster_id, SpotId.create(1))
        graph.place_entity(EntityId.create(player.player_id.value), SpotId.create(2))

        # 100 tick 経過しても追跡継続
        result = handler.try_react(
            monster, graph, SpotId.create(1), WorldTick(110),
        )

        assert result is not None
        assert result.reason == "chasing_to_other_spot"
        assert monster.is_chasing() is True


class TestChaseStartedAtTick:
    """`MonsterAggregate.chase_started_at_tick` プロパティの境界。"""

    def test_returns_chase_tick(self) -> None:
        """CHASE 中なら開始 tick を返す。"""
        monster = _monster(_template())
        ref = AttackerRef.of_player(PlayerId(7))
        monster.enter_chase_state(
            attacker_ref=ref,
            last_observed_target_spot_id=SpotId.create(1),
            current_tick=WorldTick(42),
        )
        assert monster.chase_started_at_tick == WorldTick(42)

    def test_chase_none(self) -> None:
        """CHASE でなければ None。"""
        monster = _monster(_template())
        assert monster.chase_started_at_tick is None

    def test_clear_none(self) -> None:
        """clear すると None。"""
        monster = _monster(_template())
        ref = AttackerRef.of_player(PlayerId(7))
        monster.enter_chase_state(
            attacker_ref=ref,
            last_observed_target_spot_id=SpotId.create(1),
            current_tick=WorldTick(42),
        )
        monster.clear_behavior_state_to_idle()
        assert monster.chase_started_at_tick is None

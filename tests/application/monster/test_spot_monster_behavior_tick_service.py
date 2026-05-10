"""SpotMonsterBehaviorTickService の統合テスト。

検証範囲:
- スポットに居る敵対モンスターが、同スポットの最初の生存プレイヤーに攻撃を当てる
- cooldown 中のモンスターは skip
- 視認できないと攻撃せず event も発火しない
- 攻撃成立時 MonsterAttackedPlayerInSpotEvent が SpotGraphAggregate に追加される
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.monster.services.spot_monster_behavior_tick_service import (
    SpotMonsterBehaviorTickService,
)
from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAttackedPlayerInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)


def _node(*, lighting: LightingEnum = LightingEnum.BRIGHT) -> SpotNode:
    """テスト用の SpotNode（明るさを制御可能）。"""
    return SpotNode(
        spot_id=SPOT_A,
        name="森の入口",
        description="",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
        atmosphere=SpotAtmosphere(
            lighting=lighting,
            sound_ambient=None,
            temperature=TemperatureEnum.NORMAL,
            smell=None,
        ),
    )


def _make_graph(*, lighting: LightingEnum = LightingEnum.BRIGHT) -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(_node(lighting=lighting))
    return g


def _make_monster(
    *,
    monster_id_value: int = 101,
    can_attack: bool = True,
    has_dark_vision: bool = False,
    faction: MonsterFactionEnum = MonsterFactionEnum.ENEMY,
    attack: int = 5,
    idle_wander_chance: float = 0.0,
    ecology_type=None,
):
    """domain service が触る属性だけ持つ最小 mock。

    既存 attack-only テストの挙動を維持するため、デフォルトでは
    `idle_wander_chance=0.0` で wander を完全に無効化している。wander の
    挙動を検証するテストは個別に明示的に値を設定する。
    """
    from ai_rpg_world.domain.monster.enum.monster_enum import EcologyTypeEnum
    monster = MagicMock()
    # graph.move_monster は monster.monster_id を辞書キーとして使うため、
    # 実 MonsterId 値オブジェクトを設定する必要がある（MagicMock 自動値だと
    # graph 側のルックアップが失敗する）。
    monster.monster_id = MonsterId.create(monster_id_value)
    monster.template.faction = faction
    monster.template.has_dark_vision = has_dark_vision
    monster.template.base_stats.attack = attack
    monster.template.idle_wander_chance = idle_wander_chance
    monster.template.ecology_type = ecology_type or EcologyTypeEnum.NORMAL
    # Phase 3a 飢餓系: 既存テストの挙動を維持するためデフォルトで無効化
    # （`starvation_ticks=0` と `hunger_increase_per_tick=0` の二重 guard）。
    monster.template.starvation_ticks = 0
    monster.template.hunger_increase_per_tick = 0.0
    monster.template.hunger_decrease_on_feed = 0.0
    monster.template.forage_threshold = 1.0
    monster.template.preferred_feed_item_spec_ids = frozenset()
    monster.status = MonsterStatusEnum.ALIVE
    monster.can_attack_now.return_value = can_attack
    # Phase 4a 反撃/逃走系: 既存テスト挙動の維持。MagicMock の自動値は truthy
    # なので明示的に「反応しない」値を設定する。
    from ai_rpg_world.domain.monster.enum.monster_enum import (
        BehaviorStateEnum,
        ReactionPolicyEnum,
    )
    monster.is_fleeing.return_value = False
    monster.is_chasing.return_value = False
    monster.behavior_state = BehaviorStateEnum.IDLE
    monster.last_attacked_tick = None
    monster.last_attacker_ref = None
    monster.template.reaction_to_attack = ReactionPolicyEnum.PASSIVE
    monster.template.flee_grace_ticks = 3
    monster.template.flee_threshold = 0.3
    return monster


def _make_player(*, player_id_value: int = 1, is_down: bool = False):
    player = MagicMock()
    player.player_id = PlayerId(player_id_value)
    state = {"down": is_down}
    type(player).is_down = property(lambda self: state["down"])

    def _apply(damage: int) -> None:
        # 致命でもダウンしない単純化（個別テストで切り替え）。
        pass

    player.apply_damage.side_effect = _apply
    return player


class TestAttackHappens:
    """敵対モンスターが視認できる相手を攻撃する。"""

    def test_攻撃成立時に_graph_も_save(self) -> None:
        """attack 成立後は spot_graph_repository.save(graph) が呼ばれる。

        graph aggregate に追加した MonsterAttackedPlayerInSpotEvent が観測
        パイプラインに到達するために必須（save なしだと event がメモリ上で消失）。
        """
        graph = _make_graph()
        monster = _make_monster()
        player = _make_player()
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.place_entity(EntityId.create(1), SPOT_A)
        graph.clear_events()

        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        monster_repo = MagicMock()
        monster_repo.find_by_id.return_value = monster
        player_repo = MagicMock()
        player_repo.find_by_id.return_value = player

        svc = SpotMonsterBehaviorTickService(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
            attack_orchestrator=SpotAttackOrchestrator(
                spot_graph_repository=spot_repo,
                monster_repository=monster_repo,
                player_status_repository=player_repo,
            ),
        )

        svc.tick(WorldTick(10))

        spot_repo.save.assert_called_once_with(graph)

    def test_attack_未発生なら_graph_は_save_スキップ(self) -> None:
        """attack が一度も成立しなければ graph.save はスキップされる（無駄な永続化を避ける）。"""
        graph = _make_graph()
        # cooldown 中で attack しないモンスター
        monster = _make_monster(can_attack=False)
        player = _make_player()
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.place_entity(EntityId.create(1), SPOT_A)
        graph.clear_events()

        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        monster_repo = MagicMock()
        monster_repo.find_by_id.return_value = monster
        player_repo = MagicMock()
        player_repo.find_by_id.return_value = player

        svc = SpotMonsterBehaviorTickService(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
            attack_orchestrator=SpotAttackOrchestrator(
                spot_graph_repository=spot_repo,
                monster_repository=monster_repo,
                player_status_repository=player_repo,
            ),
        )

        svc.tick(WorldTick(10))

        spot_repo.save.assert_not_called()

    def test_event_が発火し_player_と_monster_を_save(self) -> None:
        """攻撃成立で SpotGraphAggregate に event 追加 + repository.save が両方呼ばれる。"""
        graph = _make_graph()
        monster = _make_monster(attack=7)
        player = _make_player()

        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.place_entity(EntityId.create(1), SPOT_A)
        graph.clear_events()

        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        monster_repo = MagicMock()
        monster_repo.find_by_id.return_value = monster
        player_repo = MagicMock()
        player_repo.find_by_id.return_value = player

        svc = SpotMonsterBehaviorTickService(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
            attack_orchestrator=SpotAttackOrchestrator(
                spot_graph_repository=spot_repo,
                monster_repository=monster_repo,
                player_status_repository=player_repo,
            ),
        )

        outcomes = svc.tick(WorldTick(10))

        assert len(outcomes) == 1
        assert outcomes[0].executed is True
        assert outcomes[0].damage == 7
        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAttackedPlayerInSpotEvent)
        ]
        assert len(events) == 1
        assert events[0].damage == 7
        assert events[0].target_visible is True
        monster_repo.save.assert_called_once_with(monster)
        player_repo.save.assert_called_once_with(player)


class TestCooldownSkip:
    """cooldown 中のモンスターは tick で skip。"""

    def test_can_attack_now_false_は_event発火なし(self) -> None:
        """can_attack_now=False のモンスターは event を発火しない。"""
        graph = _make_graph()
        monster = _make_monster(can_attack=False)
        player = _make_player()
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.place_entity(EntityId.create(1), SPOT_A)
        graph.clear_events()

        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        monster_repo = MagicMock()
        monster_repo.find_by_id.return_value = monster
        player_repo = MagicMock()
        player_repo.find_by_id.return_value = player

        svc = SpotMonsterBehaviorTickService(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
            attack_orchestrator=SpotAttackOrchestrator(
                spot_graph_repository=spot_repo,
                monster_repository=monster_repo,
                player_status_repository=player_repo,
            ),
        )

        svc.tick(WorldTick(10))

        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAttackedPlayerInSpotEvent)
        ]
        assert events == []
        player.apply_damage.assert_not_called()


class TestDarknessGate:
    """暗闇 + dark_vision 無しは攻撃しない。dark_vision ありなら攻撃するが target_visible=False。"""

    def test_暗闇_かつ_dark_vision無しは攻撃しない(self) -> None:
        """DARK で dark_vision なし → event 発火なし。"""
        graph = _make_graph(lighting=LightingEnum.DARK)
        monster = _make_monster(has_dark_vision=False)
        player = _make_player()
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.place_entity(EntityId.create(1), SPOT_A)
        graph.clear_events()

        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        monster_repo = MagicMock()
        monster_repo.find_by_id.return_value = monster
        player_repo = MagicMock()
        player_repo.find_by_id.return_value = player

        svc = SpotMonsterBehaviorTickService(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
            attack_orchestrator=SpotAttackOrchestrator(
                spot_graph_repository=spot_repo,
                monster_repository=monster_repo,
                player_status_repository=player_repo,
            ),
        )

        svc.tick(WorldTick(10))

        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAttackedPlayerInSpotEvent)
        ]
        assert events == []

    def test_暗闇_かつ_dark_vision有りは_target_visible_false_で攻撃する(self) -> None:
        """DARK + dark_vision あり → 攻撃成立、ただし target_visible=False。"""
        graph = _make_graph(lighting=LightingEnum.DARK)
        monster = _make_monster(has_dark_vision=True, attack=4)
        player = _make_player()
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.place_entity(EntityId.create(1), SPOT_A)
        graph.clear_events()

        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        monster_repo = MagicMock()
        monster_repo.find_by_id.return_value = monster
        player_repo = MagicMock()
        player_repo.find_by_id.return_value = player

        svc = SpotMonsterBehaviorTickService(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
            attack_orchestrator=SpotAttackOrchestrator(
                spot_graph_repository=spot_repo,
                monster_repository=monster_repo,
                player_status_repository=player_repo,
            ),
        )

        svc.tick(WorldTick(10))

        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAttackedPlayerInSpotEvent)
        ]
        assert len(events) == 1
        assert events[0].target_visible is False


class TestNoTarget:
    """同スポットに敵対対象が居ない場合は何もしない。"""

    def test_プレイヤー不在は_event発火なし(self) -> None:
        """presence にプレイヤーが居なければ skip。"""
        graph = _make_graph()
        monster = _make_monster()
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.clear_events()

        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        monster_repo = MagicMock()
        monster_repo.find_by_id.return_value = monster
        player_repo = MagicMock()
        player_repo.find_by_id.return_value = None  # presence にも居ない

        svc = SpotMonsterBehaviorTickService(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
            attack_orchestrator=SpotAttackOrchestrator(
                spot_graph_repository=spot_repo,
                monster_repository=monster_repo,
                player_status_repository=player_repo,
            ),
        )

        outcomes = svc.tick(WorldTick(10))

        assert outcomes == []
        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAttackedPlayerInSpotEvent)
        ]
        assert events == []


class TestNonHostile:
    """neutral / ally のモンスターは tick で attack しない。"""

    def test_neutral_は事前スクリーニングでスキップ(self) -> None:
        """faction=NEUTRAL は can_attack_now すら呼ばれない（最適化）。"""
        graph = _make_graph()
        monster = _make_monster(faction=MonsterFactionEnum.NEUTRAL)
        player = _make_player()
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.place_entity(EntityId.create(1), SPOT_A)
        graph.clear_events()

        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        monster_repo = MagicMock()
        monster_repo.find_by_id.return_value = monster
        player_repo = MagicMock()
        player_repo.find_by_id.return_value = player

        svc = SpotMonsterBehaviorTickService(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
            attack_orchestrator=SpotAttackOrchestrator(
                spot_graph_repository=spot_repo,
                monster_repository=monster_repo,
                player_status_repository=player_repo,
            ),
        )

        svc.tick(WorldTick(10))

        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAttackedPlayerInSpotEvent)
        ]
        assert events == []
        monster.can_attack_now.assert_not_called()


# ---------------------------------------------------------------------------
# Wander 行動 (Phase 1: ランダム徘徊)
# ---------------------------------------------------------------------------

import random as _random_mod  # noqa: E402

from ai_rpg_world.domain.monster.enum.monster_enum import EcologyTypeEnum  # noqa: E402
from ai_rpg_world.domain.world_graph.entity.spot_connection import (  # noqa: E402
    SpotConnection,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (  # noqa: E402
    MonsterAppearedAtSpotEvent,
    MonsterLeftSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import (  # noqa: E402
    ConnectionId,
)
from ai_rpg_world.domain.world_graph.value_object.passage import Passage  # noqa: E402


SPOT_B = SpotId.create(2)


def _make_two_spot_graph(*, traversable_to_b: bool = True) -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(_node(lighting=LightingEnum.BRIGHT))
    g.add_spot(
        SpotNode(
            spot_id=SPOT_B,
            name="Spot B",
            description="",
            category=SpotCategoryEnum.OTHER,
            parent_id=None,
        )
    )
    g.add_connection(
        SpotConnection(
            connection_id=ConnectionId.create(10),
            from_spot_id=SPOT_A,
            to_spot_id=SPOT_B,
            name="path",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage=(
                Passage.open() if traversable_to_b
                else Passage.open(traversable=False)
            ),
            passage_conditions=[],
        )
    )
    return g


def _make_svc(graph, monster, *, random_seed: int = 0):
    spot_repo = MagicMock()
    spot_repo.find_graph.return_value = graph
    monster_repo = MagicMock()
    monster_repo.find_by_id.return_value = monster
    player_repo = MagicMock()
    player_repo.find_by_id.return_value = None  # no players for wander tests
    return (
        SpotMonsterBehaviorTickService(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
            attack_orchestrator=SpotAttackOrchestrator(
                spot_graph_repository=spot_repo,
                monster_repository=monster_repo,
                player_status_repository=player_repo,
            ),
            random_source=_random_mod.Random(random_seed),
        ),
        spot_repo,
    )


class TestWanderBasic:
    """ランダム徘徊が `idle_wander_chance` で発火し、隣接 spot へ移動する。"""

    def test_chance_1_で必ず移動する(self) -> None:
        """idle_wander_chance=1.0 なら毎 tick 必ず passable 接続へ移動。"""
        graph = _make_two_spot_graph()
        monster = _make_monster(idle_wander_chance=1.0, can_attack=False)
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.clear_events()

        svc, spot_repo = _make_svc(graph, monster)
        svc.tick(WorldTick(10))

        # spot A から消えて spot B に居る
        assert graph.get_monster_spot(MonsterId.create(101)) == SPOT_B
        # Left + Appeared event の対が graph に積まれている
        events = graph.get_events()
        types = {type(e).__name__ for e in events}
        assert "MonsterLeftSpotEvent" in types
        assert "MonsterAppearedAtSpotEvent" in types
        # graph save が tick 末で呼ばれている
        spot_repo.save.assert_called_once_with(graph)

    def test_chance_0_では移動しない(self) -> None:
        """idle_wander_chance=0.0 なら徘徊試行せず position 維持。"""
        graph = _make_two_spot_graph()
        monster = _make_monster(idle_wander_chance=0.0, can_attack=False)
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.clear_events()

        svc, spot_repo = _make_svc(graph, monster)
        svc.tick(WorldTick(10))

        assert graph.get_monster_spot(MonsterId.create(101)) == SPOT_A
        spot_repo.save.assert_not_called()


class TestWanderEcology:
    """ecology_type による徘徊抑制。"""

    def test_ambush_は_chance_1_でも移動しない(self) -> None:
        """AMBUSH は待ち伏せ習性で徘徊しない（idle_wander_chance によらず）。"""
        graph = _make_two_spot_graph()
        monster = _make_monster(
            idle_wander_chance=1.0,
            can_attack=False,
            ecology_type=EcologyTypeEnum.AMBUSH,
        )
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.clear_events()

        svc, spot_repo = _make_svc(graph, monster)
        svc.tick(WorldTick(10))

        assert graph.get_monster_spot(MonsterId.create(101)) == SPOT_A
        spot_repo.save.assert_not_called()


class TestWanderPassageGate:
    """passage_conditions / traversable=False の通行不可は徘徊先から除外される。"""

    def test_traversable_false_は徘徊先から除外される(self) -> None:
        """traversable=False の接続しか無ければ徘徊しない。"""
        graph = _make_two_spot_graph(traversable_to_b=False)
        monster = _make_monster(idle_wander_chance=1.0, can_attack=False)
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.clear_events()

        svc, spot_repo = _make_svc(graph, monster)
        svc.tick(WorldTick(10))

        # 通行不可なので spot A に留まる
        assert graph.get_monster_spot(MonsterId.create(101)) == SPOT_A
        spot_repo.save.assert_not_called()


class TestAttackPriorityOverWander:
    """attack が成立する状況では wander を試みない（priority chain）。"""

    def test_attack_成立時は移動しない(self) -> None:
        """attack 成立 monster は同じ tick で wander 抽選すらしない。"""
        graph = _make_two_spot_graph()
        monster = _make_monster(idle_wander_chance=1.0, can_attack=True, attack=5)
        graph.place_monster(MonsterId.create(101), SPOT_A)
        graph.place_entity(EntityId.create(1), SPOT_A)
        graph.clear_events()

        # 攻撃ターゲット用 player
        player = MagicMock()
        player.player_id = PlayerId(1)
        state = {"down": False}
        type(player).is_down = property(lambda self: state["down"])
        player.apply_damage.side_effect = lambda d: None

        spot_repo = MagicMock()
        spot_repo.find_graph.return_value = graph
        monster_repo = MagicMock()
        monster_repo.find_by_id.return_value = monster
        player_repo = MagicMock()
        player_repo.find_by_id.return_value = player

        svc = SpotMonsterBehaviorTickService(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
            attack_orchestrator=SpotAttackOrchestrator(
                spot_graph_repository=spot_repo,
                monster_repository=monster_repo,
                player_status_repository=player_repo,
            ),
            random_source=_random_mod.Random(0),
        )
        outcomes = svc.tick(WorldTick(10))

        # 攻撃成立で位置は元のまま
        assert len(outcomes) == 1 and outcomes[0].executed is True
        assert graph.get_monster_spot(MonsterId.create(101)) == SPOT_A

"""SpotMonsterBehaviorTickService の飢餓 + 採食 (Phase 3a) テスト。

検証範囲:
- 飢餓無効テンプレ (starvation_ticks=0) では `tick_hunger` で何も起きない
- 飢餓有効テンプレでは hunger が tick ごとに進行する
- starvation 閾値超過で `monster.starve()` が呼ばれ MonsterDiedEvent 発火
- hunger >= forage_threshold + 同スポットに preferred 食材で採食発火
- hunger 不足では採食しない
- preferred マッチしないアイテムは食べない
- 採食で graph に MonsterAteGroundItemEvent + interior から item 削除
- spot_interior_repository 未注入で採食はスキップ
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
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import (
    MonsterTemplateId,
)
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
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
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAteGroundItemEvent,
)
from ai_rpg_world.domain.world_graph.value_object.ground_item import GroundItem
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)
MEAT_SPEC = ItemSpecId(99)
ROCK_SPEC = ItemSpecId(50)


def _hungry_template(
    *,
    starvation_ticks: int = 5,
    hunger_increase: float = 0.3,
    forage_threshold: float = 0.5,
    hunger_decrease_on_feed: float = 0.4,
    preferred: frozenset = frozenset({MEAT_SPEC}),
) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        base_stats=BaseStats(
            max_hp=10, max_mp=0, attack=2,
            defense=0, speed=1, critical_rate=0.0, evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.NEUTRAL,
        description="A wolf.",
        starvation_ticks=starvation_ticks,
        hunger_increase_per_tick=hunger_increase,
        hunger_starvation_threshold=1.0,
        forage_threshold=forage_threshold,
        hunger_decrease_on_feed=hunger_decrease_on_feed,
        preferred_feed_item_spec_ids=preferred,
        idle_wander_chance=0.0,  # wander で副作用が出ないように
    )


def _make_monster(template: MonsterTemplate) -> MonsterAggregate:
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


def _make_graph() -> SpotGraphAggregate:
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(
        SpotNode(
            spot_id=SPOT_A,
            name="Field",
            description="",
            category=SpotCategoryEnum.OTHER,
            parent_id=None,
        )
    )
    return g


def _make_svc(graph, monster, *, interior_repo=None):
    spot_repo = MagicMock()
    spot_repo.find_graph.return_value = graph
    monster_repo = MagicMock()
    monster_repo.find_by_id.return_value = monster
    player_repo = MagicMock()
    player_repo.find_by_id.return_value = None
    return SpotMonsterBehaviorTickService(
        spot_graph_repository=spot_repo,
        monster_repository=monster_repo,
        player_status_repository=player_repo,
        attack_orchestrator=SpotAttackOrchestrator(
            spot_graph_repository=spot_repo,
            monster_repository=monster_repo,
            player_status_repository=player_repo,
        ),
        spot_interior_repository=interior_repo,
    ), spot_repo, monster_repo


class TestHungerTick:
    """飢餓 tick の挙動。"""

    def test_starvation_ticks_ゼロでは_hunger_進行しない(self) -> None:
        """飢餓無効テンプレでは `_lifecycle_state.hunger` が変化しない。"""
        template = _hungry_template(
            starvation_ticks=0, hunger_increase=0.5
        )
        monster = _make_monster(template)
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        svc, _, _ = _make_svc(graph, monster)
        svc.tick(WorldTick(10))

        # 飢餓無効なので hunger は 0 のまま
        assert monster._lifecycle_state.hunger == 0.0

    def test_飢餓有効で_hunger_が増える(self) -> None:
        """`hunger_increase_per_tick` 分だけ hunger が増加する。"""
        template = _hungry_template(hunger_increase=0.3)
        monster = _make_monster(template)
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)

        svc, _, monster_repo = _make_svc(graph, monster)
        svc.tick(WorldTick(10))

        # 1 tick で 0.3 増えている
        assert abs(monster._lifecycle_state.hunger - 0.3) < 1e-6
        # monster_repo に save された
        monster_repo.save.assert_called()


class TestStarvationDeath:
    """飢餓死: 閾値超過で `monster.starve()` が呼ばれる。"""

    def test_starvation_閾値超過で_died_event(self) -> None:
        """starvation_ticks 超えるまで hunger が高いと MonsterDiedEvent が発火。"""
        # starvation_ticks=2, hunger=1.0 で即死スレッシュホールド
        template = _hungry_template(
            starvation_ticks=2,
            hunger_increase=1.0,  # 1 tick で max hunger に到達
        )
        monster = _make_monster(template)
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        monster.clear_events()

        svc, _, _ = _make_svc(graph, monster)
        # 2 tick で hunger が starvation_threshold に到達して時間カウントが進み starve
        svc.tick(WorldTick(10))
        svc.tick(WorldTick(11))
        svc.tick(WorldTick(12))

        died_events = [
            e for e in monster.get_events() if isinstance(e, MonsterDiedEvent)
        ]
        assert len(died_events) == 1
        assert monster.status != MonsterStatusEnum.ALIVE


class TestForage:
    """採食: 同スポットの preferred 食材を 1 個食べる。"""

    def test_hunger_閾値超過_かつ_preferred_食材ありで採食(self) -> None:
        """採食成立で MonsterAteGroundItemEvent + interior から item 消費。"""
        template = _hungry_template(
            starvation_ticks=10,
            hunger_increase=0.6,  # 1 tick で 0.6 → forage_threshold=0.5 超え
            forage_threshold=0.5,
            hunger_decrease_on_feed=0.4,
        )
        monster = _make_monster(template)
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.clear_events()

        # interior に肉を置く
        interior = SpotInterior(
            sub_locations=(),
            objects=(),
            ground_items=(
                GroundItem(
                    item_instance_id=ItemInstanceId(1001),
                    item_spec_id=MEAT_SPEC,
                ),
            ),
            discoverable_items=(),
        )
        interior_repo = MagicMock()
        interior_repo.find_by_spot_id.return_value = interior

        svc, spot_repo, monster_repo = _make_svc(
            graph, monster, interior_repo=interior_repo
        )
        svc.tick(WorldTick(10))

        # event が発火
        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAteGroundItemEvent)
        ]
        assert len(events) == 1
        assert events[0].item_spec_id == MEAT_SPEC
        assert events[0].item_instance_id == ItemInstanceId(1001)

        # interior が更新保存された (item が消えている)
        save_call = interior_repo.save.call_args
        saved_interior: SpotInterior = save_call[0][1]
        assert all(
            g.item_instance_id != ItemInstanceId(1001)
            for g in saved_interior.ground_items
        )

        # graph save も呼ばれた
        spot_repo.save.assert_called_once_with(graph)

    def test_hunger_未満では採食しない(self) -> None:
        """hunger < forage_threshold では採食試行しない。"""
        template = _hungry_template(
            starvation_ticks=10,
            hunger_increase=0.1,  # forage_threshold=0.5 に届かない
            forage_threshold=0.5,
        )
        monster = _make_monster(template)
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.clear_events()

        interior = SpotInterior(
            sub_locations=(),
            objects=(),
            ground_items=(
                GroundItem(
                    item_instance_id=ItemInstanceId(1001),
                    item_spec_id=MEAT_SPEC,
                ),
            ),
            discoverable_items=(),
        )
        interior_repo = MagicMock()
        interior_repo.find_by_spot_id.return_value = interior

        svc, _, _ = _make_svc(graph, monster, interior_repo=interior_repo)
        svc.tick(WorldTick(10))

        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAteGroundItemEvent)
        ]
        assert events == []
        interior_repo.save.assert_not_called()

    def test_preferred_外の食材は食べない(self) -> None:
        """preferred_feed_item_spec_ids にマッチしない item は食べない。"""
        template = _hungry_template(
            starvation_ticks=10,
            hunger_increase=0.6,
            forage_threshold=0.5,
            preferred=frozenset({MEAT_SPEC}),
        )
        monster = _make_monster(template)
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.clear_events()

        # 石しか置かれていない
        interior = SpotInterior(
            sub_locations=(),
            objects=(),
            ground_items=(
                GroundItem(
                    item_instance_id=ItemInstanceId(1002),
                    item_spec_id=ROCK_SPEC,
                ),
            ),
            discoverable_items=(),
        )
        interior_repo = MagicMock()
        interior_repo.find_by_spot_id.return_value = interior

        svc, _, _ = _make_svc(graph, monster, interior_repo=interior_repo)
        svc.tick(WorldTick(10))

        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAteGroundItemEvent)
        ]
        assert events == []

    def test_interior_repo_未注入では採食しない(self) -> None:
        """`spot_interior_repository=None` で採食機能がスキップされる。"""
        template = _hungry_template(
            starvation_ticks=10,
            hunger_increase=0.6,
            forage_threshold=0.5,
        )
        monster = _make_monster(template)
        graph = _make_graph()
        graph.place_monster(monster.monster_id, SPOT_A)
        graph.clear_events()

        # interior_repo を渡さない
        svc, _, _ = _make_svc(graph, monster, interior_repo=None)
        svc.tick(WorldTick(10))

        events = [
            e for e in graph.get_events()
            if isinstance(e, MonsterAteGroundItemEvent)
        ]
        assert events == []

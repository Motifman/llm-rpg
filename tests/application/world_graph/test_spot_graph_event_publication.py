"""スポットグラフ アプリケーションサービスからのイベント発火テスト。

interaction / exploration がそれぞれ EventPublisher 経由で
ドメインイベントを発火することを検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.spot_exploration_application_service import (
    SpotExplorationApplicationService,
)
from ai_rpg_world.application.world_graph.spot_exploration_progress_store import (
    InMemorySpotExplorationProgressStore,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotExploredEvent,
    SpotObjectInteractedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum


def _build_graph_with_entity(spot_id: SpotId, entity_id: EntityId) -> SpotGraphAggregate:
    """エンティティが1つのスポットに配置されたグラフを構築する。"""
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    node = SpotNode(spot_id=spot_id, name="テスト部屋", description="テスト用", category=SpotCategoryEnum.DUNGEON, parent_id=None)
    graph.add_spot(node)
    graph.place_entity(entity_id, spot_id)
    graph.clear_events()  # 配置イベントをクリア
    return graph


def _simple_object() -> SpotObject:
    """メッセージ表示のみのシンプルなオブジェクト"""
    return SpotObject(
        object_id=SpotObjectId.create(10),
        name="石碑",
        description="古い文字が刻まれている",
        object_type=SpotObjectTypeEnum.SIGN,
        state={},
        interactions=(
            InteractionDef(
                action_name="read",
                display_label="読む",
                preconditions=(),
                effects=(
                    InteractionEffect(
                        effect_type=InteractionEffectTypeEnum.SHOW_MESSAGE,
                        parameters={"message": "古代文字が書かれている"},
                    ),
                ),
            ),
        ),
    )


def _make_interior(obj: SpotObject) -> SpotInterior:
    return SpotInterior((), (obj,), (), ())


class TestInteractionEventPublication:
    """SpotInteractionApplicationService のイベント発火テスト"""

    def test_publishes_spot_object_interacted_event(self):
        """操作完了時に SpotObjectInteractedEvent が publish される"""
        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        interior = _make_interior(_simple_object())

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None
        item_spec_repo = MagicMock()
        event_publisher = MagicMock()

        svc = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=item_spec_repo,
            world_flag_state=MutableWorldFlagState(),
            event_publisher=event_publisher,
        )

        result = svc.execute_interaction(player_id, SpotObjectId.create(10), "read")

        # publish_all が呼ばれたことを確認
        event_publisher.publish_all.assert_called_once()
        published_events = event_publisher.publish_all.call_args[0][0]

        # SpotObjectInteractedEvent が含まれること
        interacted = [e for e in published_events if isinstance(e, SpotObjectInteractedEvent)]
        assert len(interacted) == 1
        assert interacted[0].entity_id == entity_id
        assert interacted[0].spot_id == spot_id
        assert interacted[0].object_id == SpotObjectId.create(10)
        assert interacted[0].action_name == "read"

    def test_no_event_when_publisher_is_none(self):
        """event_publisher=None でもエラーにならない（後方互換）"""
        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        interior = _make_interior(_simple_object())

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None

        svc = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=MagicMock(),
            world_flag_state=MutableWorldFlagState(),
            # event_publisher=None (デフォルト)
        )

        # エラーにならないこと
        result = svc.execute_interaction(player_id, SpotObjectId.create(10), "read")
        assert result.messages


class TestExplorationEventPublication:
    """SpotExplorationApplicationService のイベント発火テスト"""

    def test_publishes_spot_explored_event(self):
        """探索完了時に SpotExploredEvent が publish される"""
        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        interior = _make_interior(_simple_object())

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None
        event_publisher = MagicMock()

        svc = SpotExplorationApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=MagicMock(),
            world_flag_state=MutableWorldFlagState(),
            exploration_progress_store=InMemorySpotExplorationProgressStore(),
            event_publisher=event_publisher,
        )

        result = svc.explore_once(player_id)

        event_publisher.publish.assert_called_once()
        event = event_publisher.publish.call_args[0][0]
        assert isinstance(event, SpotExploredEvent)
        assert event.entity_id == entity_id
        assert event.spot_id == spot_id

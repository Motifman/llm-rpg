"""アイテム使用の観測テスト。

ConsumableUsedEvent が同スポットの他エージェントに観測として届き、
使用者本人には届かないことを検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.item_use_formatter import (
    ItemUseObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.recipient_strategies.item_use_recipient_strategy import (
    ItemUseRecipientStrategy,
)
from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum


def _build_graph_two_players_same_spot():
    """2人のプレイヤーが同じスポットにいるグラフ"""
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    spot = SpotNode(
        spot_id=SpotId.create(1),
        name="広場",
        description="中央広場",
        category=SpotCategoryEnum.TOWN,
        parent_id=None,
    )
    graph.add_spot(spot)
    graph.place_entity(EntityId.create(1), SpotId.create(1))
    graph.place_entity(EntityId.create(2), SpotId.create(1))
    graph.clear_events()
    return graph


def _build_graph_two_players_different_spots():
    """2人のプレイヤーが別々のスポットにいるグラフ"""
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    spot1 = SpotNode(spot_id=SpotId.create(1), name="広場", description="", category=SpotCategoryEnum.TOWN, parent_id=None)
    spot2 = SpotNode(spot_id=SpotId.create(2), name="裏路地", description="", category=SpotCategoryEnum.TOWN, parent_id=None)
    graph.add_spot(spot1)
    graph.add_spot(spot2)
    graph.place_entity(EntityId.create(1), SpotId.create(1))
    graph.place_entity(EntityId.create(2), SpotId.create(2))
    graph.clear_events()
    return graph


def _make_player_status_repo(player_ids):
    """find_all で指定プレイヤーを返すモック"""
    statuses = []
    for pid in player_ids:
        s = MagicMock()
        s.player_id = PlayerId(pid)
        statuses.append(s)
    repo = MagicMock()
    repo.find_all.return_value = statuses
    return repo


class TestItemUseRecipientStrategy:
    """ConsumableUsedEvent の配信先解決テスト"""

    def test_same_spot_other_player_receives(self):
        """同スポットの他プレイヤーが配信先になる"""
        graph = _build_graph_two_players_same_spot()
        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        player_status_repo = _make_player_status_repo([1, 2])

        strategy = ItemUseRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            spot_graph_repository=spot_graph_repo,
            player_status_repository=player_status_repo,
        )

        event = ConsumableUsedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=ItemSpecId(100),
        )

        assert strategy.supports(event)
        recipients = strategy.resolve(event)
        assert len(recipients) == 1
        assert recipients[0] == PlayerId(2)

    def test_actor_excluded(self):
        """使用者本人は配信先に含まれない"""
        graph = _build_graph_two_players_same_spot()
        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        player_status_repo = _make_player_status_repo([1, 2])

        strategy = ItemUseRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            spot_graph_repository=spot_graph_repo,
            player_status_repository=player_status_repo,
        )

        event = ConsumableUsedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=ItemSpecId(100),
        )

        recipients = strategy.resolve(event)
        assert PlayerId(1) not in recipients

    def test_different_spot_no_recipients(self):
        """別スポットのプレイヤーには届かない"""
        graph = _build_graph_two_players_different_spots()
        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        player_status_repo = _make_player_status_repo([1, 2])

        strategy = ItemUseRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            spot_graph_repository=spot_graph_repo,
            player_status_repository=player_status_repo,
        )

        event = ConsumableUsedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=ItemSpecId(100),
        )

        recipients = strategy.resolve(event)
        assert len(recipients) == 0


class TestItemUseFormatter:
    """ConsumableUsedEvent のフォーマットテスト"""

    def test_formats_item_use_event(self):
        """アイテム使用イベントが観測テキストに変換される"""
        name_resolver = ObservationNameResolver()
        name_resolver.player_name = lambda pid: "太郎" if pid.value == 1 else "花子"
        # 実 method 名 (`item_spec_name`) を mock すること。`item_name` は
        # ObservationNameResolver に存在しないため、ここで動的に生やすと
        # 実験 #27 と同型の本番 AttributeError をテストが隠蔽してしまう。
        name_resolver.item_spec_name = lambda spec_id: "回復ポーション"
        context = ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=None,
        )
        formatter = ItemUseObservationFormatter(context)

        event = ConsumableUsedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=ItemSpecId(100),
        )

        output = formatter.format(event, PlayerId(2))
        assert output is not None
        assert "太郎" in output.prose
        assert "回復ポーション" in output.prose
        assert output.observation_category == "social"

    def test_returns_none_for_other_events(self):
        """ConsumableUsedEvent 以外は None を返す"""
        context = ObservationFormatterContext(
            name_resolver=ObservationNameResolver(),
            item_repository=None,
        )
        formatter = ItemUseObservationFormatter(context)
        assert formatter.format("not_an_event", PlayerId(1)) is None

    def test_returns_none_when_recipient_is_actor(self):
        """使用者本人が受信者の場合は None を返す（ツール結果で完結するため観測対象外）"""
        name_resolver = ObservationNameResolver()
        name_resolver.player_name = lambda pid: "太郎"
        # 実 method 名 (`item_spec_name`) を mock すること。`item_name` は
        # ObservationNameResolver に存在しないため、ここで動的に生やすと
        # 実験 #27 と同型の本番 AttributeError をテストが隠蔽してしまう。
        name_resolver.item_spec_name = lambda spec_id: "回復ポーション"
        context = ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=None,
        )
        formatter = ItemUseObservationFormatter(context)

        event = ConsumableUsedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            item_spec_id=ItemSpecId(100),
        )

        assert formatter.format(event, PlayerId(1)) is None

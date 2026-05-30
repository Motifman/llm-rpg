"""スポットグラフ世界における drop / pickup の最小サービス。

タイルマップ時代の ItemDroppedFromInventoryDropHandler は ``physical_map``
依存で escape_game / spot-graph 世界では発火しない (escape_game_runtime
で ``physical_map_repository=None`` を渡している)。spot-graph 世界では
SpotInterior.ground_items にアイテムを置き、SpotInterior 経路で
プレイヤーが拾い直せる必要がある。

本サービスはそのための機械的動作 (インベントリ↔地面の状態遷移) と、
witness 最小版 (drop / pickup の事実を同スポットの他プレイヤーに観測として
配信する PlayerDroppedItemEvent / PlayerPickedUpItemEvent の発火) を担う。
LLM ツール配線は別経路で行う (本サービスは tool 経路にも runtime 直接呼び
出し経路にも共通で使われる)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.exception.player_exceptions import (
    ItemNotInSlotException,
)
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerDroppedItemEvent,
    PlayerPickedUpItemEvent,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.ground_item import GroundItem

_logger = logging.getLogger(__name__)


class ItemTransferException(Exception):
    """drop/pickup の境界条件違反 (プレイヤー未配置・地面に存在しない 等)。"""


@dataclass(frozen=True)
class ItemTransferResult:
    """drop/pickup の結果。messages はランナー/UI 用、instance_id は監査用。"""

    messages: tuple[str, ...]
    item_instance_id: ItemInstanceId
    spot_id: SpotId


class SpotGraphItemTransferService:
    """spot-graph 世界での drop / pickup を扱うアプリサービス。

    Phase 2 (witness 最小版): drop / pickup が成功したら同室の他プレイヤー向けに
    PlayerDroppedItemEvent / PlayerPickedUpItemEvent を発火する。観測パイプライン
    の recipient strategy が「同スポット・行為者除外」で配信する。
    event_publisher が None の構成では event を発火せず、機械的な状態遷移だけ
    行う (テスト・最小構成での後方互換)。
    """

    def __init__(
        self,
        *,
        spot_graph_repository: ISpotGraphRepository,
        player_inventory_repository: PlayerInventoryRepository,
        spot_interior_repository: ISpotInteriorRepository,
        item_repository: ItemRepository,
        event_publisher: Optional[object] = None,
    ) -> None:
        # spot-graph 世界では「プレイヤーがどこに居るか」は
        # PlayerStatusAggregate ではなく SpotGraphAggregate.get_entity_spot で
        # 解決する (status 側の current_spot_id は tile-map 由来で、
        # spot-graph runtime では更新されない)。
        self._spot_graph_repository = spot_graph_repository
        self._player_inventory_repository = player_inventory_repository
        self._spot_interior_repository = spot_interior_repository
        self._item_repository = item_repository
        # event_publisher は publish_all([event]) を持つ duck-typed オブジェクト。
        # 注入されない構成では event を発火せず、機械的な状態遷移だけ行う。
        self._event_publisher = event_publisher

    def set_event_publisher(self, event_publisher: Optional[object]) -> None:
        """event_publisher を後付けで注入する (二段構築用)。

        通常は constructor で渡すのが望ましいが、escape_game_runtime のように
        publisher が runtime 本体に依存して構築順序的に後になるケースで使う。
        """
        self._event_publisher = event_publisher

    def drop_item(self, player_id: PlayerId, slot_id: SlotId) -> ItemTransferResult:
        """指定スロットのアイテムをプレイヤーの現在地に落とす。

        ItemDroppedFromInventoryEvent は発火させない (tile-map handler が
        食ってしまうため)。代わりに本サービスが直接 SpotInterior に
        書き込む。
        """
        inventory = self._player_inventory_repository.find_by_id(player_id)
        if inventory is None:
            raise ItemTransferException(
                f"inventory not found for player {player_id.value}"
            )

        item_instance_id = inventory.get_item_instance_id_by_slot(slot_id)
        if item_instance_id is None:
            raise ItemNotInSlotException(
                f"No item in slot {slot_id.value}"
            )

        spot_id = self._resolve_current_spot(player_id)
        interior = self._spot_interior_repository.find_by_spot_id(spot_id)
        if interior is None:
            raise ItemTransferException(
                f"spot interior not found for spot {spot_id.value}"
            )

        item_aggregate = self._item_repository.find_by_id(item_instance_id)
        if item_aggregate is None:
            raise ItemTransferException(
                f"item aggregate not found for instance {item_instance_id.value}"
            )
        item_spec_id = item_aggregate.item_spec.item_spec_id

        # event を発火させない remove_item_for_storage を使う。
        # (drop_item() は ItemDroppedFromInventoryEvent を発火するが、現状
        # その listener は tile-map 専用なので拾わせない。)
        inventory.remove_item_for_storage(item_instance_id)
        self._player_inventory_repository.save(inventory)

        ground_item = GroundItem(
            item_instance_id=item_instance_id,
            item_spec_id=item_spec_id,
        )
        new_interior = interior.with_ground_item(ground_item)
        self._spot_interior_repository.save(spot_id, new_interior)

        # 表示名は inventory remove 前に確定させる必要があるが、ItemAggregate は
        # まだ item_repository に残っているのでここで OK。
        item_name = self._item_name_or_id(item_instance_id)

        # witness 最小版: 同室の他プレイヤーに観測として届ける。
        # 行為者本人には messages を ItemTransferResult で返し、観測ストリームには
        # 流さない (recipient strategy 側で actor exclusion される)。
        self._publish_event(
            PlayerDroppedItemEvent.create(
                aggregate_id=self._spot_graph_repository.find_graph().graph_id,
                aggregate_type="SpotGraphAggregate",
                entity_id=EntityId.create(int(player_id)),
                spot_id=spot_id,
                item_instance_id=item_instance_id,
                item_spec_id=item_spec_id,
                item_name=item_name,
            )
        )

        return ItemTransferResult(
            messages=(f"{item_name}を地面に置いた。",),
            item_instance_id=item_instance_id,
            spot_id=spot_id,
        )

    def pickup_item(
        self, player_id: PlayerId, item_instance_id: ItemInstanceId
    ) -> ItemTransferResult:
        """プレイヤーの現在地から指定アイテムを拾う。"""
        spot_id = self._resolve_current_spot(player_id)
        interior = self._spot_interior_repository.find_by_spot_id(spot_id)
        if interior is None:
            raise ItemTransferException(
                f"spot interior not found for spot {spot_id.value}"
            )

        ground_item = interior.find_ground_item(item_instance_id)
        if ground_item is None:
            raise ItemTransferException(
                f"ground item {item_instance_id.value} not found at spot "
                f"{spot_id.value}"
            )

        inventory = self._player_inventory_repository.find_by_id(player_id)
        if inventory is None:
            raise ItemTransferException(
                f"inventory not found for player {player_id.value}"
            )

        # acquire_item は overflow event を発火する可能性があるが、
        # それは正しい (インベントリ満杯は LLM が知りたい状態)。
        inventory.acquire_item(
            item_instance_id,
            item_spec_id_value=ground_item.item_spec_id.value,
        )
        self._player_inventory_repository.save(inventory)

        new_interior = interior.without_ground_item(item_instance_id)
        self._spot_interior_repository.save(spot_id, new_interior)

        item_name = self._item_name_or_id(item_instance_id)

        # witness 最小版: 同室の他プレイヤーに観測として届ける。
        self._publish_event(
            PlayerPickedUpItemEvent.create(
                aggregate_id=self._spot_graph_repository.find_graph().graph_id,
                aggregate_type="SpotGraphAggregate",
                entity_id=EntityId.create(int(player_id)),
                spot_id=spot_id,
                item_instance_id=item_instance_id,
                item_spec_id=ground_item.item_spec_id,
                item_name=item_name,
            )
        )

        return ItemTransferResult(
            messages=(f"{item_name}を拾い上げた。",),
            item_instance_id=item_instance_id,
            spot_id=spot_id,
        )

    def list_ground_items_at_player_spot(
        self, player_id: PlayerId
    ) -> tuple[GroundItem, ...]:
        """プレイヤーが今いるスポットの地面アイテム一覧。

        UI / ランナー / 将来の LLM tool が「拾える物」を列挙するために使う。
        """
        spot_id = self._resolve_current_spot(player_id)
        interior = self._spot_interior_repository.find_by_spot_id(spot_id)
        if interior is None:
            return ()
        return interior.ground_items

    def _publish_event(self, event: object) -> None:
        """event_publisher が注入されていれば publish_all で 1 件発火する。

        publisher は publish_all(events) を持つ duck-typed object (本番では
        PipelineEventPublisher) を想定。未注入 (None) なら no-op で、最小
        構成・テスト用の経路を維持する。
        """
        if self._event_publisher is None:
            return
        try:
            self._event_publisher.publish_all([event])
        except Exception:  # noqa: BLE001 — publisher 側の失敗で本体を倒さない
            _logger.exception("failed to publish item transfer event")

    def _resolve_current_spot(self, player_id: PlayerId) -> SpotId:
        graph = self._spot_graph_repository.find_graph()
        if graph is None:
            raise ItemTransferException("spot graph not found")
        try:
            return graph.get_entity_spot(EntityId.create(int(player_id)))
        except Exception as e:
            raise ItemTransferException(
                f"player {player_id.value} is not placed at any spot: {e}"
            ) from e

    def _item_name_or_id(self, item_instance_id: ItemInstanceId) -> str:
        agg = self._item_repository.find_by_id(item_instance_id)
        if agg is None:
            return f"アイテム#{item_instance_id.value}"
        return agg.item_spec.name


__all__ = [
    "SpotGraphItemTransferService",
    "ItemTransferException",
    "ItemTransferResult",
]

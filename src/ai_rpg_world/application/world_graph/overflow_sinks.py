"""持ちきれなかった品の行き先 (経済統合 Phase 3 の後始末)。

`acquire_item` は満杯だと**黙って品を捨てる**。付与ヘルパーが溢れをここへ渡す
ので、行き先ごとに「何が起きるか」をこのモジュールに集める。

行き先は入口の性質で分かれる。

- **効果として与える経路** (採取・発見・報酬): 足元に落とす。採取そのものは
  成功していて、効果の一部が入らなかっただけなので、行動全体を失敗にすると
  意味が変わる
- **ツールが直接受け取る経路** (市場・同席取引): 事前に断ってあるので、ここへ
  来たら**事前拒否が壊れた証拠**。黙って地面に落とすと、破れが「なぜか品が
  地面にある」という読みにくい形で現れる
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.ground_item import GroundItem

logger = logging.getLogger(__name__)


class OverflowShouldNotHappenError(RuntimeError):
    """事前に断っているはずの経路で、溢れが起きた。

    市場の約定や同席取引の決済は、受け取る空きを**動かす前に**確かめている。
    それでもここへ来たなら、その確認が壊れている。黙って地面に落とすと、
    破れが「なぜか品が地面にある」という読みにくい形でしか現れない。
    """


def refuse_overflow(where: str):
    """溢れたら落ちる行き先を作る (事前拒否のある経路用)。"""

    def _sink(player_id: PlayerId, spec_ids: tuple) -> None:
        raise OverflowShouldNotHappenError(
            f"{where} で溢れが起きました。事前に空きを確かめる処理が壊れています "
            f"(player_id={int(player_id)}, 入らなかった品数={len(spec_ids)})"
        )

    return _sink


class GroundOverflowSink:
    """持ちきれなかった品を、その人の足元へ落とす。

    **地面に容量の制約が無いことに依存している。** `SpotInterior.ground_items`
    は Tuple で上限が無いので、落とす操作は必ず成功し、溢れが再帰しない。
    地面に上限を設けるなら、溢れの行き先をもう一段考える必要がある。
    """

    def __init__(
        self,
        *,
        fixed_spot_provider: Optional[Any] = None,
        event_kind: str = "overflow",
        spot_graph_repository: Any,
        spot_interior_repository: Any,
        item_repository: Any,
        item_spec_repository: Any,
        event_publisher: Optional[Any] = None,
    ) -> None:
        self._fixed_spot = fixed_spot_provider
        self._event_kind = event_kind
        self._graph = spot_graph_repository
        self._interiors = spot_interior_repository
        self._items = item_repository
        self._item_specs = item_spec_repository
        self._events = event_publisher

    def set_event_publisher(self, event_publisher: Any) -> None:
        """観測を出す先を後付けで注入する。

        publisher は runtime を組み終えてからしか作れない。注入前は観測が出ない
        — 品は地面にあるのに誰も気づかない状態なので、配線漏れは観測のテストで
        落ちる。
        """
        self._events = event_publisher

    def bind_to_command(
        self,
        *,
        spot_graph_repository: Any,
        spot_interior_repository: Any,
        item_repository: Any,
        item_spec_repository: Any,
        event_publisher: Any,
    ) -> "GroundOverflowSink":
        """同じ行き先規則をcommand内の資源とイベント収集先へ束縛する。

        長寿命のsinkをそのまま使うと、地面への保存と観測だけが
        ``CommandScope`` を迂回する。後段失敗時に状態は巻き戻っても観測だけが
        残るため、設定値だけを引き継いだcommand専用sinkを作る。
        """
        return GroundOverflowSink(
            fixed_spot_provider=self._fixed_spot,
            event_kind=self._event_kind,
            spot_graph_repository=spot_graph_repository,
            spot_interior_repository=spot_interior_repository,
            item_repository=item_repository,
            item_spec_repository=item_spec_repository,
            event_publisher=event_publisher,
        )

    def __call__(self, player_id: PlayerId, spec_ids: tuple) -> None:
        graph = self._graph.find_graph()
        try:
            # 落とし先が固定されている行き先 (板の足元) では、本人の居場所を
            # 見ない。**落ちる場所が本人の居場所に依存しない**ことが、探しに
            # 行く先が決まることの根拠になる。
            spot_id = (
                self._fixed_spot()
                if self._fixed_spot is not None
                else graph.get_entity_spot(EntityId.create(int(player_id)))
            )
            if spot_id is None:
                raise ValueError("落とし先が決まらない")
        except Exception:  # noqa: BLE001
            # 世界に居ない相手の足元は決められない。黙って捨てるよりは、
            # 落とせなかったことを残す。
            logger.warning(
                "持ちきれなかった品の落とし先が決まらない: player_id=%s 品数=%s",
                int(player_id), len(spec_ids),
            )
            return
        interior = self._interiors.find_by_spot_id(spot_id)
        if interior is None:
            logger.warning(
                "地面の無い場所へ落とそうとした: spot_id=%s player_id=%s",
                spot_id, int(player_id),
            )
            return

        events = []
        for spec_id in spec_ids:
            aggregate = self._create_item(spec_id)
            if aggregate is None:
                continue
            interior = interior.with_ground_item(
                GroundItem(
                    item_instance_id=aggregate.item_instance_id,
                    item_spec_id=aggregate.item_spec.item_spec_id,
                )
            )
            events.append((spot_id, aggregate, graph.graph_id))
        self._interiors.save(spot_id, interior)
        self._publish(player_id, events)

    def _create_item(self, spec_id: ItemSpecId):
        from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate

        spec_union = self._item_specs.find_by_id(spec_id)
        if spec_union is None:
            return None
        spec = (
            spec_union.to_item_spec()
            if hasattr(spec_union, "to_item_spec")
            else spec_union
        )
        aggregate = ItemAggregate.create(
            item_instance_id=self._items.generate_item_instance_id(),
            item_spec=spec,
            quantity=1,
            state=None,
        )
        self._items.save(aggregate)
        return aggregate

    def _publish(self, player_id: PlayerId, events: list) -> None:
        if self._events is None or not events:
            return
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
            MarketDeliveryLeftAtBoardEvent,
            PlayerOverflowedItemEvent,
        )

        event_type = (
            MarketDeliveryLeftAtBoardEvent
            if self._event_kind == "delivery"
            else PlayerOverflowedItemEvent
        )
        self._events.publish_all([
            event_type.create(
                aggregate_id=graph_id,
                aggregate_type="SpotGraphAggregate",
                entity_id=EntityId.create(int(player_id)),
                spot_id=spot_id,
                item_instance_id=aggregate.item_instance_id,
                item_spec_id=aggregate.item_spec.item_spec_id,
                item_name=getattr(aggregate.item_spec, "name", "") or "何か",
            )
            for spot_id, aggregate, graph_id in events
        ])


__all__ = [
    "GroundOverflowSink",
    "OverflowShouldNotHappenError",
    "refuse_overflow",
]

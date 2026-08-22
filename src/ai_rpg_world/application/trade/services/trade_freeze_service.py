"""取引に出したものを、返事がつくまで使えなくする (経済統合 Phase 2)。

## なぜ凍結するか

凍結しないと、承諾した側から見て「受けたのに何も来なかった」が起きる。
失敗が**相手の行動に依存して**発生するので、流れた取引が「判断の失敗」なのか
「タイミングの不運」なのか切り分けられない。交渉そのものを観測したい Phase 2
では、決済の不確実性が観測を汚す。

## item と gold で置き場所が非対称なこと

- **item**: `PlayerInventoryAggregate` の予約 (`reserve_item`) を張る。既存機構で、
  world snapshot にも永続化済み。quest も同じ予約を使っている
- **gold**: 集約に凍結額を持たせない。「利用可能 = 所持 - 提案に出している合計」を
  **提案 store から導出**する

gold を導出にしたのは、凍結の実体が「提案が生きていること」だから。集約に額を
持たせると、提案の消滅と凍結の解除を 2 か所で同期する必要があり、ずれると
**誰の提案でもないのに凍結された gold** が残る。導出なら提案が唯一の真実源に
なり、ずれようがない。snapshot 追随も要らない (提案が復元されれば凍結も戻る)。

item を同じ形にしないのは、既存の予約機構が inventory 側にあり、他機構
(quest) も使っているため。既存に合わせる方が、同じ意味の仕組みを 2 つ持つより
壊れにくい。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    inventory_item_appearances,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.pending_trade_offer import PendingTradeOffer


class TradeFreezeService:
    """提案に出したものを凍結し、返事がついたら解く。"""

    def __init__(
        self,
        *,
        pending_trade_offer_store: Any,
        player_inventory_repository: Any,
        player_status_repository: Any,
        item_repository: Any,
    ) -> None:
        self._offers = pending_trade_offer_store
        self._inventories = player_inventory_repository
        self._statuses = player_status_repository
        self._items = item_repository

    def for_repositories(
        self,
        *,
        player_inventory_repository: Any,
        item_repository: Any,
    ) -> "TradeFreezeService":
        """同じ提案storeを保ち、command専用repositoryへ差し替える。"""
        return TradeFreezeService(
            pending_trade_offer_store=self._offers,
            player_inventory_repository=player_inventory_repository,
            player_status_repository=self._statuses,
            item_repository=item_repository,
        )

    # ── gold ────────────────────────────────────────────────────────────

    def available_gold(self, player_id: PlayerId) -> int:
        """いま使える所持金 (提案に出している額を差し引いた残り)。

        **gold を使う経路はこれを先に通す。** `pay_gold` を直接呼ぶと凍結分まで
        使えてしまう。
        """
        status = self._statuses.find_by_id(player_id)
        if status is None:
            return 0
        return max(0, status.gold.value - self.committed_gold(player_id))

    def committed_gold(self, player_id: PlayerId) -> int:
        """提案に出していて、いまは使えない額。"""
        return self._offers.committed_gold(player_id)

    # ── item ────────────────────────────────────────────────────────────

    def frozen_quantity(self, player_id: PlayerId, item_spec_id: int) -> int:
        """その品を、提案に出していていま使えない数。"""
        return self._offers.committed_item_quantities(player_id).get(item_spec_id, 0)

    def freeze_offer(self, offer: PendingTradeOffer) -> None:
        """提案が差し出している品を予約する。

        予約できる実体が足りないときは例外にせず、**呼び出し側が事前に
        確かめる**契約にしている (提案を作る側が「出せる数を持っているか」を
        先に見る)。ここで黙って一部だけ予約すると、凍結の意味が崩れる。
        """
        inventory = self._inventories.find_by_id(offer.offerer_player_id)
        if inventory is None:
            return
        for spec_id, quantity in offer.gives.items:
            for _ in range(quantity):
                appearances = inventory_item_appearances(inventory, self._items)
                found = inventory.find_available_slot_by_item_spec_id_and_spoilage(
                    ItemSpecId.create(spec_id), False, appearances,
                )
                if not found.found:
                    break
                inventory.reserve_item(found.slot_id)
        self._inventories.save(inventory)

    def release_offer(self, offer: PendingTradeOffer) -> None:
        """返事がついた提案の凍結を解く。

        承諾・辞退・期限切れのどれでも同じように解く。「もう待っていない」
        提案が品を握り続けると、その品は二度と使えなくなる。

        **冪等**。二度呼んでも何も起きない (解除するものが無いだけ)。片付けの
        途中で落ちた提案を次の tick で拾い直すとき、既に解除済みの提案へ
        もう一度呼ぶことがあるため。
        """
        inventory = self._inventories.find_by_id(offer.offerer_player_id)
        if inventory is None:
            return
        wanted: Dict[int, int] = {}
        for spec_id, quantity in offer.gives.items:
            wanted[spec_id] = wanted.get(spec_id, 0) + quantity
        for item_instance_id in tuple(inventory.reserved_item_ids):
            item = self._items.find_by_id(item_instance_id)
            if item is None:
                continue
            spec_value = item.item_spec.item_spec_id.value
            if wanted.get(spec_value, 0) <= 0:
                continue
            inventory.unreserve_item(item_instance_id)
            wanted[spec_value] -= 1
        self._inventories.save(inventory)


__all__ = ["TradeFreezeService"]

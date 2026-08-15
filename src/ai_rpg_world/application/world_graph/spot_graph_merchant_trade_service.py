"""NPC 商人との売買 (経済統合 Phase 1)。

## なぜ部分成功を作らないか

``give_item`` は配列バッチで部分成功を返す。売買では作らない。金銭が動く
操作で「3 個買おうとして 2 個買えた」を許すと、run 全体の gold 流入・流出を
trace から集計するときに、1 回の呼び出しが何 gold 動かしたのかを結果から
逆算しないと決まらなくなる。**全量成功か 0 か**にして、1 回の売買が 1 つの
金額に対応する形を保つ。

## なぜ失敗を原因ごとに分けるか

「買えなかった」だけでは、金が足りないのか、その商人が扱っていないのか、
商人がそもそも居ないのかが分からず、次の一手が決まらない。原因ごとに
例外を分け、文面には次の判断に要る値 (不足額・扱う品・所持数) を載せる。

商人の gold と在庫は無限として扱う (Phase 1 の判断)。売っても買っても
商人側は減らない。通貨の総量を追えるように、増減は trace 側で source つきに
記録する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
    remove_items_of_specs_from_inventory,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerTradedWithMerchantEvent,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

#: trace と観測が使う取引の向き。gold の増減イベントはこの 1 種類に集約し、
#: source を増やすだけで trade / quest 報酬にも拡張できる形にする。
TRADE_DIRECTION_BUY = "merchant_buy"
TRADE_DIRECTION_SELL = "merchant_sell"


class MerchantTradeException(Exception):
    """商人との売買が成立しなかった。

    ``error_code`` は LLM へ返す失敗の分類で、executor がそのまま使う。
    """

    error_code = "MERCHANT_TRADE_FAILED"


class MerchantNotAtSpotError(MerchantTradeException):
    """指定した商人が現在地に居ない。"""

    error_code = "MERCHANT_NOT_AT_SPOT"

    def __init__(self, *, merchant_name: str = "その商人") -> None:
        super().__init__(
            f"{merchant_name}はこの場所に居ません。"
            "商人と同じ場所に居るときだけ売り買いできます。"
        )


class MerchantDoesNotSellError(MerchantTradeException):
    """その商人は、その品を売っていない。"""

    error_code = "BUY_ITEM_NOT_SOLD_HERE"

    def __init__(self, *, merchant_name: str, item_name: str, sold: Sequence[str]) -> None:
        catalog = "、".join(sold) if sold else "何も"
        super().__init__(
            f"{merchant_name}は{item_name}を売っていません。"
            f"{merchant_name}が売っているのは {catalog} です。"
        )


class MerchantDoesNotBuyError(MerchantTradeException):
    """その商人は、その品を買い取らない。"""

    error_code = "SELL_ITEM_NOT_BOUGHT_HERE"

    def __init__(self, *, merchant_name: str, item_name: str, bought: Sequence[str]) -> None:
        catalog = "、".join(bought) if bought else "何も"
        super().__init__(
            f"{merchant_name}は{item_name}を買い取りません。"
            f"{merchant_name}が買い取るのは {catalog} です。"
        )


class NotEnoughGoldError(MerchantTradeException):
    """所持金が足りない。"""

    error_code = "BUY_ITEM_NOT_ENOUGH_GOLD"

    def __init__(
        self,
        *,
        item_name: str,
        quantity: int,
        total: int,
        owned: int,
        committed: int = 0,
    ) -> None:
        # 不足額まで書く。「足りない」だけでは、あと何を売れば届くかを
        # 決められない。取引で凍結している額があれば、それも書く
        # (書かないと「持っているのに足りない」と読めてしまう)。
        tail = (
            f" (うち{committed}G は取引の提案に出しているため使えません)"
            if committed > 0
            else ""
        )
        super().__init__(
            f"{item_name}を{quantity}つ買うには{total}G 必要ですが、"
            f"いま使えるのは{owned}G で{total - owned}G 足りません。{tail}"
        )


class PurchaseInventoryFullError(MerchantTradeException):
    """買った品を入れる空きが足りない。"""

    error_code = "BUY_ITEM_INVENTORY_FULL"

    def __init__(self, *, quantity: int, free_slots: int) -> None:
        tail = (
            "いま持ち物に空きがありません。何かを置くか使ってから買ってください。"
            if free_slots <= 0
            else f"いま入るのは{free_slots}つまでです。"
        )
        super().__init__(f"{quantity}つを持ち物に入れられません。{tail}")


class NotEnoughItemsToSellError(MerchantTradeException):
    """売ろうとした数だけ持っていない。"""

    error_code = "SELL_ITEM_NOT_OWNED"

    def __init__(
        self, *, item_name: str, quantity: int, owned: int, frozen: int = 0,
    ) -> None:
        # 所持ゼロと数量不足を 1 つに畳む。原因 (手持ちが足りない) も
        # 次の一手 (数を減らすか集めてくる) も同じなので、分けても選択が
        # 変わらない。ただし取引に出しているぶんは別で、そちらは「返事を
        # 待つ / 取り下げる」という違う一手になるので書き分ける。
        tail = (
            f" (ほかに{frozen}つを取引の提案に出しているため使えません)"
            if frozen > 0
            else ""
        )
        super().__init__(
            f"{item_name}を{quantity}つ売ろうとしましたが、"
            f"いま売れるのは{owned}つです。{tail}"
        )


@dataclass(frozen=True)
class MerchantTradeResult:
    """成立した売買 1 件。trace と観測はここから作る。"""

    direction: str
    merchant_id: int
    merchant_name: str
    item_spec_id: int
    item_name: str
    quantity: int
    unit_price: int
    #: 行動者から見た増減。買いは負、売りは正。
    gold_delta: int
    gold_after: int


class SpotGraphMerchantTradeService:
    """同席する NPC 商人との売買を実行する。

    商人はシナリオ宣言から作られる読み取り専用の存在で、状態を持たない
    (在庫・所持金とも無限)。したがって本サービスが変えるのは行動者側の
    gold と所持品だけになる。
    """

    def __init__(
        self,
        *,
        spot_graph_repository: ISpotGraphRepository,
        player_status_repository: PlayerStatusRepository,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: Any,
        item_spec_repository: Any,
        merchants: Sequence[Any] = (),
        item_spec_name_resolver: Optional[Any] = None,
        event_publisher: Optional[Any] = None,
        # 経済統合 Phase 2: 取引に出しているぶんを差し引いて見るための口。
        # 未注入なら凍結ゼロとして扱う (取引を宣言しない世界の挙動と一致)。
        trade_freeze_service: Optional[Any] = None,
        overflow_sink: Any = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._player_status_repository = player_status_repository
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._item_spec_repository = item_spec_repository
        self._merchants = tuple(merchants)
        self._item_spec_name_resolver = item_spec_name_resolver
        self._event_publisher = event_publisher
        self._freeze = trade_freeze_service
        self._overflow_sink = overflow_sink

    def set_event_publisher(self, event_publisher: Optional[Any]) -> None:
        """event_publisher を後付けで注入する (runtime の二段構築用)。"""
        self._event_publisher = event_publisher

    def buy(
        self,
        player_id: PlayerId,
        *,
        merchant_id: int,
        item_spec_id: int,
        quantity: int,
    ) -> MerchantTradeResult:
        """同席する商人から品を買う。全量買えないときは 1 つも買わない。"""
        merchant = self._merchant_present_for(player_id, merchant_id)
        unit_price = self._price_of(merchant.sells, item_spec_id)
        item_name = self._item_name(item_spec_id)
        if unit_price is None:
            raise MerchantDoesNotSellError(
                merchant_name=merchant.name,
                item_name=item_name,
                sold=self._catalog_names(merchant.sells),
            )

        status = self._require_status(player_id)
        total = unit_price * quantity
        # **凍結を差し引いた額で見る。** 所持額をそのまま見ると、取引に出して
        # いる gold で買えてしまい、承諾した相手へ渡す金が消える。
        owned = self._available_gold(player_id, status)
        if owned < total:
            raise NotEnoughGoldError(
                item_name=item_name,
                quantity=quantity,
                total=total,
                owned=owned,
                committed=self._committed_gold(player_id),
            )

        # 空きの確認は支払いより先に行う。逆順にすると、入らなかったときに
        # 払った金を戻す処理が要る = 途中で壊れる余地を作る。
        free_slots = self._free_slots(player_id)
        if free_slots < quantity:
            raise PurchaseInventoryFullError(quantity=quantity, free_slots=free_slots)

        status.pay_gold(total)
        self._player_status_repository.save(status)
        grant_item_specs_to_inventory(
            player_id,
            tuple(ItemSpecId.create(item_spec_id) for _ in range(quantity)),
            self._item_repository,
            self._item_spec_repository,
            self._player_inventory_repository,
            overflow_sink=self._overflow_sink,
        )
        return self._finish(
            player_id,
            direction=TRADE_DIRECTION_BUY,
            merchant=merchant,
            item_spec_id=item_spec_id,
            item_name=item_name,
            quantity=quantity,
            unit_price=unit_price,
            gold_delta=-total,
        )

    def sell(
        self,
        player_id: PlayerId,
        *,
        merchant_id: int,
        item_spec_id: int,
        quantity: int,
    ) -> MerchantTradeResult:
        """同席する商人へ品を売る。全量売れないときは 1 つも売らない。"""
        merchant = self._merchant_present_for(player_id, merchant_id)
        unit_price = self._price_of(merchant.buys, item_spec_id)
        item_name = self._item_name(item_spec_id)
        if unit_price is None:
            raise MerchantDoesNotBuyError(
                merchant_name=merchant.name,
                item_name=item_name,
                bought=self._catalog_names(merchant.buys),
            )

        inventory = self._player_inventory_repository.find_by_id(player_id)
        owned = 0
        if inventory is not None:
            counts = count_owned_item_instances_by_spec(inventory, self._item_repository)
            owned = counts.get(ItemSpecId.create(item_spec_id), 0)
        if inventory is None or owned < quantity:
            # 「持っていない」と「取引に出している」を畳まない。次の一手が
            # 違う (集めてくる vs 返事を待つ / 取り下げる)。
            raise NotEnoughItemsToSellError(
                item_name=item_name,
                quantity=quantity,
                owned=owned,
                frozen=self._frozen_quantity(player_id, item_spec_id),
            )

        removed = remove_items_of_specs_from_inventory(
            inventory,
            tuple(ItemSpecId.create(item_spec_id) for _ in range(quantity)),
            self._item_repository,
        )
        if not removed:
            # 予約中の品しか無い等で全量を確保できなかった。数え方 (予約を
            # 除外する) と揃っているので通常は起きないが、黙って売れたことに
            # すると金だけ増える。
            raise NotEnoughItemsToSellError(
                item_name=item_name, quantity=quantity, owned=owned,
            )
        self._player_inventory_repository.save(inventory)

        status = self._require_status(player_id)
        total = unit_price * quantity
        status.earn_gold(total)
        self._player_status_repository.save(status)
        return self._finish(
            player_id,
            direction=TRADE_DIRECTION_SELL,
            merchant=merchant,
            item_spec_id=item_spec_id,
            item_name=item_name,
            quantity=quantity,
            unit_price=unit_price,
            gold_delta=total,
        )

    def merchants_at(self, spot_id: SpotId) -> Tuple[Any, ...]:
        """その場所に居る商人を宣言順で返す。"""
        return tuple(m for m in self._merchants if m.spot_id == spot_id)

    def _merchant_present_for(self, player_id: PlayerId, merchant_id: int) -> Any:
        """行動者と同席している商人を返す。居なければ失敗にする。"""
        merchant = next(
            (m for m in self._merchants if m.merchant_id == merchant_id), None,
        )
        if merchant is None:
            raise MerchantNotAtSpotError()
        spot_id = self._current_spot(player_id)
        if spot_id is None or merchant.spot_id != spot_id:
            raise MerchantNotAtSpotError(merchant_name=merchant.name)
        return merchant

    def _current_spot(self, player_id: PlayerId) -> Optional[SpotId]:
        graph = self._spot_graph_repository.find_graph()
        try:
            return graph.get_entity_spot(EntityId.create(int(player_id)))
        except Exception:
            # グラフに居ない (死亡・退場など) は「同席していない」と同じ扱い。
            return None

    def _available_gold(self, player_id: PlayerId, status: Any) -> int:
        """いま使える所持金 (取引に出しているぶんを差し引いた残り)。"""
        if self._freeze is None:
            return status.gold.value
        return self._freeze.available_gold(player_id)

    def _committed_gold(self, player_id: PlayerId) -> int:
        return 0 if self._freeze is None else self._freeze.committed_gold(player_id)

    def _frozen_quantity(self, player_id: PlayerId, item_spec_id: int) -> int:
        if self._freeze is None:
            return 0
        return self._freeze.frozen_quantity(player_id, item_spec_id)

    def _require_status(self, player_id: PlayerId) -> Any:
        status = self._player_status_repository.find_by_id(player_id)
        if status is None:
            raise MerchantTradeException(
                f"player status not found for {player_id.value}"
            )
        return status

    def _free_slots(self, player_id: PlayerId) -> int:
        inventory = self._player_inventory_repository.find_by_id(player_id)
        if inventory is None:
            return 0
        return sum(1 for _slot, instance in inventory.iter_slots() if instance is None)

    @staticmethod
    def _price_of(price_list: Sequence[Any], item_spec_id: int) -> Optional[int]:
        for entry in price_list:
            if entry.item_spec_id == item_spec_id:
                return entry.price
        return None

    def _catalog_names(self, price_list: Sequence[Any]) -> Tuple[str, ...]:
        return tuple(
            f"{self._item_name(entry.item_spec_id)} {entry.price}G"
            for entry in price_list
        )

    def _item_name(self, item_spec_id: int) -> str:
        if self._item_spec_name_resolver is None:
            return "その品"
        try:
            return self._item_spec_name_resolver(item_spec_id) or "その品"
        except Exception:
            return "その品"

    def _finish(
        self,
        player_id: PlayerId,
        *,
        direction: str,
        merchant: Any,
        item_spec_id: int,
        item_name: str,
        quantity: int,
        unit_price: int,
        gold_delta: int,
    ) -> MerchantTradeResult:
        """成立した売買を観測イベントとして流し、結果を返す。"""
        gold_after = self._require_status(player_id).gold.value
        result = MerchantTradeResult(
            direction=direction,
            merchant_id=merchant.merchant_id,
            merchant_name=merchant.name,
            item_spec_id=item_spec_id,
            item_name=item_name,
            quantity=quantity,
            unit_price=unit_price,
            gold_delta=gold_delta,
            gold_after=gold_after,
        )
        self._publish_trade_event(player_id, merchant.spot_id, result)
        return result

    def _publish_trade_event(
        self, player_id: PlayerId, spot_id: SpotId, result: MerchantTradeResult,
    ) -> None:
        if self._event_publisher is None:
            return
        event = PlayerTradedWithMerchantEvent.create(
            aggregate_id=self._spot_graph_repository.find_graph().graph_id,
            aggregate_type="SpotGraphAggregate",
            entity_id=EntityId.create(int(player_id)),
            spot_id=spot_id,
            merchant_name=result.merchant_name,
            item_name=result.item_name,
            item_spec_id=ItemSpecId.create(result.item_spec_id),
            quantity=result.quantity,
            direction=result.direction,
        )
        self._event_publisher.publish_all([event])


__all__ = [
    "MerchantDoesNotBuyError",
    "MerchantDoesNotSellError",
    "MerchantNotAtSpotError",
    "MerchantTradeException",
    "MerchantTradeResult",
    "NotEnoughGoldError",
    "NotEnoughItemsToSellError",
    "PurchaseInventoryFullError",
    "SpotGraphMerchantTradeService",
    "TRADE_DIRECTION_BUY",
    "TRADE_DIRECTION_SELL",
]

"""返事のないまま期限を過ぎた提案を片付ける tick stage (経済統合 Phase 2)。

## 手順の順序が壊れ方を決める

提案の片付けは 2 つの store をまたぐ (提案 store と inventory の予約)。途中で
落ちたときにどちらの中間状態が残るかは、順序で決まる。

- 削除 → 解除 の順: 間で落ちると **提案は消えたのに凍結だけ残る**。その品を
  解放できる提案がもう存在しないので、**永久に使えない品**が生まれる
- 解除 → 削除 の順: 間で落ちると「凍結の無い期限切れ提案」が残るだけ。次の
  tick で同じ提案をもう一度拾えるので、**自己修復する**

**回復可能な中間状態が残る方を選ぶ。** そのため解除を先に置き、解除自体を
冪等にしてある (二度解除しても何も起きない)。

## 誰に知らせるか

offerer と target の両方へ届ける。第三者には流さない。

target にも届けるのは、accept / decline を常時露出にした結果、target の状況
確認には「自分宛ての提案がある」が出るため。それが黙って消えると「さっきまで
あった選択肢が理由もなく無くなった」になる。第三者は提案の時点で中身を観測して
いるので、その後の沈黙まで公開する必要は無い。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ai_rpg_world.application.trade.services.trade_freeze_service import (
    TradeFreezeService,
)
from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
    WorldTickFailureIsolator,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.trade.event.trade_event import TradeOfferExpiredEvent

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )
    from ai_rpg_world.application.trade.trade_offer_expiry_command_repository_provider import (
        TradeOfferExpiryCommandRepositoryProviderPort,
    )


class TradeOfferExpiryStage:
    """期限切れの提案を、凍結を解いてから片付ける。"""

    def __init__(
        self,
        *,
        command_scope_factory: CommandScopeFactoryPort[TradeOfferExpiryCommandRepositoryProviderPort] | None = None,
        failure_isolator: WorldTickFailureIsolator | None = None,
    ) -> None:
        self._failure_isolator = failure_isolator or WorldTickFailureIsolator.fail_fast()
        self._command_scope_factory = command_scope_factory

    def set_command_scope_factory(
        self,
        factory: CommandScopeFactoryPort[TradeOfferExpiryCommandRepositoryProviderPort],
    ) -> None:
        """本番stageをoffer一件単位の確定境界へ接続する。"""
        self._command_scope_factory = factory

    def run(self, current_tick: WorldTick) -> None:
        raw_tick: Any = getattr(current_tick, "value", current_tick)
        tick_value = int(raw_tick)
        factory = self._command_scope_factory
        if factory is None:
            raise RuntimeError("trade offer expiry command scope が未配線です")

        # 候補取得も同じstoreの占有下で行う。各offerは別scopeで再確認するため、
        # 先行offerの確定は後続offerの失敗に巻き戻されない。
        with factory.create() as scope:
            offer_ids = tuple(
                offer.offer_id for offer in scope.repositories.pending_trade_offers.expired_offers(tick_value)
            )

        for offer_id in offer_ids:
            with self._failure_isolator.unit(
                stage="trade_offer_expiry",
                tick=WorldTick(tick_value),
                target_kind="trade_offer",
                target_id=getattr(offer_id, "value", offer_id),
            ):
                self._expire_one(factory, offer_id, tick_value)

    @staticmethod
    def _expire_one(factory: Any, offer_id: Any, tick_value: int) -> None:
        """一件をscope内で再確認し、予約解除・削除・eventを一緒に確定する。"""
        with factory.create() as scope:
            repositories = scope.repositories
            offers = repositories.pending_trade_offers
            offer = offers.find(offer_id)
            if offer is None or not offer.is_pending or not offer.is_expired_at(tick_value):
                return
            freeze = TradeFreezeService(
                pending_trade_offer_store=offers,
                player_inventory_repository=repositories.player_inventories,
                player_status_repository=None,
                item_repository=repositories.items,
            )
            freeze.release_offer(offer)
            offers.put(offer.expire())
            scope.collect(
                TradeOfferExpiredEvent.create(
                    aggregate_id=offer.offer_id,
                    aggregate_type="PendingTradeOffer",
                    offerer_player_id=offer.offerer_player_id,
                    target_player_id=offer.target_player_id,
                    gives=offer.gives,
                    asks=offer.asks,
                    occurred_tick=WorldTick(tick_value),
                )
            )


__all__ = ["TradeOfferExpiryStage"]

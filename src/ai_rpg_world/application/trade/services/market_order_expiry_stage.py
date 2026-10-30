"""期限を過ぎた板の注文を片付ける tick stage (経済統合 Phase 3)。

## なぜ stage が要るか

`MarketService.expire_orders` は書いてあったが、**どこからも呼ばれていなかった**。
その結果、期限は宣言されているのに**注文が永久に板へ残る**。v3 の実 run では
t33 に出した注文が t80 まで生きていて、値の付け直しまで受けている。

「期限がある」と宣言した世界で期限が来ないのは、**世界が嘘をついている**状態。
出した人は「置いておけばいつか流れる」と思って板を離れる。

## 片付けは市場サービスに任せる

預けた品を返せるか、返せないなら引き取り待ちにするか、という判断は板の側の
知識である。stage は**いつ呼ぶか**だけを持つ。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
    WorldTickFailureIsolator,
)
from ai_rpg_world.domain.common.value_object import WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )
    from ai_rpg_world.application.trade.market_order_expiry_command_repository_provider import (
        MarketOrderExpiryCommandRepositoryProviderPort,
    )
    from ai_rpg_world.application.trade.services.market_service import (
        MarketOrderExpiryResult,
    )


class MarketOrderExpiryStage:
    """毎 tick、期限を過ぎた注文を板から下げる。"""

    def __init__(
        self,
        *,
        market_service: Any,
        command_scope_factory: CommandScopeFactoryPort[MarketOrderExpiryCommandRepositoryProviderPort] | None = None,
        failure_isolator: WorldTickFailureIsolator | None = None,
    ) -> None:
        self._failure_isolator = failure_isolator or WorldTickFailureIsolator.fail_fast()
        self._market = market_service
        self._command_scope_factory = command_scope_factory

    def set_command_scope_factory(
        self,
        factory: CommandScopeFactoryPort[MarketOrderExpiryCommandRepositoryProviderPort],
    ) -> None:
        """本番stageを注文一件単位の確定境界へ接続する。"""
        self._command_scope_factory = factory

    def run(self, current_tick: WorldTick) -> None:
        raw_tick: Any = getattr(current_tick, "value", current_tick)
        tick_value = int(raw_tick)
        scope_factory = self._command_scope_factory
        if scope_factory is None:
            raise RuntimeError("市場注文期限切れ用CommandScopeFactoryが未配線です。")
        for order in self._market.expired_orders(current_tick=tick_value):
            # 失敗した注文は rollback で板へ残るため、次 tick でもう一度拾い直せる。
            with self._failure_isolator.unit(
                stage="market_order_expiry",
                tick=WorldTick(tick_value),
                target_kind="market_order",
                target_id=getattr(getattr(order, "order_id", None), "value", None),
            ):
                self._expire_with_scope(order, tick_value, scope_factory)

    def _expire_with_scope(
        self,
        order: Any,
        tick_value: int,
        scope_factory: (CommandScopeFactoryPort[MarketOrderExpiryCommandRepositoryProviderPort]),
    ) -> None:
        result: MarketOrderExpiryResult | None = None
        try:
            with scope_factory.create() as scope:
                repositories = scope.repositories
                market = self._market.for_expiry_repositories(
                    player_inventory_repository=repositories.player_inventories,
                    player_status_repository=repositories.player_statuses,
                    item_repository=repositories.items,
                )
                result = market._expire_order_with_repositories(
                    order_id=order.order_id,
                    current_tick=tick_value,
                )
        except CommandPostCommitException:
            self._notify(result, tick_value)
            raise
        self._notify(result, tick_value)

    def _notify(self, result: MarketOrderExpiryResult | None, tick_value: int) -> None:
        if result is None:
            return
        try:
            self._market.observe_expiry(result)
        except Exception as exc:  # noqa: BLE001
            self._failure_isolator.record_continued_failure(
                exc,
                stage="market_order_expiry.observation",
                tick=WorldTick(tick_value),
                target_kind="market_order",
                target_id=result.order.order_id.value,
            )


__all__ = ["MarketOrderExpiryStage"]

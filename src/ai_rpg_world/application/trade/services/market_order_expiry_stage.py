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

import logging
from typing import Any, Optional, TYPE_CHECKING

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
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

logger = logging.getLogger(__name__)


class MarketOrderExpiryStage:
    """毎 tick、期限を過ぎた注文を板から下げる。"""

    def __init__(
        self,
        *,
        market_service: Any,
        command_scope_factory: Optional[
            "CommandScopeFactoryPort[MarketOrderExpiryCommandRepositoryProviderPort]"
        ] = None,
    ) -> None:
        self._market = market_service
        self._command_scope_factory = command_scope_factory

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[MarketOrderExpiryCommandRepositoryProviderPort]",
    ) -> None:
        """本番stageを注文一件単位の確定境界へ接続する。"""
        self._command_scope_factory = factory

    def run(self, current_tick: WorldTick) -> None:
        tick_value = int(getattr(current_tick, "value", current_tick))
        if self._command_scope_factory is None:
            self._run_legacy(tick_value)
            return
        for order in self._market.expired_orders(current_tick=tick_value):
            try:
                self._expire_with_scope(order, tick_value)
            except CommandPostCommitException:
                # 状態は確定済みだが、transaction資源の後始末に失敗している。
                # 通常失敗として握ると、呼び出し側が資源を再利用してしまう。
                raise
            except Exception:  # noqa: BLE001
                # 一件が壊れても、独立した後続注文の返却は続ける。失敗注文は
                # rollbackで板へ残るため、次tickでもう一度拾い直せる。
                logger.warning(
                    "板の期限切れを片付けられなかった "
                    "(tick=%s order_id=%s)",
                    tick_value,
                    getattr(getattr(order, "order_id", None), "value", None),
                    exc_info=True,
                )

    def _run_legacy(self, tick_value: int) -> None:
        try:
            self._market.expire_orders(current_tick=tick_value)
        except Exception:  # noqa: BLE001
            logger.warning(
                "板の期限切れを片付けられなかった (tick=%s)",
                tick_value,
                exc_info=True,
            )

    def _expire_with_scope(self, order: Any, tick_value: int) -> None:
        result: Optional["MarketOrderExpiryResult"] = None
        try:
            with self._command_scope_factory.create() as scope:
                repositories = scope.repositories
                market = self._market.for_expiry_repositories(
                    player_inventory_repository=repositories.player_inventories,
                    player_status_repository=repositories.player_statuses,
                    item_repository=repositories.items,
                )
                result = market.expire_order(
                    order_id=order.order_id,
                    current_tick=tick_value,
                )
        except CommandPostCommitException:
            self._notify(result)
            raise
        self._notify(result)

    def _notify(self, result: Optional["MarketOrderExpiryResult"]) -> None:
        if result is None:
            return
        try:
            self._market.observe_expiry(result)
        except Exception:  # noqa: BLE001
            logger.warning(
                "板の期限切れ観測を配れませんでした (order_id=%s)",
                result.order.order_id.value,
                exc_info=True,
            )


__all__ = ["MarketOrderExpiryStage"]

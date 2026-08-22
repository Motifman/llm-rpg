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

import logging
from typing import Any, Optional, TYPE_CHECKING

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.domain.common.value_object import WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )
    from ai_rpg_world.application.trade.trade_offer_expiry_command_repository_provider import (
        TradeOfferExpiryCommandRepositoryProviderPort,
    )

logger = logging.getLogger(__name__)


class TradeOfferExpiryStage:
    """期限切れの提案を、凍結を解いてから片付ける。"""

    def __init__(
        self,
        *,
        pending_trade_offer_store: Any,
        trade_freeze_service: Any,
        expiry_observer: Optional[Any] = None,
        command_scope_factory: Optional[
            "CommandScopeFactoryPort[TradeOfferExpiryCommandRepositoryProviderPort]"
        ] = None,
    ) -> None:
        self._offers = pending_trade_offer_store
        self._freeze = trade_freeze_service
        # 観測の発火は外から差し込む。stage が観測の作り方まで知ると、
        # 保存・復元やテストのたびに観測経路を引き回すことになる。
        self._observer = expiry_observer
        self._command_scope_factory = command_scope_factory

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[TradeOfferExpiryCommandRepositoryProviderPort]",
    ) -> None:
        """本番stageをoffer一件単位の確定境界へ接続する。"""
        self._command_scope_factory = factory

    def run(self, current_tick: WorldTick) -> None:
        tick_value = int(getattr(current_tick, "value", current_tick))
        for offer in self._offers.expired_offers(tick_value):
            if self._command_scope_factory is not None:
                self._expire_with_scope(offer)
                continue
            # 1. 凍結を先に解く (冪等)。ここで落ちても、提案は store に残り
            #    次の tick で拾い直せる。
            self._freeze.release_offer(offer)
            # 2. 集約を期限切れへ遷移させ、store から外す。
            self._offers.put(offer.expire())
            # 3. 当事者へ知らせる。
            self._notify(offer)

    def _expire_with_scope(self, offer: Any) -> None:
        """一件の提案削除とinventory予約解除を一緒に確定する。"""
        try:
            with self._command_scope_factory.create() as scope:
                repositories = scope.repositories
                freeze = self._freeze.for_repositories(
                    player_inventory_repository=repositories.player_inventories,
                    item_repository=repositories.items,
                )
                freeze.release_offer(offer)
                self._offers.put(offer.expire())
        except CommandPostCommitException:
            self._notify(offer)
            raise
        self._notify(offer)

    def _notify(self, offer: Any) -> None:
        if self._observer is None:
            return
        try:
            self._observer(offer)
        except Exception:  # noqa: BLE001
            # 観測が落ちても片付け自体は終わっている。ここで例外を上げると
            # tick 全体が止まり、片付いた提案が観測だけ無い状態より悪くなる。
            logger.warning(
                "取引の期限切れ観測を配れませんでした (offer_id=%s)",
                getattr(getattr(offer, "offer_id", None), "value", None),
                exc_info=True,
            )


__all__ = ["TradeOfferExpiryStage"]

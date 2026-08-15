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
from typing import Any

from ai_rpg_world.domain.common.value_object import WorldTick

logger = logging.getLogger(__name__)


class MarketOrderExpiryStage:
    """毎 tick、期限を過ぎた注文を板から下げる。"""

    def __init__(self, *, market_service: Any) -> None:
        self._market = market_service

    def run(self, current_tick: WorldTick) -> None:
        tick_value = int(getattr(current_tick, "value", current_tick))
        try:
            self._market.expire_orders(current_tick=tick_value)
        except Exception:  # noqa: BLE001
            # 片付けに失敗しても世界の進行は止めない。ただし**黙らせない** —
            # 静かに落ちると「期限が来ない板」に逆戻りし、run が終わるまで
            # 誰も気づけない。
            logger.warning(
                "板の期限切れを片付けられなかった (tick=%s)", tick_value,
                exc_info=True,
            )


__all__ = ["MarketOrderExpiryStage"]

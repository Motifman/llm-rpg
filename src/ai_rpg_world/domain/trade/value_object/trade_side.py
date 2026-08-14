"""取引の片側 (差し出す物と金) を表す値オブジェクト (Phase 2)。

品と gold を 1 つにまとめるのは、「パン 2 つ + 3G と薬草 1 つ」のような
混ぜた条件を 1 つの提案で書けるようにするため。片側が空の提案は作れない
(一方的な譲渡は give_item の仕事)。
"""

from dataclasses import dataclass
from typing import Tuple

from ai_rpg_world.domain.trade.exception.trade_exception import (
    TradeOfferValidationException,
)

#: (item_spec_id, quantity) の並び。
TradeSideItems = Tuple[Tuple[int, int], ...]


@dataclass(frozen=True)
class TradeSide:
    """片側が差し出すもの。品の並びと gold を持つ。"""

    items: TradeSideItems = ()
    gold: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise TradeOfferValidationException("items は tuple で指定してください")
        seen: set = set()
        for entry in self.items:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TradeOfferValidationException(
                    f"items の要素は (item_spec_id, quantity) で指定してください (got {entry!r})"
                )
            spec_id, quantity = entry
            for name, value in (("item_spec_id", spec_id), ("quantity", quantity)):
                if isinstance(value, bool) or not isinstance(value, int):
                    raise TradeOfferValidationException(
                        f"{name} は整数で指定してください (got {value!r})"
                    )
            if quantity <= 0:
                raise TradeOfferValidationException(
                    f"quantity は 1 以上で指定してください (got {quantity})"
                )
            if spec_id in seen:
                # どちらの個数が効くか決まらない。商人の価格表で同じ判断をしている。
                raise TradeOfferValidationException(
                    f"同じ品を片側に二度書けません (item_spec_id={spec_id})"
                )
            seen.add(spec_id)
        if isinstance(self.gold, bool) or not isinstance(self.gold, int):
            raise TradeOfferValidationException(
                f"gold は整数で指定してください (got {self.gold!r})"
            )
        if self.gold < 0:
            raise TradeOfferValidationException(
                f"gold は 0 以上で指定してください (got {self.gold})"
            )

    @property
    def is_empty(self) -> bool:
        """何も差し出していないか。"""
        return not self.items and self.gold == 0

    @property
    def has_gold(self) -> bool:
        return self.gold > 0

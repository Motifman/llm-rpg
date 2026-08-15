"""市場の板に出す注文の ID (経済統合 Phase 3)。"""

from dataclasses import dataclass
from typing import Union

from ai_rpg_world.domain.trade.exception.trade_exception import (
    MarketOrderValidationException,
)


@dataclass(frozen=True)
class MarketOrderId:
    """板の注文 1 件の識別子。1 以上の整数。"""

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise MarketOrderValidationException(
                f"order_id は整数で指定してください (got {self.value!r})"
            )
        if self.value <= 0:
            raise MarketOrderValidationException(
                f"order_id は 1 以上で指定してください (got {self.value})"
            )

    @classmethod
    def create(cls, value: Union[int, str]) -> "MarketOrderId":
        try:
            return cls(int(value))
        except (TypeError, ValueError) as exc:
            raise MarketOrderValidationException(
                f"order_id を整数として読めません (got {value!r})"
            ) from exc

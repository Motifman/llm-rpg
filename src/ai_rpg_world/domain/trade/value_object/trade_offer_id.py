"""同席取引の提案 ID (Phase 2)。"""

from dataclasses import dataclass
from typing import Union

from ai_rpg_world.domain.trade.exception.trade_exception import (
    TradeOfferValidationException,
)


@dataclass(frozen=True)
class TradeOfferId:
    """提案 1 件の識別子。1 以上の整数。"""

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise TradeOfferValidationException(
                f"offer_id は整数で指定してください (got {self.value!r})"
            )
        if self.value <= 0:
            raise TradeOfferValidationException(
                f"offer_id は 1 以上で指定してください (got {self.value})"
            )

    @classmethod
    def create(cls, value: Union[int, str]) -> "TradeOfferId":
        try:
            return cls(int(value))
        except (TypeError, ValueError) as exc:
            raise TradeOfferValidationException(
                f"offer_id を整数として読めません (got {value!r})"
            ) from exc

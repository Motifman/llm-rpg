"""取引イベントの冪等なread model投影境界。"""

from __future__ import annotations

from typing import Callable, Protocol

from ai_rpg_world.domain.trade.repository.trade_read_model_repository import (
    TradeReadModelRepository,
)


TradeProjection = Callable[[TradeReadModelRepository], None]


class TradeProjectionExecutorPort(Protocol):
    """投影更新と処理済み記録を同じ原子性境界で実行する契約。"""

    def execute_once(
        self,
        *,
        consumer_id: str,
        event_id: int,
        projection: TradeProjection,
    ) -> bool:
        """未処理なら投影してTrue、処理済みなら何もせずFalseを返す。"""
        ...


def validate_consumer_identity(*, consumer_id: object, event_id: object) -> None:
    """consumer inboxの一意キーを永続化前に検証する。"""
    if (
        not isinstance(consumer_id, str)
        or not consumer_id
        or consumer_id != consumer_id.strip()
    ):
        raise ValueError("consumer_idは前後空白のない文字列である必要があります")
    if isinstance(event_id, bool) or not isinstance(event_id, int) or event_id < 1:
        raise ValueError("event_idは1以上の整数である必要があります")


__all__ = [
    "TradeProjection",
    "TradeProjectionExecutorPort",
    "validate_consumer_identity",
]

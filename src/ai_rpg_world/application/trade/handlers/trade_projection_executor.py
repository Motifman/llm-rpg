"""取引イベントの冪等なread model投影境界。"""

from __future__ import annotations

from typing import Callable, Protocol

from ai_rpg_world.domain.trade.repository.trade_read_model_repository import (
    TradeReadModelRepository,
)
from ai_rpg_world.application.common.exceptions import ApplicationException


TradeProjection = Callable[[TradeReadModelRepository], None]


class TradeProjectionPrerequisiteMissingException(ApplicationException):
    """先行するread model投影が未到着で、現在の投影を確定できない。"""

    def __init__(self, *, trade_id: int, event_name: str) -> None:
        self.trade_id = trade_id
        self.event_name = event_name
        super().__init__(
            "取引read modelの前提投影がまだありません: "
            f"trade_id={trade_id}, event={event_name}",
            trade_id=trade_id,
            event_name=event_name,
        )


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
    "TradeProjectionPrerequisiteMissingException",
    "validate_consumer_identity",
]

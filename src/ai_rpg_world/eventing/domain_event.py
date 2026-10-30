"""ゲームと Being が共通に使うイベントの基底。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DomainEvent:
    """文脈に依存せず、起きた出来事の識別子と日時を保持する。"""

    event_id: int
    occurred_at: datetime

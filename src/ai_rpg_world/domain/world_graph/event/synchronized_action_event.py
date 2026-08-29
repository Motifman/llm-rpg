"""同期行動groupが確定区間へ収集する結果イベント。"""

from dataclasses import dataclass
from typing import Literal

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent


@dataclass(frozen=True)
class SynchronizedActionMessageEvent(BaseDomainEvent[str, str]):
    """同期行動の完成または時間切れを参加者へ伝える。"""

    outcome: Literal["completed", "timed_out"]
    recipient_ids: tuple[int, ...]
    message: str


__all__ = ["SynchronizedActionMessageEvent"]

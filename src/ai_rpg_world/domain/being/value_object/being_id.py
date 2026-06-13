"""BeingId 値オブジェクト。

「経験を持つ AI」の主体を一意に識別する ID。世界・run を跨いで永続化される
ため、整数 ``PlayerId`` (= world 内の attachment) とは別系統の識別子として
**文字列 ID** を採用する。

- 空文字 / 空白のみは不可
- 前後の空白はトリム
- 内部で UUID を使うかどうかは利用側の自由 (Repository が生成側を担うため
  本 VO は形式を強制しない)
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingIdValidationException,
)


@dataclass(frozen=True)
class BeingId:
    """Being を一意に識別する値オブジェクト。"""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise BeingIdValidationException(
                f"BeingId.value must be str, got {type(self.value).__name__}"
            )
        stripped = self.value.strip()
        if not stripped:
            raise BeingIdValidationException("BeingId.value must be non-empty")
        object.__setattr__(self, "value", stripped)

    def __str__(self) -> str:
        return self.value


__all__ = ["BeingId"]

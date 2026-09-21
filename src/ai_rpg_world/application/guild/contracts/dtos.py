from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GuildCommandResultDto:
    """ギルドコマンド実行結果DTO"""
    success: bool
    message: str
    data: dict[str, Any] | None = None

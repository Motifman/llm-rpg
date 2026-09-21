from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HarvestCommandResultDto:
    """採集コマンドの結果DTO"""
    success: bool
    message: str
    data: dict[str, Any] | None = None

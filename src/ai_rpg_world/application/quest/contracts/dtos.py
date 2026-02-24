from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class QuestCommandResultDto:
    """クエストコマンド実行結果DTO"""
    success: bool
    message: str
    data: Optional[dict] = None

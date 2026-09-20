from dataclasses import dataclass


@dataclass(frozen=True)
class QuestCommandResultDto:
    """クエストコマンド実行結果DTO"""
    success: bool
    message: str
    data: dict | None = None

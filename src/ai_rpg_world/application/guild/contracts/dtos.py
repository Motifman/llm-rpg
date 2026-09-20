from dataclasses import dataclass


@dataclass(frozen=True)
class GuildCommandResultDto:
    """ギルドコマンド実行結果DTO"""
    success: bool
    message: str
    data: dict | None = None

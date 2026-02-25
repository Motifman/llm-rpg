"""ショップコマンド結果DTO"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ShopCommandResultDto:
    """ショップコマンド実行結果DTO"""
    success: bool
    message: str
    data: Optional[dict] = None

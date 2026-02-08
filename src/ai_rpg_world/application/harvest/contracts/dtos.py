from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass(frozen=True)
class HarvestCommandResultDto:
    """採集コマンドの結果DTO"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

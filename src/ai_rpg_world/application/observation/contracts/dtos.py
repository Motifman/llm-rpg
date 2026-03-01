"""観測まわりの DTO・値オブジェクト"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Literal

ObservationCategory = Literal["self_only", "social", "environment"]


@dataclass(frozen=True)
class ObservationOutput:
    """1イベント分の観測出力（プローズ文と構造化データの両方）。
    observation_category は attention_level によるフィルタで使用する。
    """

    prose: str
    structured: Dict[str, Any]
    observation_category: ObservationCategory = "self_only"

    def __post_init__(self) -> None:
        if not isinstance(self.prose, str):
            raise TypeError("prose must be str")
        if not isinstance(self.structured, dict):
            raise TypeError("structured must be dict")
        if self.observation_category not in ("self_only", "social", "environment"):
            raise TypeError(
                "observation_category must be 'self_only', 'social', or 'environment'"
            )


@dataclass(frozen=True)
class ObservationEntry:
    """バッファに蓄積する1件の観測（発生日時付き）"""

    occurred_at: datetime
    output: ObservationOutput

    def __post_init__(self) -> None:
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be datetime")
        if not isinstance(self.output, ObservationOutput):
            raise TypeError("output must be ObservationOutput")

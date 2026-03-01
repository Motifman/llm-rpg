"""観測まわりの DTO・値オブジェクト"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict


@dataclass(frozen=True)
class ObservationOutput:
    """1イベント分の観測出力（プローズ文と構造化データの両方）"""

    prose: str
    structured: Dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.prose, str):
            raise TypeError("prose must be str")
        if not isinstance(self.structured, dict):
            raise TypeError("structured must be dict")


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

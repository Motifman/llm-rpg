"""観測まわりの DTO・値オブジェクト"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Literal, Optional

ObservationCategory = Literal["self_only", "social", "environment"]


@dataclass(frozen=True)
class ObservationOutput:
    """1イベント分の観測出力（プローズ文と構造化データの両方）。
    observation_category は attention_level によるフィルタで使用する。
    schedules_turn: LLM にターンを積む（反応すべき観測）。
    breaks_movement: 移動中なら経路を中断する（被ダメージ・会話開始・目の前の危険等）。
    """

    prose: str
    structured: Dict[str, Any]
    observation_category: ObservationCategory = "self_only"
    schedules_turn: bool = False
    breaks_movement: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.prose, str):
            raise TypeError("prose must be str")
        if not isinstance(self.structured, dict):
            raise TypeError("structured must be dict")
        if self.observation_category not in ("self_only", "social", "environment"):
            raise TypeError(
                "observation_category must be 'self_only', 'social', or 'environment'"
            )
        if not isinstance(self.schedules_turn, bool):
            raise TypeError("schedules_turn must be bool")
        if not isinstance(self.breaks_movement, bool):
            raise TypeError("breaks_movement must be bool")


@dataclass(frozen=True)
class ObservationEntry:
    """バッファに蓄積する1件の観測（発生日時・ゲーム内時刻ラベル付き）"""

    occurred_at: datetime
    output: ObservationOutput
    game_time_label: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be datetime")
        if not isinstance(self.output, ObservationOutput):
            raise TypeError("output must be ObservationOutput")
        if self.game_time_label is not None and not isinstance(self.game_time_label, str):
            raise TypeError("game_time_label must be str or None")

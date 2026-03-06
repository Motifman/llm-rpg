"""観測まわりの DTO・値オブジェクト"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Literal, Optional

ObservationCategory = Literal["self_only", "social", "environment"]


@dataclass(frozen=True)
class ObservationOutput:
    """1イベント分の観測出力（プローズ文と構造化データの両方）。
    observation_category は attention_level によるフィルタで使用する。
    causes_interrupt: リアルタイム性を要求する観測（話しかけ・ダメージ・アイテム発見等）で True。
    プレイヤーが複数ティックの行動中でも、この観測が届いたら行動を中断して LLM に渡す。
    """

    prose: str
    structured: Dict[str, Any]
    observation_category: ObservationCategory = "self_only"
    causes_interrupt: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.prose, str):
            raise TypeError("prose must be str")
        if not isinstance(self.structured, dict):
            raise TypeError("structured must be dict")
        if self.observation_category not in ("self_only", "social", "environment"):
            raise TypeError(
                "observation_category must be 'self_only', 'social', or 'environment'"
            )
        if not isinstance(self.causes_interrupt, bool):
            raise TypeError("causes_interrupt must be bool")


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

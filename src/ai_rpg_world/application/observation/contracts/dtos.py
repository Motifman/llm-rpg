"""観測まわりの DTO・値オブジェクト"""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

ObservationCategory = Literal["self_only", "social", "environment"]


@dataclass(frozen=True)
class SubjectUnknownView:
    """話し手を知らない受け手に記録させる版。名前を伏せた本文と structured。"""

    prose: str
    structured: dict[str, Any]


@dataclass(frozen=True)
class WithheldFromStrangers:
    """主体を知らない受け手には届けない印。名前を伏せても、誰かがいることが分かってしまう観測に付ける。"""


@dataclass(frozen=True)
class ObservationOutput:
    """1イベント分の観測出力（プローズ文と構造化データの両方）。
    observation_category は attention_level によるフィルタで使用する。
    schedules_turn: LLM にターンを積む（反応すべき観測）。
    breaks_movement: 移動中なら経路を中断する（被ダメージ・会話開始・目の前の危険等）。
    """

    prose: str
    structured: dict[str, Any]
    observation_category: ObservationCategory = "self_only"
    schedules_turn: bool = False
    breaks_movement: bool = False
    # #1520: 話し手を知っているかで描き方が変わる観測だけが持つ。どちらを記録
    # するかは、受け手の Being が知り合いの記録を引いて決める。
    subject_name: str | None = None
    if_subject_unknown: SubjectUnknownView | WithheldFromStrangers | None = None

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
        if (self.subject_name is None) != (self.if_subject_unknown is None):
            raise TypeError("subject_name and if_subject_unknown must come together")
        if self.subject_name is not None:
            if not isinstance(self.subject_name, str) or not self.subject_name.strip():
                raise TypeError("subject_name must be non-blank str")
            if not isinstance(
                self.if_subject_unknown, (SubjectUnknownView, WithheldFromStrangers)
            ):
                raise TypeError(
                    "if_subject_unknown must be SubjectUnknownView or WithheldFromStrangers"
                )

    def as_subject_known(self) -> "ObservationOutput":
        return replace(self, subject_name=None, if_subject_unknown=None)

    def as_subject_unknown(self) -> "ObservationOutput | None":
        """伏せた版を持たない観測は、そのまま返す。届けない観測は None を返す。"""
        view = self.if_subject_unknown
        if view is None:
            return self
        if isinstance(view, WithheldFromStrangers):
            return None
        return replace(
            self,
            prose=view.prose,
            structured=dict(view.structured),
            subject_name=None,
            if_subject_unknown=None,
        )


@dataclass(frozen=True)
class ObservationEntry:
    """バッファに蓄積する1件の観測（発生日時・ゲーム内時刻ラベル付き）"""

    occurred_at: datetime
    output: ObservationOutput
    game_time_label: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be datetime")
        if not isinstance(self.output, ObservationOutput):
            raise TypeError("output must be ObservationOutput")
        if self.game_time_label is not None and not isinstance(self.game_time_label, str):
            raise TypeError("game_time_label must be str or None")

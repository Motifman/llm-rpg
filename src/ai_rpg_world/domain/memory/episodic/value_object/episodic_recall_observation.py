"""EpisodicRecallObservation — 受動想起された episode と想起時状況スナップショット。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/episodic_reinterpretation.py`` から domain に昇格。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ai_rpg_world.domain.memory.episodic.value_object._validators import (
    normalize_optional_text,
    optional_non_blank,
    reject_blank,
    validate_str_tuple,
)


@dataclass(frozen=True)
class EpisodicRecallObservation:
    """受動想起された episode と、その想起時点の状況スナップショット。"""

    recall_id: str
    player_id: int
    episode_id: str
    recalled_at: datetime
    source_axes: tuple[str, ...]
    current_state_snapshot: str
    recent_events_snapshot: str
    persona_snapshot: str
    situation_cues: tuple[str, ...]
    turn_index: int
    # U1 (予測誤差統一設計 部品1・部品5): この episode を想起した prompt build
    # 時点で発行された prediction_context_id。「この記憶を思い出して立てた予測が
    # どう外れた/当たったか」を後から辿るための紐付けキー (U9 の想起信用割り当て
    # の土台)。prompt_builder が二段階発行 (id 発行 → recall stamp → in-context
    # 集合の確定) で recall observation 生成時に stamp する。id 機構が OFF
    # (PREDICTION_CONTEXT_ID_ENABLED 未設定) のとき・旧 snapshot 由来のときは
    # None (既定値で後方互換)。
    prediction_context_id: Optional[str] = None
    # U9a (予測誤差統一設計 部品5・誤差駆動再解釈): この recall observation を
    # in-context にして立てた予測 (= prediction_context_id で特定される) が
    # 外れたときの誤差文。chunk 補完で prediction_error が確定した瞬間、
    # recall buffer 側の該当 observation にこの値が刻まれる
    # (`EpisodicRecallBufferRepository.stamp_prediction_outcome_by_being`)。
    # 「思い出したのに外れた」を再解釈 coordinator が誤差専用 framing で扱う
    # ための入力になる (的中側の ranking boost は U9b で別途扱う、本 VO
    # フィールドはその対象外)。ERROR_DRIVEN_REINTERPRETATION_ENABLED が
    # OFF (既定) のときは常に None (後方互換・旧 snapshot 由来も None)。
    prediction_outcome_error: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "recall_id", reject_blank("recall_id", self.recall_id))
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        object.__setattr__(self, "episode_id", reject_blank("episode_id", self.episode_id))
        if not isinstance(self.recalled_at, datetime):
            raise TypeError("recalled_at must be datetime")
        object.__setattr__(
            self, "source_axes", validate_str_tuple("source_axes", self.source_axes)
        )
        object.__setattr__(
            self,
            "current_state_snapshot",
            normalize_optional_text("current_state_snapshot", self.current_state_snapshot),
        )
        object.__setattr__(
            self,
            "recent_events_snapshot",
            normalize_optional_text("recent_events_snapshot", self.recent_events_snapshot),
        )
        object.__setattr__(
            self,
            "persona_snapshot",
            normalize_optional_text("persona_snapshot", self.persona_snapshot),
        )
        object.__setattr__(
            self,
            "situation_cues",
            validate_str_tuple("situation_cues", self.situation_cues),
        )
        if not isinstance(self.turn_index, int):
            raise TypeError("turn_index must be int")
        if self.turn_index < 0:
            raise ValueError("turn_index must be 0 or greater")
        if self.prediction_context_id is not None and not isinstance(
            self.prediction_context_id, str
        ):
            raise TypeError("prediction_context_id must be str or None")
        object.__setattr__(
            self,
            "prediction_outcome_error",
            optional_non_blank(
                "prediction_outcome_error", self.prediction_outcome_error
            ),
        )


__all__ = ["EpisodicRecallObservation"]

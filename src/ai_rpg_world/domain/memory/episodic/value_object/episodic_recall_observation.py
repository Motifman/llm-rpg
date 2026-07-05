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
    # の土台)。既定 None で後方互換 (= 旧 snapshot / id 未発行の recall)。
    prediction_context_id: Optional[str] = None

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


__all__ = ["EpisodicRecallObservation"]

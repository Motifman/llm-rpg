"""想起後のエピソード再解釈に関する契約型。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


def _reject_blank(field_label: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_label} must be str")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_label} must not be empty or whitespace-only")
    return stripped


def _normalize_optional_text(field_label: str, value: str | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{field_label} must be str or None")
    return value.strip()


def _validate_str_tuple(field_label: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_label} must be tuple[str, ...]")
    out: list[str] = []
    for idx, raw in enumerate(values):
        out.append(_reject_blank(f"{field_label}[{idx}]", raw))
    return tuple(out)


class EpisodicReinterpretationStatus(str, Enum):
    """再解釈ジャーナル entry の有効状態。"""

    ACTIVE = "active"
    SUPERSEDED = "superseded"


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "recall_id", _reject_blank("recall_id", self.recall_id))
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        object.__setattr__(self, "episode_id", _reject_blank("episode_id", self.episode_id))
        if not isinstance(self.recalled_at, datetime):
            raise TypeError("recalled_at must be datetime")
        object.__setattr__(self, "source_axes", _validate_str_tuple("source_axes", self.source_axes))
        object.__setattr__(
            self,
            "current_state_snapshot",
            _normalize_optional_text("current_state_snapshot", self.current_state_snapshot),
        )
        object.__setattr__(
            self,
            "recent_events_snapshot",
            _normalize_optional_text("recent_events_snapshot", self.recent_events_snapshot),
        )
        object.__setattr__(
            self,
            "persona_snapshot",
            _normalize_optional_text("persona_snapshot", self.persona_snapshot),
        )
        object.__setattr__(
            self,
            "situation_cues",
            _validate_str_tuple("situation_cues", self.situation_cues),
        )
        if not isinstance(self.turn_index, int):
            raise TypeError("turn_index must be int")
        if self.turn_index < 0:
            raise ValueError("turn_index must be 0 or greater")


@dataclass(frozen=True)
class EpisodicReinterpretationEntry:
    """現在視点での episode 再解釈。active entry だけを prompt 参照に使う。"""

    entry_id: str
    player_id: int
    episode_id: str
    created_at: datetime
    turn_index: int
    current_interpretation: str
    current_recall_text: str
    source_recall_ids: tuple[str, ...]
    status: EpisodicReinterpretationStatus = EpisodicReinterpretationStatus.ACTIVE
    superseded_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_id", _reject_blank("entry_id", self.entry_id))
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        object.__setattr__(self, "episode_id", _reject_blank("episode_id", self.episode_id))
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be datetime")
        if not isinstance(self.turn_index, int):
            raise TypeError("turn_index must be int")
        if self.turn_index < 0:
            raise ValueError("turn_index must be 0 or greater")
        object.__setattr__(
            self,
            "current_interpretation",
            _reject_blank("current_interpretation", self.current_interpretation),
        )
        object.__setattr__(
            self,
            "current_recall_text",
            _reject_blank("current_recall_text", self.current_recall_text),
        )
        object.__setattr__(
            self,
            "source_recall_ids",
            _validate_str_tuple("source_recall_ids", self.source_recall_ids),
        )
        if not isinstance(self.status, EpisodicReinterpretationStatus):
            object.__setattr__(self, "status", EpisodicReinterpretationStatus(str(self.status)))
        if self.superseded_at is not None and not isinstance(self.superseded_at, datetime):
            raise TypeError("superseded_at must be datetime or None")
        if self.status == EpisodicReinterpretationStatus.ACTIVE and self.superseded_at is not None:
            raise ValueError("active entry must not have superseded_at")


class IEpisodicRecallBufferStore(ABC):
    """想起イベントを再解釈 flush まで保持するストア。"""

    @abstractmethod
    def append(self, observation: EpisodicRecallObservation) -> None:
        """想起観測を追加する。"""

    @abstractmethod
    def peek_batch(
        self,
        player_id: int,
        *,
        batch_size: int,
        max_contexts_per_episode: int,
    ) -> tuple[EpisodicRecallObservation, ...]:
        """episode ごとに束ねた pending batch を返す。削除はしない。"""

    @abstractmethod
    def mark_processed(self, player_id: int, recall_ids: tuple[str, ...]) -> None:
        """処理済み recall_id を pending から除く。"""

    @abstractmethod
    def pending_count(self, player_id: int) -> int:
        """指定 player の pending 件数。"""


class IEpisodicReinterpretationJournalStore(ABC):
    """再解釈履歴を保持し、最新 active entry だけを通常参照へ出すストア。"""

    @abstractmethod
    def put_active(self, entry: EpisodicReinterpretationEntry) -> None:
        """同一 episode の既存 active entry を supersede して entry を active 保存する。"""

    @abstractmethod
    def get_active(
        self,
        player_id: int,
        episode_id: str,
    ) -> EpisodicReinterpretationEntry | None:
        """通常参照用の active entry を返す。なければ None。"""

    @abstractmethod
    def list_by_episode(
        self,
        player_id: int,
        episode_id: str,
    ) -> list[EpisodicReinterpretationEntry]:
        """監査用に履歴を新しい順で返す。"""


class IEpisodicReinterpretationCompletionPort(ABC):
    """想起済み episode 群を現在文脈から再解釈する JSON 完了ポート。"""

    @abstractmethod
    def complete_episodic_reinterpretation_json(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """messages を LLM に送り、JSON object を返す。"""


__all__ = [
    "EpisodicRecallObservation",
    "EpisodicReinterpretationEntry",
    "EpisodicReinterpretationStatus",
    "IEpisodicRecallBufferStore",
    "IEpisodicReinterpretationCompletionPort",
    "IEpisodicReinterpretationJournalStore",
]

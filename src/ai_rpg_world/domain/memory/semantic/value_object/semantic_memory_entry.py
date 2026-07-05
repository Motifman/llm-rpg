"""SemanticMemoryEntry — エピソード集約から昇格したセマンティック要約 (長期記憶プロトタイプ)。

DDD 再編 (Issue #470 Phase 1 PR3): 元
``application/llm/contracts/semantic_memory_entry.py`` から domain に昇格。

U3a (belief journal 化): semantic_learning_consolidation_design.md
「保存 (ルール): belief journal」節の構造だけを導入する。LLM 呼び出しや
固着 coordinator は含まない (U3b で別 PR)。既定挙動 (全 entry が active)
は不変で、既存の想起結果は変わらない。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from ai_rpg_world.domain.memory.semantic.exception.semantic_exception import (
    SemanticMemoryEntryValidationException,
)

# belief の状態遷移 (再解釈 journal と同型): create は active、revise で旧 belief
# が superseded、反証が閾値を割ると inactive。いずれも削除はしない (想起は
# active のみが読む)。
SEMANTIC_MEMORY_STATUS_ACTIVE = "active"
SEMANTIC_MEMORY_STATUS_SUPERSEDED = "superseded"
SEMANTIC_MEMORY_STATUS_INACTIVE = "inactive"
_VALID_SEMANTIC_MEMORY_STATUS_VALUES = frozenset(
    {
        SEMANTIC_MEMORY_STATUS_ACTIVE,
        SEMANTIC_MEMORY_STATUS_SUPERSEDED,
        SEMANTIC_MEMORY_STATUS_INACTIVE,
    }
)


@dataclass(frozen=True)
class SemanticMemoryEntry:
    """クラスタ根拠付きの一般化テキスト。

    Phase 1b で ``importance_score`` / ``tags`` を追加 (default で後方互換)。
    現状 (Phase 1b) は LLM 生成の場合だけ意味のある値が入り、決定論 gist の
    場合は default のまま。Phase 1c の passive top-K スコアリングで使う。

    U3a で belief journal 用フィールドを追加 (全て default 付きで後方互換):
    ``belief_id`` / ``status`` / ``supersedes`` / ``support_evidence_ids`` /
    ``contradict_evidence_ids``。旧 entry (belief_id 未指定) は
    ``__post_init__`` で ``belief_id = entry_id`` にフォールバックし、
    「自分自身が 1 系譜の journal」として扱われる。
    """

    entry_id: str
    player_id: int
    text: str
    evidence_episode_ids: Tuple[str, ...]
    confidence: float
    created_at: datetime
    # Phase 1b 拡張: LLM gist の場合に値が入る。決定論 gist の場合は default
    # (importance_score=5, tags=()) のまま。Phase 1c で top-K スコアの
    # importance 項として使う予定。
    importance_score: int = 5
    tags: Tuple[str, ...] = ()
    # U3a 拡張 (belief journal)。belief_id は空文字なら entry_id にフォール
    # バックする (frozen なので __post_init__ 内で object.__setattr__ する)。
    belief_id: str = ""
    status: str = SEMANTIC_MEMORY_STATUS_ACTIVE
    supersedes: Optional[str] = None
    support_evidence_ids: Tuple[str, ...] = ()
    contradict_evidence_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.entry_id, str) or not self.entry_id.strip():
            raise ValueError("entry_id must be non-empty str")
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must be non-empty str")
        if not isinstance(self.evidence_episode_ids, tuple):
            raise TypeError("evidence_episode_ids must be tuple[str, ...]")
        for i, eid in enumerate(self.evidence_episode_ids):
            if not isinstance(eid, str) or not eid.strip():
                raise ValueError(f"evidence_episode_ids[{i}] must be non-empty str")
        if not isinstance(self.confidence, (int, float)) or not (
            0.0 <= float(self.confidence) <= 1.0
        ):
            raise ValueError("confidence must be float in [0,1]")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be datetime")
        if not isinstance(self.importance_score, int):
            raise TypeError("importance_score must be int")
        if not (1 <= self.importance_score <= 10):
            raise ValueError("importance_score must be in [1, 10]")
        if not isinstance(self.tags, tuple):
            raise TypeError("tags must be tuple[str, ...]")
        for i, tag in enumerate(self.tags):
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError(f"tags[{i}] must be non-empty str")

        # U3a: belief journal フィールドのバリデーション。
        if not isinstance(self.belief_id, str):
            raise SemanticMemoryEntryValidationException(
                "belief_id must be str", field="belief_id", value=self.belief_id
            )
        if not self.belief_id.strip():
            # 未指定 (旧 entry) は自分自身を belief 系譜の起点とみなす。
            object.__setattr__(self, "belief_id", self.entry_id)
        else:
            object.__setattr__(self, "belief_id", self.belief_id.strip())

        if not isinstance(self.status, str):
            raise SemanticMemoryEntryValidationException(
                "status must be str", field="status", value=self.status
            )
        if self.status not in _VALID_SEMANTIC_MEMORY_STATUS_VALUES:
            raise SemanticMemoryEntryValidationException(
                f"status must be one of {sorted(_VALID_SEMANTIC_MEMORY_STATUS_VALUES)}",
                field="status",
                value=self.status,
            )

        if self.supersedes is not None:
            if not isinstance(self.supersedes, str) or not self.supersedes.strip():
                raise SemanticMemoryEntryValidationException(
                    "supersedes must be non-empty str or None",
                    field="supersedes",
                    value=self.supersedes,
                )
            object.__setattr__(self, "supersedes", self.supersedes.strip())

        if not isinstance(self.support_evidence_ids, tuple):
            raise SemanticMemoryEntryValidationException(
                "support_evidence_ids must be tuple[str, ...]",
                field="support_evidence_ids",
                value=self.support_evidence_ids,
            )
        for i, eid in enumerate(self.support_evidence_ids):
            if not isinstance(eid, str) or not eid.strip():
                raise SemanticMemoryEntryValidationException(
                    f"support_evidence_ids[{i}] must be non-empty str",
                    field="support_evidence_ids",
                    index=i,
                )

        if not isinstance(self.contradict_evidence_ids, tuple):
            raise SemanticMemoryEntryValidationException(
                "contradict_evidence_ids must be tuple[str, ...]",
                field="contradict_evidence_ids",
                value=self.contradict_evidence_ids,
            )
        for i, eid in enumerate(self.contradict_evidence_ids):
            if not isinstance(eid, str) or not eid.strip():
                raise SemanticMemoryEntryValidationException(
                    f"contradict_evidence_ids[{i}] must be non-empty str",
                    field="contradict_evidence_ids",
                    index=i,
                )


__all__ = [
    "SemanticMemoryEntry",
    "SEMANTIC_MEMORY_STATUS_ACTIVE",
    "SEMANTIC_MEMORY_STATUS_SUPERSEDED",
    "SEMANTIC_MEMORY_STATUS_INACTIVE",
]

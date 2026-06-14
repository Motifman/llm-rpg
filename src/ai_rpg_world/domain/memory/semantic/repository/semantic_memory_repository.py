"""SemanticMemoryRepository — セマンティック記憶 (昇格済み要約) の保管庫 interface。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/semantic_memory_store_port.py::SemanticMemoryRepository``
を domain に昇格し、``*Repository`` 命名に統一。

Phase 3 Step 3b-3 (Issue #470): legacy player_id 版 API
(``add`` / ``list_for_player`` / ``register_cluster_signature_if_new``) を撤去し、
being_id 版のみを残した。caller は全て ``*_by_being`` 経路で読み書きする
(Step 3b-2 で caller 切替済)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)


class SemanticMemoryRepository(ABC):
    """セマンティック記憶 (エピソード集約から昇格した一般化要約) を保持する。

    一次キーは ``BeingId``。run 跨ぎ identity を保つため Being 集約を識別子に
    使う設計 (Phase 2 で導入、Phase 3 で全 caller を Being keyed に統一)。
    """

    @abstractmethod
    def add_by_being(self, being_id: BeingId, entry: SemanticMemoryEntry) -> None:
        """being_id keyed で entry を追加する。同一 entry_id は upsert。

        entry 自体の ``player_id`` フィールドは attach 元 PlayerId として保持
        されるが、本 API では BeingId が一次キーとして扱われる。
        """

    @abstractmethod
    def list_for_being(self, being_id: BeingId) -> list[SemanticMemoryEntry]:
        """being_id keyed で entry 一覧を返す (``created_at`` 降順)。"""

    @abstractmethod
    def register_cluster_signature_if_new_by_being(
        self, being_id: BeingId, evidence_signature: str
    ) -> bool:
        """being_id keyed で cluster signature を登録。既存なら False。"""


__all__ = ["SemanticMemoryRepository"]

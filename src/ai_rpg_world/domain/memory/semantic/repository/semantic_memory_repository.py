"""SemanticMemoryRepository — セマンティック記憶 (昇格済み要約) の保管庫 interface。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/semantic_memory_store_port.py::SemanticMemoryRepository``
を domain に昇格し、``*Repository`` 命名に統一。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)


class SemanticMemoryRepository(ABC):
    """セマンティック記憶 (エピソード集約から昇格した一般化要約) を保持する。"""

    @abstractmethod
    def add(self, entry: SemanticMemoryEntry) -> None:
        """同一 entry_id は上書き可とみなし upsert でもよい。"""

    @abstractmethod
    def list_for_player(self, player_id: int) -> list[SemanticMemoryEntry]:
        """昇格済みエントリ一覧（新しい順など実装依存）。"""

    @abstractmethod
    def register_cluster_signature_if_new(
        self, player_id: int, evidence_signature: str
    ) -> bool:
        """同一エビデンス集合が未昇格なら登録し True。既存なら False。"""


__all__ = ["SemanticMemoryRepository"]

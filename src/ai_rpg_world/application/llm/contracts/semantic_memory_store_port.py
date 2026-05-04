"""セマンティック記憶（昇格済み要約）の永続化ポート。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.application.llm.contracts.semantic_memory_entry import SemanticMemoryEntry


class ISemanticMemoryStore(ABC):
    @abstractmethod
    def add(self, entry: SemanticMemoryEntry) -> None:
        """同一 entry_id は上書き可とみなし upsert でもよい。"""

    @abstractmethod
    def list_for_player(self, player_id: int) -> list[SemanticMemoryEntry]:
        """昇格済みエントリ一覧（新しい順など実装依存）。"""

    @abstractmethod
    def register_cluster_signature_if_new(self, player_id: int, evidence_signature: str) -> bool:
        """同一エビデンス集合が未昇格なら登録し True。既存なら False。"""


__all__ = ["ISemanticMemoryStore"]

"""SemanticMemoryRepository — セマンティック記憶 (昇格済み要約) の保管庫 interface。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/semantic_memory_store_port.py::SemanticMemoryRepository``
を domain に昇格し、``*Repository`` 命名に統一。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)


class SemanticMemoryRepository(ABC):
    """セマンティック記憶 (エピソード集約から昇格した一般化要約) を保持する。

    Phase 3 Step 3b-1 (Issue #470): ``*_by_being`` API を並走追加。Step 3b-2 で
    caller を新 API に切替え、Step 3b-3 で旧 player_id 版を撤去する想定。
    並走期間中は両 API のデータは互いに見えない (= 同一 caller が新旧を
    混在させない前提)。memo の Step 3a と同じパターン。
    """

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

    # ===== Phase 3 Step 3b-1: being_id 版を並走追加 =====

    @abstractmethod
    def add_by_being(self, being_id: BeingId, entry: SemanticMemoryEntry) -> None:
        """being_id keyed で entry を追加する。同一 entry_id は upsert。

        entry 自体の ``player_id`` フィールドはそのまま保持されるが、本 API では
        BeingId が一次キーとして扱われる。
        """

    @abstractmethod
    def list_for_being(self, being_id: BeingId) -> list[SemanticMemoryEntry]:
        """being_id keyed で entry 一覧を返す。"""

    @abstractmethod
    def register_cluster_signature_if_new_by_being(
        self, being_id: BeingId, evidence_signature: str
    ) -> bool:
        """being_id keyed で cluster signature を登録。既存なら False。"""


__all__ = ["SemanticMemoryRepository"]

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

    @abstractmethod
    def list_cluster_signatures_by_being(self, being_id: BeingId) -> list[str]:
        """being_id keyed で登録済 cluster signature を **辞書順** で返す。

        Phase 4 Step 4-2a (Issue #470): snapshot 用の enumeration。
        ``register_cluster_signature_if_new_by_being`` で True を返した signature
        の集合を取り出すための readout API。
        """

    @abstractmethod
    def replace_all_by_being(
        self,
        being_id: BeingId,
        entries: list[SemanticMemoryEntry],
        cluster_signatures: list[str],
    ) -> None:
        """being_id 配下の entries と cluster_signatures を完全置換する。

        Phase 4 Step 4-2a: snapshot restore primitive。**既存の entries / cluster
        signatures は全て削除** され、引数で再構築される。順序保持。Snapshot 経路
        以外からの呼び出しは想定しない。
        """

    @abstractmethod
    def supersede_by_being(
        self,
        being_id: BeingId,
        *,
        old_entry_id: str,
        new_entry: SemanticMemoryEntry,
    ) -> None:
        """belief journal の revise 操作 (U3a)。

        ``old_entry_id`` の entry を ``status=superseded`` に更新し、
        ``new_entry`` (``status=active`` / ``supersedes=old_entry_id`` /
        旧 entry と同じ ``belief_id`` を持つ想定) を upsert する。1 操作として
        アトミックに行う (片方だけ反映される状態を構造的に防ぐ)。

        ``old_entry_id`` が存在しない場合は old 側の更新をスキップし、
        ``new_entry`` の追加のみ行う (無条件失敗にしない)。
        """

    @abstractmethod
    def update_status_by_being(
        self, being_id: BeingId, entry_id: str, status: str
    ) -> None:
        """belief journal の状態更新操作 (U3a)。反証で inactive 化する等に使う。

        ``entry_id`` が存在しない場合は何もしない (無条件失敗にしない)。
        """


__all__ = ["SemanticMemoryRepository"]

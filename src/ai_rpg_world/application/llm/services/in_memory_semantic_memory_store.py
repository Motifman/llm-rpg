"""SemanticMemoryRepository のインメモリ実装。

Phase 3 Step 3b-3 (Issue #470): legacy player_id 版を撤去し、being_id 版のみ
を残した。
"""

from __future__ import annotations

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import SemanticMemoryEntry
from ai_rpg_world.domain.memory.semantic.repository.semantic_memory_repository import SemanticMemoryRepository


class InMemorySemanticMemoryStore(SemanticMemoryRepository):
    def __init__(self) -> None:
        self._being_rows: dict[BeingId, list[SemanticMemoryEntry]] = {}
        self._being_cluster_sigs: set[tuple[BeingId, str]] = set()

    def add_by_being(self, being_id: BeingId, entry: SemanticMemoryEntry) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entry, SemanticMemoryEntry):
            raise TypeError("entry must be SemanticMemoryEntry")
        # upsert: 同一 entry_id があれば置換、なければ追加。
        # 内部 dict 値 (list) を comprehension で再構築することで in-place 変更
        # を避け、プロジェクトの immutability 方針に揃える。
        existing_bucket = self._being_rows.get(being_id, [])
        replaced = False
        new_bucket: list[SemanticMemoryEntry] = []
        for e in existing_bucket:
            if e.entry_id == entry.entry_id:
                new_bucket.append(entry)
                replaced = True
            else:
                new_bucket.append(e)
        if not replaced:
            new_bucket.append(entry)
        self._being_rows[being_id] = new_bucket

    def list_for_being(self, being_id: BeingId) -> list[SemanticMemoryEntry]:
        """being_id keyed で entry 一覧を ``created_at`` 降順で返す。

        SQLite 実装 (= ``SqliteSemanticMemoryStore.list_for_being``) と並びを揃え、
        環境間で挙動差を出さない (Phase 3 Step 3b-1 レビュー指摘反映)。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        entries = self._being_rows.get(being_id, [])
        return sorted(entries, key=lambda e: e.created_at, reverse=True)

    def register_cluster_signature_if_new_by_being(
        self, being_id: BeingId, evidence_signature: str
    ) -> bool:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(evidence_signature, str):
            raise TypeError("evidence_signature must be str")
        key = (being_id, evidence_signature)
        if key in self._being_cluster_sigs:
            return False
        self._being_cluster_sigs.add(key)
        return True

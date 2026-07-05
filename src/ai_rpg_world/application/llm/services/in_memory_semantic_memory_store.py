"""SemanticMemoryRepository のインメモリ実装。

Phase 3 Step 3b-3 (Issue #470): legacy player_id 版を撤去し、being_id 版のみ
を残した。
"""

from __future__ import annotations

import dataclasses

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

    def list_cluster_signatures_by_being(self, being_id: BeingId) -> list[str]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        sigs = [s for (b, s) in self._being_cluster_sigs if b == being_id]
        return sorted(sigs)

    def replace_all_by_being(
        self,
        being_id: BeingId,
        entries: list[SemanticMemoryEntry],
        cluster_signatures: list[str],
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entries, list):
            raise TypeError("entries must be list")
        for e in entries:
            if not isinstance(e, SemanticMemoryEntry):
                raise TypeError("entries elements must be SemanticMemoryEntry")
        if not isinstance(cluster_signatures, list):
            raise TypeError("cluster_signatures must be list")
        for s in cluster_signatures:
            if not isinstance(s, str):
                raise TypeError("cluster_signatures elements must be str")
        self._being_rows[being_id] = list(entries)
        # 当該 being の signature を全 drop して再構築。他 being の signature は
        # そのまま保持。
        self._being_cluster_sigs = {
            (b, s) for (b, s) in self._being_cluster_sigs if b != being_id
        } | {(being_id, s) for s in cluster_signatures}

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

    def supersede_by_being(
        self,
        being_id: BeingId,
        *,
        old_entry_id: str,
        new_entry: SemanticMemoryEntry,
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(old_entry_id, str) or not old_entry_id.strip():
            raise TypeError("old_entry_id must be non-empty str")
        if not isinstance(new_entry, SemanticMemoryEntry):
            raise TypeError("new_entry must be SemanticMemoryEntry")
        existing_bucket = self._being_rows.get(being_id, [])
        new_bucket: list[SemanticMemoryEntry] = []
        for e in existing_bucket:
            if e.entry_id == old_entry_id:
                new_bucket.append(
                    dataclasses.replace(
                        e, status="superseded"
                    )
                )
            else:
                new_bucket.append(e)
        self._being_rows[being_id] = new_bucket
        # new_entry の upsert は既存 add_by_being と同じ処理を再利用する。
        self.add_by_being(being_id, new_entry)

    def update_status_by_being(
        self, being_id: BeingId, entry_id: str, status: str
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entry_id, str) or not entry_id.strip():
            raise TypeError("entry_id must be non-empty str")
        if not isinstance(status, str):
            raise TypeError("status must be str")
        existing_bucket = self._being_rows.get(being_id, [])
        new_bucket: list[SemanticMemoryEntry] = [
            dataclasses.replace(e, status=status) if e.entry_id == entry_id else e
            for e in existing_bucket
        ]
        self._being_rows[being_id] = new_bucket

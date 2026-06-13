"""SemanticMemoryRepository のインメモリ実装。"""

from __future__ import annotations

from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import SemanticMemoryEntry
from ai_rpg_world.domain.memory.semantic.repository.semantic_memory_repository import SemanticMemoryRepository


class InMemorySemanticMemoryStore(SemanticMemoryRepository):
    def __init__(self) -> None:
        self._rows: list[SemanticMemoryEntry] = []
        self._cluster_sigs: set[tuple[int, str]] = set()

    def add(self, entry: SemanticMemoryEntry) -> None:
        self._rows.append(entry)

    def list_for_player(self, player_id: int) -> list[SemanticMemoryEntry]:
        return [e for e in self._rows if e.player_id == player_id]

    def register_cluster_signature_if_new(self, player_id: int, evidence_signature: str) -> bool:
        key = (player_id, evidence_signature)
        if key in self._cluster_sigs:
            return False
        self._cluster_sigs.add(key)
        return True


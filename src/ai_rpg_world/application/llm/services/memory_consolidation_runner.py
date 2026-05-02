"""Memory Reflection ジャーナルから長期事実・Identity への Consolidation（ルールベース採用）。"""

from __future__ import annotations

from threading import RLock
from typing import Dict, Set

from ai_rpg_world.application.llm.contracts.interfaces import (
    IIdentityMemoryStore,
    ILongTermMemoryStore,
    ISubjectiveEpisodeStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemoryConsolidationCheckpoint:
    """ジャーナル entry_id 単位で Consolidation 適用済みを記録する in-memory チェックポイント。"""

    def __init__(self) -> None:
        self._by_player: Dict[int, Set[str]] = {}
        self._lock = RLock()

    def has_any_marked(self, player_id: PlayerId) -> bool:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        with self._lock:
            s = self._by_player.get(player_id.value)
            return bool(s)

    def is_processed(self, player_id: PlayerId, entry_id: str) -> bool:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(entry_id, str):
            raise TypeError("entry_id must be str")
        with self._lock:
            return entry_id in self._by_player.get(player_id.value, set())

    def mark_processed(self, player_id: PlayerId, entry_id: str) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(entry_id, str) or not entry_id.strip():
            raise ValueError("entry_id must be non-empty str")
        with self._lock:
            self._by_player.setdefault(player_id.value, set()).add(entry_id)


class MemoryConsolidationRunner:
    """`memory_reflection_journal` の未処理エントリを長期事実・Identity に反映する。"""

    def __init__(
        self,
        *,
        subjective_episode_store: ISubjectiveEpisodeStore,
        long_term_memory_store: ILongTermMemoryStore,
        identity_memory_store: IIdentityMemoryStore,
        checkpoint: InMemoryConsolidationCheckpoint,
        journal_threshold: int = 8,
    ) -> None:
        if not isinstance(subjective_episode_store, ISubjectiveEpisodeStore):
            raise TypeError("subjective_episode_store must be ISubjectiveEpisodeStore")
        if not isinstance(long_term_memory_store, ILongTermMemoryStore):
            raise TypeError("long_term_memory_store must be ILongTermMemoryStore")
        if not isinstance(identity_memory_store, IIdentityMemoryStore):
            raise TypeError("identity_memory_store must be IIdentityMemoryStore")
        if not isinstance(checkpoint, InMemoryConsolidationCheckpoint):
            raise TypeError("checkpoint must be InMemoryConsolidationCheckpoint")
        if journal_threshold < 0:
            raise ValueError("journal_threshold must be 0 or greater")
        self._episodes = subjective_episode_store
        self._long_term = long_term_memory_store
        self._identity = identity_memory_store
        self._checkpoint = checkpoint
        self._journal_threshold = journal_threshold

    def run(self, player_id: PlayerId) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if self._journal_threshold <= 0:
            return
        total = self._episodes.count_reflection_journal_entries(player_id)
        if total < self._journal_threshold and not self._checkpoint.has_any_marked(
            player_id
        ):
            return

        for episode in self._episodes.list_all_episodes(player_id):
            for entry in episode.memory_reflection_journal:
                if self._checkpoint.is_processed(player_id, entry.entry_id):
                    continue
                for cand in entry.semantic_update_candidates:
                    text = cand.summary.strip()
                    if not text:
                        continue
                    line = f"[consolidation:semantic] {text}"
                    note = cand.note.strip()
                    if note:
                        line = f"{line} ({note})"
                    self._long_term.add_fact(player_id, line)
                for cand in entry.identity_update_candidates:
                    text = cand.summary.strip()
                    if not text:
                        continue
                    self._identity.append_statement(
                        player_id,
                        text,
                        source_note=f"consolidation:{entry.entry_id}",
                    )
                self._checkpoint.mark_processed(player_id, entry.entry_id)

"""エピソード記憶ストアの既定解決（インメモリ vs SUBJECTIVE_EPISODE_DB_PATH）。"""

from __future__ import annotations

import os

from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import EpisodicEpisodeRepository
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)


def resolve_default_episodic_episode_store(
    override: EpisodicEpisodeRepository | None,
) -> EpisodicEpisodeRepository:
    """
    呼び出し元がストアを渡したときはそれを使い、未指定なら環境変数で SQLite かインメモリを選ぶ。
    """
    if override is not None:
        return override
    path = os.environ.get("SUBJECTIVE_EPISODE_DB_PATH", "").strip()
    if path:
        from ai_rpg_world.infrastructure.repository.sqlite_subjective_episode_store import (
            SqliteSubjectiveEpisodeStore,
        )

        return SqliteSubjectiveEpisodeStore.connect(path)
    return InMemorySubjectiveEpisodeStore()

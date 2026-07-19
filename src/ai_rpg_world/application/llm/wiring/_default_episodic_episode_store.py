"""エピソード記憶ストアの既定解決（インメモリ vs SQLite 永続化）。

永続化先 (旧 ``SUBJECTIVE_EPISODE_DB_PATH``) は呼び出し側が
``ResolvedLlmRuntimeConfig.subjective_episode_db_path`` から解決した値を ``db_path``
引数で渡す。この関数は env を一切読まない (実験設定の入口を profile/config →
ResolvedLlmRuntimeConfig の 1 本に固定するため / PR #736 の取り残し解消)。
"""

from __future__ import annotations

from typing import Optional

from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import EpisodicEpisodeRepository
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)


def resolve_default_episodic_episode_store(
    override: EpisodicEpisodeRepository | None,
    *,
    db_path: Optional[str] = None,
) -> EpisodicEpisodeRepository:
    """呼び出し元が store を渡したらそれを使い、未指定なら db_path で SQLite か in-memory を選ぶ。

    - ``override`` が渡されたらそのまま返す (db_path は見ない)
    - ``override`` が None で ``db_path`` があれば SQLite 永続化 store
    - どちらも無ければ in-memory store
    """
    if override is not None:
        return override
    path = (db_path or "").strip()
    if path:
        from ai_rpg_world.infrastructure.repository.sqlite_subjective_episode_store import (
            SqliteSubjectiveEpisodeStore,
        )

        return SqliteSubjectiveEpisodeStore.connect(path)
    return InMemorySubjectiveEpisodeStore()

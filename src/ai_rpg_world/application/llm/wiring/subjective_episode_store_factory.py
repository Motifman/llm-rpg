"""v2 主観エピソードストアの既定組み立て（インメモリ既定・SQLite はオプトイン）。"""

from __future__ import annotations

import os
from typing import Mapping, Optional

from ai_rpg_world.application.llm.contracts.interfaces import ISubjectiveEpisodeStore
from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.infrastructure.llm.sqlite_subjective_episode_store import (
    SqliteSubjectiveEpisodeStore,
)

# `TRADE_READMODEL_DB_PATH` と同様、パス明示用。未設定ならインメモリ。
ENV_SUBJECTIVE_EPISODE_DB_PATH = "SUBJECTIVE_EPISODE_DB_PATH"


def create_subjective_episode_store_for_wiring(
    *,
    subjective_episode_store: Optional[ISubjectiveEpisodeStore] = None,
    sqlite_path: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> ISubjectiveEpisodeStore:
    """配線用に `ISubjectiveEpisodeStore` を 1 個返す。

    優先順:
    1. ``subjective_episode_store`` が非 None → そのまま返す（型検査のみ）
    2. ``sqlite_path`` が非空文字列 → ``SqliteSubjectiveEpisodeStore``
    3. 環境変数 ``SUBJECTIVE_EPISODE_DB_PATH`` が非空 → SQLite
    4. それ以外 → ``InMemorySubjectiveEpisodeStore``
    """
    if subjective_episode_store is not None:
        if not isinstance(subjective_episode_store, ISubjectiveEpisodeStore):
            raise TypeError("subjective_episode_store must be ISubjectiveEpisodeStore")
        return subjective_episode_store
    env = environ if environ is not None else os.environ
    path = (sqlite_path or "").strip()
    if not path:
        path = (env.get(ENV_SUBJECTIVE_EPISODE_DB_PATH) or "").strip()
    if path:
        return SqliteSubjectiveEpisodeStore(path)
    return InMemorySubjectiveEpisodeStore()

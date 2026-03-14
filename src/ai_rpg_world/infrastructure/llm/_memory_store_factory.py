"""
LLM メモリストアのファクトリ。

memory_db_path または環境変数 LLM_MEMORY_DB_PATH により、
episode / long-term / reflection_state を SQLite 永続化するか InMemory にするかを決定する。
"""

import os
from typing import Optional

from ai_rpg_world.application.llm.contracts.interfaces import (
    IEpisodeMemoryStore,
    ILongTermMemoryStore,
    IReflectionStatePort,
)

_ENV_LLM_MEMORY_DB_PATH = "LLM_MEMORY_DB_PATH"


def _effective_memory_db_path(memory_db_path: Optional[str] = None) -> Optional[str]:
    """
    メモリ DB パスを決定する。
    引数が渡されていればそれを優先、そうでなければ環境変数 LLM_MEMORY_DB_PATH を参照する。
    """
    if memory_db_path is not None and memory_db_path.strip():
        return memory_db_path.strip()
    raw = (os.environ.get(_ENV_LLM_MEMORY_DB_PATH) or "").strip()
    return raw if raw else None


def create_episode_memory_store(
    memory_db_path: Optional[str] = None,
) -> IEpisodeMemoryStore:
    """
    エピソード記憶ストアを生成する。

    引数 memory_db_path または環境変数 LLM_MEMORY_DB_PATH が設定されていれば
    SqliteEpisodeMemoryStore を、そうでなければ InMemoryEpisodeMemoryStore を返す。

    Args:
        memory_db_path: SQLite DB のパス。None の場合は環境変数を参照。

    Returns:
        IEpisodeMemoryStore を実装したインスタンス。
    """
    path = _effective_memory_db_path(memory_db_path)
    if path:
        from ai_rpg_world.infrastructure.llm.sqlite_episode_memory_store import (
            SqliteEpisodeMemoryStore,
        )
        return SqliteEpisodeMemoryStore(path)
    from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
        InMemoryEpisodeMemoryStore,
    )
    return InMemoryEpisodeMemoryStore()


def create_long_term_memory_store(
    memory_db_path: Optional[str] = None,
) -> "ILongTermMemoryStore":
    """
    長期記憶ストアを生成する。

    引数 memory_db_path または環境変数 LLM_MEMORY_DB_PATH が設定されていれば
    SqliteLongTermMemoryStore を、そうでなければ InMemoryLongTermMemoryStore を返す。

    Args:
        memory_db_path: SQLite DB のパス。None の場合は環境変数を参照。

    Returns:
        ILongTermMemoryStore を実装したインスタンス。
    """
    path = _effective_memory_db_path(memory_db_path)
    if path:
        from ai_rpg_world.infrastructure.llm.sqlite_long_term_memory_store import (
            SqliteLongTermMemoryStore,
        )
        return SqliteLongTermMemoryStore(path)
    from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
        InMemoryLongTermMemoryStore,
    )
    return InMemoryLongTermMemoryStore()


def create_reflection_state_port(
    memory_db_path: Optional[str] = None,
) -> Optional[IReflectionStatePort]:
    """
    Reflection 状態ポートを生成する。

    引数 memory_db_path または環境変数 LLM_MEMORY_DB_PATH が設定されていれば
    SqliteReflectionStatePort を、そうでなければ None を返す（永続化なし）。

    Args:
        memory_db_path: SQLite DB のパス。None の場合は環境変数を参照。

    Returns:
        IReflectionStatePort を実装したインスタンス、または None。
    """
    path = _effective_memory_db_path(memory_db_path)
    if path:
        from ai_rpg_world.infrastructure.llm.sqlite_reflection_state_port import (
            SqliteReflectionStatePort,
        )
        return SqliteReflectionStatePort(path)
    return None

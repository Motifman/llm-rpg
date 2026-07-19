"""episode store の既定解決が config 由来の db_path を使い、env を読まないことを固定する。

PR #736 で実験設定は profile/config → ResolvedLlmRuntimeConfig の 1 経路に固定した
はずだが、``resolve_default_episodic_episode_store`` だけ ``SUBJECTIVE_EPISODE_DB_PATH``
を os.environ から直読みし続けていた (二重入口の取り残し)。db_path は引数で受け取り、
env は一切読まない。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
    InMemorySubjectiveEpisodeStore,
)
from ai_rpg_world.application.llm.wiring._default_episodic_episode_store import (
    resolve_default_episodic_episode_store,
)


class TestResolveDefaultEpisodicEpisodeStore:
    def test_override_wins_over_db_path(self) -> None:
        """override を渡したら db_path に関係なくそれを返す。"""
        override = InMemorySubjectiveEpisodeStore()
        result = resolve_default_episodic_episode_store(
            override, db_path="var/ignored.db"
        )
        assert result is override

    def test_none_db_path_returns_in_memory(self) -> None:
        """override なし・db_path なしなら in-memory store。"""
        result = resolve_default_episodic_episode_store(None, db_path=None)
        assert isinstance(result, InMemorySubjectiveEpisodeStore)

    def test_db_path_builds_sqlite_store(self, tmp_path) -> None:
        """db_path を渡すと SQLite 永続化 store を組む。"""
        from ai_rpg_world.infrastructure.repository.sqlite_subjective_episode_store import (
            SqliteSubjectiveEpisodeStore,
        )

        db = tmp_path / "episodes.db"
        result = resolve_default_episodic_episode_store(None, db_path=str(db))
        assert isinstance(result, SqliteSubjectiveEpisodeStore)

    def test_env_is_not_read(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """SUBJECTIVE_EPISODE_DB_PATH が env にあっても無視し in-memory になる。"""
        monkeypatch.setenv("SUBJECTIVE_EPISODE_DB_PATH", str(tmp_path / "leaked.db"))
        result = resolve_default_episodic_episode_store(None, db_path=None)
        assert isinstance(result, InMemorySubjectiveEpisodeStore)

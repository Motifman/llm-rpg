"""memory_store_factory のテスト（正常・境界・例外）"""

import pytest
from datetime import datetime
from unittest.mock import patch

from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
from ai_rpg_world.application.llm.contracts.interfaces import (
    IEpisodeMemoryStore,
    ILongTermMemoryStore,
    IReflectionStatePort,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.llm._memory_store_factory import (
    create_episode_memory_store,
    create_long_term_memory_store,
    create_reflection_state_port,
)


def _make_episode_entry(
    eid: str = "ep1",
    context: str = "洞窟にいた",
    action: str = "move",
    outcome: str = "到着",
) -> EpisodeMemoryEntry:
    return EpisodeMemoryEntry(
        id=eid,
        context_summary=context,
        action_taken=action,
        outcome_summary=outcome,
        entity_ids=("loc_1",),
        location_id="loc_1",
        timestamp=datetime.now(),
        importance="medium",
        surprise=False,
        recall_count=0,
        scope_keys=(),
        world_object_ids=(),
        spot_id_value=None,
    )


class TestCreateEpisodeMemoryStore:
    """create_episode_memory_store の正常・境界ケース"""

    def test_with_path_returns_sqlite_store(self, tmp_path):
        """path を渡した場合 SqliteEpisodeMemoryStore を返す"""
        db_path = str(tmp_path / "ep.db")
        store = create_episode_memory_store(memory_db_path=db_path)
        assert isinstance(store, IEpisodeMemoryStore)
        assert store.__class__.__name__ == "SqliteEpisodeMemoryStore"

    def test_with_path_persists_data(self, tmp_path):
        """path 指定時は永続化され、同一 path で再生成すれば取得できる"""
        db_path = str(tmp_path / "ep.db")
        store1 = create_episode_memory_store(memory_db_path=db_path)
        player_id = PlayerId(1)
        store1.add(player_id, _make_episode_entry(eid="e1", context="永続化テスト"))

        store2 = create_episode_memory_store(memory_db_path=db_path)
        got = store2.get_recent(player_id, 10)
        assert len(got) == 1
        assert got[0].id == "e1"
        assert got[0].context_summary == "永続化テスト"

    def test_without_path_returns_in_memory_store(self):
        """path を渡さず環境変数も未設定時は InMemoryEpisodeMemoryStore を返す"""
        with patch.dict("os.environ", {}, clear=False):
            # 既存の LLM_MEMORY_DB_PATH を消す
            import os
            env_backup = os.environ.pop("LLM_MEMORY_DB_PATH", None)
            try:
                store = create_episode_memory_store()
                assert isinstance(store, IEpisodeMemoryStore)
                assert store.__class__.__name__ == "InMemoryEpisodeMemoryStore"
            finally:
                if env_backup is not None:
                    os.environ["LLM_MEMORY_DB_PATH"] = env_backup

    def test_with_env_returns_sqlite_store(self, tmp_path):
        """環境変数 LLM_MEMORY_DB_PATH が設定されていれば Sqlite を返す"""
        db_path = str(tmp_path / "ep_env.db")
        with patch.dict("os.environ", {"LLM_MEMORY_DB_PATH": db_path}, clear=False):
            store = create_episode_memory_store()
            assert store.__class__.__name__ == "SqliteEpisodeMemoryStore"
            player_id = PlayerId(1)
            store.add(player_id, _make_episode_entry(eid="e1"))
            store2 = create_episode_memory_store()
            got = store2.get_recent(player_id, 10)
            assert len(got) == 1

    def test_explicit_path_overrides_env(self, tmp_path):
        """明示的な path は環境変数より優先される"""
        path_a = str(tmp_path / "a.db")
        path_b = str(tmp_path / "b.db")
        with patch.dict("os.environ", {"LLM_MEMORY_DB_PATH": path_b}, clear=False):
            store = create_episode_memory_store(memory_db_path=path_a)
            assert store._db_path == path_a
            player_id = PlayerId(1)
            store.add(player_id, _make_episode_entry(eid="from_a"))
        store_b = create_episode_memory_store()
        store_b2 = create_episode_memory_store(memory_db_path=path_b)
        got_b = store_b2.get_recent(player_id, 10)
        assert len(got_b) == 0
        got_a = create_episode_memory_store(memory_db_path=path_a).get_recent(
            player_id, 10
        )
        assert len(got_a) == 1
        assert got_a[0].id == "from_a"

    def test_empty_string_path_uses_env_or_in_memory(self):
        """空文字 path は未指定扱い（環境変数があれば SQLite、なければ InMemory）"""
        with patch.dict("os.environ", {}, clear=False):
            env_backup = __import__("os").environ.pop("LLM_MEMORY_DB_PATH", None)
            try:
                store = create_episode_memory_store(memory_db_path="")
                assert store.__class__.__name__ == "InMemoryEpisodeMemoryStore"
            finally:
                if env_backup is not None:
                    __import__("os").environ["LLM_MEMORY_DB_PATH"] = env_backup

    def test_whitespace_path_stripped(self, tmp_path):
        """path 前後の空白はトリムされる"""
        db_path = str(tmp_path / "trim.db")
        store = create_episode_memory_store(memory_db_path=f"  {db_path}  ")
        assert store._db_path == db_path


class TestCreateLongTermMemoryStore:
    """create_long_term_memory_store の正常・境界ケース"""

    def test_with_path_returns_sqlite_store(self, tmp_path):
        """path を渡した場合 SqliteLongTermMemoryStore を返す"""
        db_path = str(tmp_path / "lt.db")
        store = create_long_term_memory_store(memory_db_path=db_path)
        assert isinstance(store, ILongTermMemoryStore)
        assert store.__class__.__name__ == "SqliteLongTermMemoryStore"

    def test_with_path_persists_data(self, tmp_path):
        """path 指定時は永続化され、add_fact した内容が search_facts で取得できる"""
        db_path = str(tmp_path / "lt.db")
        store1 = create_long_term_memory_store(memory_db_path=db_path)
        player_id = PlayerId(1)
        store1.add_fact(player_id, "洞窟の奥には宝がある")

        store2 = create_long_term_memory_store(memory_db_path=db_path)
        facts = store2.search_facts(player_id, limit=10)
        contents = [f.content for f in facts]
        assert "洞窟の奥には宝がある" in contents

    def test_without_path_returns_in_memory_store(self):
        """path を渡さず環境変数も未設定時は InMemoryLongTermMemoryStore を返す"""
        with patch.dict("os.environ", {}, clear=False):
            env_backup = __import__("os").environ.pop("LLM_MEMORY_DB_PATH", None)
            try:
                store = create_long_term_memory_store()
                assert isinstance(store, ILongTermMemoryStore)
                assert store.__class__.__name__ == "InMemoryLongTermMemoryStore"
            finally:
                if env_backup is not None:
                    __import__("os").environ["LLM_MEMORY_DB_PATH"] = env_backup

    def test_with_env_returns_sqlite_store(self, tmp_path):
        """環境変数 LLM_MEMORY_DB_PATH が設定されていれば Sqlite を返す"""
        db_path = str(tmp_path / "lt_env.db")
        with patch.dict("os.environ", {"LLM_MEMORY_DB_PATH": db_path}, clear=False):
            store = create_long_term_memory_store()
            assert store.__class__.__name__ == "SqliteLongTermMemoryStore"


class TestCreateReflectionStatePort:
    """create_reflection_state_port の正常・境界ケース"""

    def test_with_path_returns_sqlite_port(self, tmp_path):
        """path を渡した場合 SqliteReflectionStatePort を返す"""
        db_path = str(tmp_path / "ref.db")
        port = create_reflection_state_port(memory_db_path=db_path)
        assert port is not None
        assert isinstance(port, IReflectionStatePort)
        assert port.__class__.__name__ == "SqliteReflectionStatePort"

    def test_with_path_persists_data(self, tmp_path):
        """path 指定時は mark_reflection_success が永続化され取得できる"""
        db_path = str(tmp_path / "ref.db")
        port1 = create_reflection_state_port(memory_db_path=db_path)
        player_id = PlayerId(1)
        cursor = datetime(2025, 3, 13, 10, 0, 0)
        port1.mark_reflection_success(player_id, game_day=7, cursor=cursor)

        port2 = create_reflection_state_port(memory_db_path=db_path)
        got_day = port2.get_last_reflection_game_day(player_id)
        got_cursor = port2.get_reflection_cursor(player_id)
        assert got_day == 7
        assert got_cursor is not None
        assert got_cursor.year == 2025

    def test_without_path_returns_none(self):
        """path を渡さず環境変数も未設定時は None を返す"""
        with patch.dict("os.environ", {}, clear=False):
            env_backup = __import__("os").environ.pop("LLM_MEMORY_DB_PATH", None)
            try:
                port = create_reflection_state_port()
                assert port is None
            finally:
                if env_backup is not None:
                    __import__("os").environ["LLM_MEMORY_DB_PATH"] = env_backup

    def test_with_env_returns_sqlite_port(self, tmp_path):
        """環境変数 LLM_MEMORY_DB_PATH が設定されていれば SqliteReflectionStatePort を返す"""
        db_path = str(tmp_path / "ref_env.db")
        with patch.dict("os.environ", {"LLM_MEMORY_DB_PATH": db_path}, clear=False):
            port = create_reflection_state_port()
            assert port is not None
            assert port.__class__.__name__ == "SqliteReflectionStatePort"

    def test_empty_string_path_returns_none_when_env_unset(self):
        """空文字 path かつ環境変数未設定時は None を返す"""
        with patch.dict("os.environ", {}, clear=False):
            env_backup = __import__("os").environ.pop("LLM_MEMORY_DB_PATH", None)
            try:
                port = create_reflection_state_port(memory_db_path="")
                assert port is None
            finally:
                if env_backup is not None:
                    __import__("os").environ["LLM_MEMORY_DB_PATH"] = env_backup


class TestMemoryStoreFactoryExceptions:
    """memory_store_factory の例外・境界ケース"""

    def test_episode_store_with_none_path_no_raise(self):
        """memory_db_path=None を渡しても例外を出さずストアを返す"""
        with patch.dict("os.environ", {}, clear=False):
            env_backup = __import__("os").environ.pop("LLM_MEMORY_DB_PATH", None)
            try:
                store = create_episode_memory_store(memory_db_path=None)
                assert store is not None
                assert isinstance(store, IEpisodeMemoryStore)
            finally:
                if env_backup is not None:
                    __import__("os").environ["LLM_MEMORY_DB_PATH"] = env_backup

    def test_reflection_port_with_whitespace_only_path_returns_none(self):
        """path が空白のみの場合は未指定扱いで None を返す"""
        with patch.dict("os.environ", {}, clear=False):
            env_backup = __import__("os").environ.pop("LLM_MEMORY_DB_PATH", None)
            try:
                port = create_reflection_state_port(memory_db_path="   ")
                assert port is None
            finally:
                if env_backup is not None:
                    __import__("os").environ["LLM_MEMORY_DB_PATH"] = env_backup

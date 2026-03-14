"""_build_memory_stack のテスト（正常・境界・例外）"""

from unittest.mock import MagicMock, patch

import pytest

from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
from ai_rpg_world.application.llm.contracts.interfaces import (
    IEpisodeMemoryStore,
    ILongTermMemoryStore,
    IReflectionStatePort,
)
from ai_rpg_world.application.llm.services.handle_store import InMemoryHandleStore
from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
    InMemoryEpisodeMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
    InMemoryLongTermMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_todo_store import (
    InMemoryTodoStore,
)
from ai_rpg_world.application.llm.services.in_memory_working_memory_store import (
    InMemoryWorkingMemoryStore,
)
from ai_rpg_world.application.llm.wiring import (
    _MemoryStackResult,
    _build_memory_stack,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_episode_entry(
    eid: str = "ep1",
    context: str = "洞窟にいた",
    action: str = "move",
    outcome: str = "到着",
) -> EpisodeMemoryEntry:
    from datetime import datetime

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


class TestBuildMemoryStackReturnType:
    """_build_memory_stack の戻り値の型・構造"""

    def test_returns_memory_stack_result(self):
        """戻り値は _MemoryStackResult である"""
        result = _build_memory_stack()
        assert isinstance(result, _MemoryStackResult)

    def test_result_has_all_expected_attributes(self):
        """戻り値には episode, long_term, reflection_state_port, working, todo, handle が含まれる"""
        result = _build_memory_stack()
        assert hasattr(result, "episode_memory_store")
        assert hasattr(result, "long_term_memory_store")
        assert hasattr(result, "reflection_state_port")
        assert hasattr(result, "working_memory_store")
        assert hasattr(result, "todo_store")
        assert hasattr(result, "handle_store")

    def test_result_is_unpackable(self):
        """戻り値は unpack 可能である"""
        result = _build_memory_stack()
        ep, lt, ref, working, todo, handle = result
        assert ep is result.episode_memory_store
        assert lt is result.long_term_memory_store
        assert ref is result.reflection_state_port
        assert working is result.working_memory_store
        assert todo is result.todo_store
        assert handle is result.handle_store


class TestBuildMemoryStackEpisodeStore:
    """episode_memory_store の正常・境界ケース"""

    def test_without_path_returns_in_memory_store(self):
        """memory_db_path 未指定かつ環境変数未設定時は InMemoryEpisodeMemoryStore を返す"""
        with patch.dict("os.environ", {}, clear=False):
            env_backup = __import__("os").environ.pop("LLM_MEMORY_DB_PATH", None)
            try:
                result = _build_memory_stack()
                assert isinstance(result.episode_memory_store, IEpisodeMemoryStore)
                assert isinstance(
                    result.episode_memory_store, InMemoryEpisodeMemoryStore
                )
            finally:
                if env_backup is not None:
                    __import__("os").environ["LLM_MEMORY_DB_PATH"] = env_backup

    def test_with_path_returns_sqlite_store(self, tmp_path):
        """memory_db_path 指定時は SqliteEpisodeMemoryStore を返す"""
        db_path = str(tmp_path / "ep.db")
        result = _build_memory_stack(memory_db_path=db_path)
        assert isinstance(result.episode_memory_store, IEpisodeMemoryStore)
        assert result.episode_memory_store.__class__.__name__ == "SqliteEpisodeMemoryStore"

    def test_with_path_persists_data(self, tmp_path):
        """path 指定時は永続化され、同一 path で再生成すれば取得できる"""
        db_path = str(tmp_path / "ep.db")
        result1 = _build_memory_stack(memory_db_path=db_path)
        player_id = PlayerId(1)
        result1.episode_memory_store.add(
            player_id, _make_episode_entry(eid="e1", context="永続化テスト")
        )

        result2 = _build_memory_stack(memory_db_path=db_path)
        got = result2.episode_memory_store.get_recent(player_id, 10)
        assert len(got) == 1
        assert got[0].id == "e1"
        assert got[0].context_summary == "永続化テスト"

    def test_episode_store_override_is_used(self):
        """episode_memory_store を渡した場合はそれが使われる"""
        custom_store = InMemoryEpisodeMemoryStore()
        custom_store.add(PlayerId(1), _make_episode_entry(eid="custom"))
        result = _build_memory_stack(episode_memory_store=custom_store)
        assert result.episode_memory_store is custom_store
        got = result.episode_memory_store.get_recent(PlayerId(1), 10)
        assert len(got) == 1
        assert got[0].id == "custom"


class TestBuildMemoryStackLongTermStore:
    """long_term_memory_store の正常・境界ケース"""

    def test_without_path_returns_in_memory_store(self):
        """memory_db_path 未指定かつ環境変数未設定時は InMemoryLongTermMemoryStore を返す"""
        with patch.dict("os.environ", {}, clear=False):
            env_backup = __import__("os").environ.pop("LLM_MEMORY_DB_PATH", None)
            try:
                result = _build_memory_stack()
                assert isinstance(result.long_term_memory_store, ILongTermMemoryStore)
                assert isinstance(
                    result.long_term_memory_store, InMemoryLongTermMemoryStore
                )
            finally:
                if env_backup is not None:
                    __import__("os").environ["LLM_MEMORY_DB_PATH"] = env_backup

    def test_with_path_returns_sqlite_store(self, tmp_path):
        """memory_db_path 指定時は SqliteLongTermMemoryStore を返す"""
        db_path = str(tmp_path / "lt.db")
        result = _build_memory_stack(memory_db_path=db_path)
        assert isinstance(result.long_term_memory_store, ILongTermMemoryStore)
        assert (
            result.long_term_memory_store.__class__.__name__
            == "SqliteLongTermMemoryStore"
        )

    def test_long_term_store_override_is_used(self):
        """long_term_memory_store を渡した場合はそれが使われる"""
        custom_store = InMemoryLongTermMemoryStore()
        custom_store.add_fact(PlayerId(1), "カスタム事実")
        result = _build_memory_stack(long_term_memory_store=custom_store)
        assert result.long_term_memory_store is custom_store
        facts = result.long_term_memory_store.search_facts(PlayerId(1), limit=10)
        assert any("カスタム事実" in f.content for f in facts)


class TestBuildMemoryStackReflectionStatePort:
    """reflection_state_port の正常・境界ケース"""

    def test_without_path_returns_none(self):
        """memory_db_path 未指定かつ環境変数未設定時は None を返す"""
        with patch.dict("os.environ", {}, clear=False):
            env_backup = __import__("os").environ.pop("LLM_MEMORY_DB_PATH", None)
            try:
                result = _build_memory_stack()
                assert result.reflection_state_port is None
            finally:
                if env_backup is not None:
                    __import__("os").environ["LLM_MEMORY_DB_PATH"] = env_backup

    def test_with_path_returns_sqlite_port(self, tmp_path):
        """memory_db_path 指定時は SqliteReflectionStatePort を返す"""
        db_path = str(tmp_path / "ref.db")
        result = _build_memory_stack(memory_db_path=db_path)
        assert result.reflection_state_port is not None
        assert isinstance(result.reflection_state_port, IReflectionStatePort)
        assert (
            result.reflection_state_port.__class__.__name__
            == "SqliteReflectionStatePort"
        )

    def test_reflection_state_port_override_is_used(self):
        """reflection_state_port を渡した場合はそれが使われる（None でも）"""
        result = _build_memory_stack(reflection_state_port=None)
        assert result.reflection_state_port is None

    def test_reflection_state_port_custom_port_override(self):
        """reflection_state_port に IReflectionStatePort 実装を渡した場合はそれが使われる"""
        mock_port = MagicMock(spec=IReflectionStatePort)
        mock_port.get_last_reflection_game_day.return_value = None
        mock_port.get_reflection_cursor.return_value = None
        mock_port.mark_reflection_success = MagicMock()
        result = _build_memory_stack(reflection_state_port=mock_port)
        assert result.reflection_state_port is mock_port


class TestBuildMemoryStackWorkingTodoHandle:
    """working_memory_store, todo_store, handle_store の正常ケース"""

    def test_working_memory_store_is_in_memory(self):
        """working_memory_store は常に InMemoryWorkingMemoryStore"""
        result = _build_memory_stack()
        assert isinstance(result.working_memory_store, InMemoryWorkingMemoryStore)
        result.working_memory_store.append(PlayerId(1), "作業メモ")
        got = result.working_memory_store.get_recent(PlayerId(1), 10)
        assert len(got) == 1
        assert got[0] == "作業メモ"

    def test_todo_store_is_in_memory(self):
        """todo_store は常に InMemoryTodoStore"""
        result = _build_memory_stack()
        assert isinstance(result.todo_store, InMemoryTodoStore)
        todo_id = result.todo_store.add(PlayerId(1), "タスク1")
        assert todo_id
        uncompleted = result.todo_store.list_uncompleted(PlayerId(1))
        assert len(uncompleted) == 1
        assert uncompleted[0].content == "タスク1"

    def test_handle_store_is_in_memory(self):
        """handle_store は常に InMemoryHandleStore"""
        result = _build_memory_stack()
        assert isinstance(result.handle_store, InMemoryHandleStore)
        result.handle_store.put(PlayerId(1), "h1", [{"k": "v"}], "expr")
        got = result.handle_store.get(PlayerId(1), "h1")
        assert got == [{"k": "v"}]

    def test_each_call_creates_new_in_memory_instances(self):
        """呼び出しごとに working, todo, handle は新規インスタンス"""
        r1 = _build_memory_stack()
        r2 = _build_memory_stack()
        assert r1.working_memory_store is not r2.working_memory_store
        assert r1.todo_store is not r2.todo_store
        assert r1.handle_store is not r2.handle_store


class TestBuildMemoryStackEnvVar:
    """環境変数 LLM_MEMORY_DB_PATH の扱い"""

    def test_with_env_returns_sqlite_stores(self, tmp_path):
        """環境変数 LLM_MEMORY_DB_PATH が設定されていれば Sqlite 系を返す"""
        db_path = str(tmp_path / "env.db")
        with patch.dict("os.environ", {"LLM_MEMORY_DB_PATH": db_path}, clear=False):
            result = _build_memory_stack()
            assert result.episode_memory_store.__class__.__name__ == "SqliteEpisodeMemoryStore"
            assert result.long_term_memory_store.__class__.__name__ == "SqliteLongTermMemoryStore"
            assert result.reflection_state_port is not None
            assert result.reflection_state_port.__class__.__name__ == "SqliteReflectionStatePort"

    def test_explicit_path_overrides_env(self, tmp_path):
        """明示的な memory_db_path は環境変数より優先される"""
        path_a = str(tmp_path / "a.db")
        path_b = str(tmp_path / "b.db")
        with patch.dict("os.environ", {"LLM_MEMORY_DB_PATH": path_b}, clear=False):
            result = _build_memory_stack(memory_db_path=path_a)
            assert result.episode_memory_store._db_path == path_a

    def test_empty_string_path_uses_env_or_in_memory(self):
        """空文字 memory_db_path は未指定扱い"""
        with patch.dict("os.environ", {}, clear=False):
            env_backup = __import__("os").environ.pop("LLM_MEMORY_DB_PATH", None)
            try:
                result = _build_memory_stack(memory_db_path="")
                assert isinstance(
                    result.episode_memory_store, InMemoryEpisodeMemoryStore
                )
                assert result.reflection_state_port is None
            finally:
                if env_backup is not None:
                    __import__("os").environ["LLM_MEMORY_DB_PATH"] = env_backup

    def test_whitespace_path_stripped(self, tmp_path):
        """memory_db_path 前後の空白はトリムされる"""
        db_path = str(tmp_path / "trim.db")
        result = _build_memory_stack(memory_db_path=f"  {db_path}  ")
        assert result.episode_memory_store._db_path == db_path


def _minimal_wiring_deps():
    """create_llm_agent_wiring に渡す最小限のモック依存を返す。"""
    from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
    from ai_rpg_world.application.world.services.world_query_service import (
        WorldQueryService,
    )
    from ai_rpg_world.application.world.services.movement_service import (
        MovementApplicationService,
    )
    from ai_rpg_world.domain.player.repository.player_profile_repository import (
        PlayerProfileRepository,
    )
    from ai_rpg_world.domain.player.repository.player_status_repository import (
        PlayerStatusRepository,
    )
    from ai_rpg_world.domain.world.repository.physical_map_repository import (
        PhysicalMapRepository,
    )

    uow_factory = MagicMock(spec=UnitOfWorkFactory)
    uow_factory.create.return_value = MagicMock()
    uow_factory.create.return_value.__enter__ = MagicMock(return_value=MagicMock())
    uow_factory.create.return_value.__exit__ = MagicMock(return_value=False)
    world_query = MagicMock(spec=WorldQueryService)
    world_query.get_player_current_state = MagicMock(return_value=None)
    movement = MagicMock(spec=MovementApplicationService)
    movement.move_to_destination = MagicMock()
    movement.cancel_movement = MagicMock()
    return {
        "player_status_repository": MagicMock(spec=PlayerStatusRepository),
        "physical_map_repository": MagicMock(spec=PhysicalMapRepository),
        "world_query_service": world_query,
        "movement_service": movement,
        "player_profile_repository": MagicMock(spec=PlayerProfileRepository),
        "unit_of_work_factory": uow_factory,
    }


class TestBuildMemoryStackIntegration:
    """create_llm_agent_wiring 経由での統合確認"""

    def test_wiring_uses_memory_stack_from_build(self):
        """create_llm_agent_wiring で _build_memory_stack 経由のストアが使われる"""
        from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring

        deps = _minimal_wiring_deps()
        result = create_llm_agent_wiring(**deps)
        episode_store = (
            result.llm_turn_trigger._turn_runner._orchestrator._episode_memory_store
        )
        assert isinstance(episode_store, IEpisodeMemoryStore)

    def test_wiring_with_memory_db_path_uses_sqlite(self, tmp_path):
        """create_llm_agent_wiring に memory_db_path を渡すと Sqlite が使われる"""
        from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring
        from ai_rpg_world.infrastructure.llm.sqlite_episode_memory_store import (
            SqliteEpisodeMemoryStore,
        )

        deps = _minimal_wiring_deps()
        deps["memory_db_path"] = str(tmp_path / "wiring.db")
        result = create_llm_agent_wiring(**deps)
        episode_store = (
            result.llm_turn_trigger._turn_runner._orchestrator._episode_memory_store
        )
        assert isinstance(episode_store, SqliteEpisodeMemoryStore)

"""_build_reflection_stack のテスト（正常・境界・例外）"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.interfaces import (
    IReflectionRunner,
    IReflectionService,
)
from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
    InMemoryEpisodeMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
    InMemoryLongTermMemoryStore,
)
from ai_rpg_world.application.llm.services.llm_player_resolver import (
    ProfileBasedLlmPlayerResolver,
)
from ai_rpg_world.application.llm.services.reflection_service import (
    RuleBasedReflectionService,
)
from ai_rpg_world.application.llm.wiring import (
    _build_reflection_stack,
    _ReflectionStackResult,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world.service.world_time_config_service import (
    DefaultWorldTimeConfigService,
    WorldTimeConfigService,
)


def _minimal_deps():
    """_build_reflection_stack に渡す最小限の依存を返す。"""
    episode_store = InMemoryEpisodeMemoryStore()
    long_term_store = InMemoryLongTermMemoryStore()
    player_status_repo = MagicMock(spec=PlayerStatusRepository)
    player_profile_repo = MagicMock(spec=PlayerProfileRepository)
    llm_player_resolver = ProfileBasedLlmPlayerResolver(
        player_profile_repository=player_profile_repo,
    )
    return {
        "episode_memory_store": episode_store,
        "long_term_memory_store": long_term_store,
        "reflection_state_port": None,
        "player_status_repository": player_status_repo,
        "llm_player_resolver": llm_player_resolver,
    }


class TestBuildReflectionStackReturnType:
    """_build_reflection_stack の戻り値（正常）"""

    def test_returns_reflection_stack_result(self):
        """返り値は _ReflectionStackResult のタプルである"""
        deps = _minimal_deps()
        result = _build_reflection_stack(**deps)
        assert isinstance(result, _ReflectionStackResult)

    def test_result_has_reflection_service_and_runner(self):
        """返り値は reflection_service と reflection_runner を持つ"""
        deps = _minimal_deps()
        result = _build_reflection_stack(**deps)
        assert hasattr(result, "reflection_service")
        assert hasattr(result, "reflection_runner")
        assert isinstance(result.reflection_service, RuleBasedReflectionService)

    def test_result_is_unpackable(self):
        """返り値は unpacking で (reflection_service, reflection_runner) 取得可能"""
        deps = _minimal_deps()
        deps["world_time_config_service"] = DefaultWorldTimeConfigService(
            ticks_per_day=24
        )
        result = _build_reflection_stack(**deps)
        svc, runner = result
        assert svc is result.reflection_service
        assert runner is result.reflection_runner


class TestBuildReflectionStackReflectionService:
    """reflection_service の構築（正常）"""

    def test_reflection_service_is_rule_based(self):
        """reflection_service は RuleBasedReflectionService"""
        deps = _minimal_deps()
        result = _build_reflection_stack(**deps)
        assert isinstance(result.reflection_service, IReflectionService)
        assert isinstance(result.reflection_service, RuleBasedReflectionService)

    def test_reflection_service_uses_provided_stores(self):
        """渡した episode / long_term store が reflection_service に渡される"""
        episode_store = InMemoryEpisodeMemoryStore()
        long_term_store = InMemoryLongTermMemoryStore()
        deps = _minimal_deps()
        deps["episode_memory_store"] = episode_store
        deps["long_term_memory_store"] = long_term_store
        result = _build_reflection_stack(**deps)
        assert result.reflection_service._episode_store is episode_store
        assert result.reflection_service._long_term_store is long_term_store


class TestBuildReflectionStackReflectionRunner:
    """reflection_runner の構築（正常・境界）"""

    def test_when_world_time_config_provided_runner_is_created(self):
        """world_time_config_service が WorldTimeConfigService のとき reflection_runner が作成される"""
        deps = _minimal_deps()
        deps["world_time_config_service"] = DefaultWorldTimeConfigService(
            ticks_per_day=24
        )
        result = _build_reflection_stack(**deps)
        assert result.reflection_runner is not None
        assert isinstance(result.reflection_runner, IReflectionRunner)
        assert hasattr(result.reflection_runner, "run_after_tick")
        assert callable(result.reflection_runner.run_after_tick)

    def test_when_world_time_config_none_runner_is_none(self):
        """world_time_config_service が None のとき reflection_runner は None"""
        deps = _minimal_deps()
        deps["world_time_config_service"] = None
        result = _build_reflection_stack(**deps)
        assert result.reflection_runner is None

    def test_when_world_time_config_not_world_time_config_service_runner_is_none(
        self,
    ):
        """world_time_config_service が WorldTimeConfigService でないとき reflection_runner は None"""
        deps = _minimal_deps()
        deps["world_time_config_service"] = "invalid"
        result = _build_reflection_stack(**deps)
        assert result.reflection_runner is None

    def test_runner_run_after_tick_does_not_raise(self):
        """reflection_runner.run_after_tick を呼んでも例外が出ない"""
        deps = _minimal_deps()
        deps["world_time_config_service"] = DefaultWorldTimeConfigService(
            ticks_per_day=24
        )
        result = _build_reflection_stack(**deps)
        assert result.reflection_runner is not None
        result.reflection_runner.run_after_tick(WorldTick(0))

    def test_runner_uses_provided_state_port(self, tmp_path):
        """reflection_state_port を渡した場合 runner に渡される"""
        from ai_rpg_world.infrastructure.llm._memory_store_factory import (
            create_reflection_state_port,
        )

        db_path = str(tmp_path / "ref.db")
        port = create_reflection_state_port(memory_db_path=db_path)
        deps = _minimal_deps()
        deps["reflection_state_port"] = port
        deps["world_time_config_service"] = DefaultWorldTimeConfigService(
            ticks_per_day=24
        )
        result = _build_reflection_stack(**deps)
        assert result.reflection_runner is not None
        assert result.reflection_runner._state_port is port


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


class TestBuildReflectionStackIntegration:
    """create_llm_agent_wiring 経由での統合確認"""

    def test_wiring_reflection_runner_from_build(self):
        """create_llm_agent_wiring で _build_reflection_stack 経由の runner が使われる"""
        from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring

        deps = _minimal_wiring_deps()
        deps["world_time_config_service"] = DefaultWorldTimeConfigService(
            ticks_per_day=24
        )
        result = create_llm_agent_wiring(**deps)
        assert result.reflection_runner is not None
        assert isinstance(result.reflection_runner, IReflectionRunner)
        result.reflection_runner.run_after_tick(WorldTick(0))

    def test_wiring_without_world_time_config_returns_none_runner(self):
        """create_llm_agent_wiring に world_time_config_service を渡さない場合 reflection_runner は None"""
        from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring

        deps = _minimal_wiring_deps()
        result = create_llm_agent_wiring(**deps)
        assert result.reflection_runner is None

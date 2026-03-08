"""DefaultReflectionRunner のテスト（正常・境界・runtime 接続）"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
    InMemoryEpisodeMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
    InMemoryLongTermMemoryStore,
)
from ai_rpg_world.application.llm.services.llm_player_resolver import (
    SetBasedLlmPlayerResolver,
)
from ai_rpg_world.application.llm.services.reflection_runner import (
    DefaultReflectionRunner,
)
from ai_rpg_world.application.llm.services.reflection_service import (
    RuleBasedReflectionService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.service.world_time_config_service import (
    DefaultWorldTimeConfigService,
)


def _make_episode(eid: str, recall_count: int = 2) -> EpisodeMemoryEntry:
    from datetime import datetime

    return EpisodeMemoryEntry(
        id=eid,
        context_summary="洞窟でチェストを発見",
        action_taken="open_chest を実行",
        outcome_summary="回復ポーションを入手",
        entity_ids=("chest_1",),
        location_id=None,
        timestamp=datetime.now(),
        importance="medium",
        surprise=False,
        recall_count=recall_count,
    )


class TestDefaultReflectionRunner:
    """DefaultReflectionRunner の正常・境界・runtime 接続ケース"""

    @pytest.fixture
    def episode_store(self):
        return InMemoryEpisodeMemoryStore()

    @pytest.fixture
    def long_term_store(self):
        return InMemoryLongTermMemoryStore()

    @pytest.fixture
    def reflection_service(self, episode_store, long_term_store):
        return RuleBasedReflectionService(
            episode_store=episode_store,
            long_term_store=long_term_store,
        )

    @pytest.fixture
    def player_status_repository(self):
        from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
            InMemoryDataStore,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
            InMemoryPlayerStatusRepository,
        )
        from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
            InMemoryUnitOfWork,
        )

        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(
                unit_of_work_factory=create_uow, data_store=data_store
            )

        uow, _ = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow, data_store=data_store
        )
        return InMemoryPlayerStatusRepository(
            data_store=data_store, unit_of_work=uow
        )

    @pytest.fixture
    def llm_player_resolver(self):
        return SetBasedLlmPlayerResolver(set())

    @pytest.fixture
    def world_time_config(self):
        return DefaultWorldTimeConfigService(ticks_per_day=24)

    @pytest.fixture
    def runner(
        self,
        reflection_service,
        player_status_repository,
        llm_player_resolver,
        world_time_config,
    ):
        return DefaultReflectionRunner(
            reflection_service=reflection_service,
            player_status_repository=player_status_repository,
            llm_player_resolver=llm_player_resolver,
            world_time_config=world_time_config,
        )

    def test_run_after_tick_with_no_players_does_not_raise(self, runner):
        """LLM プレイヤーがいないとき run_after_tick は正常終了する"""
        runner.run_after_tick(WorldTick(0))
        runner.run_after_tick(WorldTick(50))

    def test_run_after_tick_triggers_reflection_for_llm_player_on_day_boundary(
        self,
        episode_store,
        long_term_store,
        reflection_service,
        world_time_config,
    ):
        """game day が変わると LLM プレイヤーに reflection が実行され長期記憶に追加される"""
        from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
            PlayerStatusAggregate,
        )
        from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
        from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
        from ai_rpg_world.domain.player.value_object.gold import Gold
        from ai_rpg_world.domain.player.value_object.growth import Growth
        from ai_rpg_world.domain.player.value_object.hp import Hp
        from ai_rpg_world.domain.player.value_object.mp import Mp
        from ai_rpg_world.domain.player.value_object.stat_growth_factor import (
            StatGrowthFactor,
        )
        from ai_rpg_world.domain.player.value_object.stamina import Stamina
        from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
            InMemoryDataStore,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
            InMemoryPlayerStatusRepository,
        )
        from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
            InMemoryUnitOfWork,
        )

        exp_table = ExpTable(100, 1.5)
        status = PlayerStatusAggregate(
            player_id=PlayerId(1),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold.create(0),
            hp=Hp.create(10, 10),
            mp=Mp.create(10, 10),
            stamina=Stamina.create(10, 10),
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        )
        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(
                unit_of_work_factory=create_uow, data_store=data_store
            )

        uow, _ = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow, data_store=data_store
        )
        player_status_repository = InMemoryPlayerStatusRepository(
            data_store=data_store, unit_of_work=uow
        )
        player_status_repository.save(status)

        runner = DefaultReflectionRunner(
            reflection_service=reflection_service,
            player_status_repository=player_status_repository,
            llm_player_resolver=SetBasedLlmPlayerResolver({1}),
            world_time_config=world_time_config,
        )

        episode_store.add(PlayerId(1), _make_episode("e1"))

        runner.run_after_tick(WorldTick(24))

        facts = long_term_store.search_facts(PlayerId(1), limit=10)
        assert len(facts) >= 1
        assert "洞窟" in facts[0].content or "チェスト" in facts[0].content

    def test_run_after_tick_ticks_per_day_zero_returns_early(self):
        """ticks_per_day が 0 のとき early return（クラッシュしない）"""
        from ai_rpg_world.domain.world.service.world_time_config_service import (
            WorldTimeConfigService,
        )

        class ZeroTicksWorldTimeConfig(WorldTimeConfigService):
            def get_ticks_per_day(self) -> int:
                return 0

            def get_days_per_month(self) -> int:
                return 30

            def get_months_per_year(self) -> int:
                return 12

        world_time_config = ZeroTicksWorldTimeConfig()
        from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
            InMemoryDataStore,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
            InMemoryPlayerStatusRepository,
        )
        from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
            InMemoryUnitOfWork,
        )

        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(
                unit_of_work_factory=create_uow, data_store=data_store
            )

        uow, _ = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow, data_store=data_store
        )
        player_status_repository = InMemoryPlayerStatusRepository(
            data_store=data_store, unit_of_work=uow
        )

        runner = DefaultReflectionRunner(
            reflection_service=RuleBasedReflectionService(
                episode_store=InMemoryEpisodeMemoryStore(),
                long_term_store=InMemoryLongTermMemoryStore(),
            ),
            player_status_repository=player_status_repository,
            llm_player_resolver=SetBasedLlmPlayerResolver(set()),
            world_time_config=world_time_config,
        )
        runner.run_after_tick(WorldTick(0))

    def test_init_reflection_service_not_interface_raises_type_error(
        self, player_status_repository, llm_player_resolver, world_time_config
    ):
        """reflection_service が IReflectionService でないとき TypeError"""
        with pytest.raises(TypeError, match="reflection_service must be IReflectionService"):
            DefaultReflectionRunner(
                reflection_service=None,  # type: ignore[arg-type]
                player_status_repository=player_status_repository,
                llm_player_resolver=llm_player_resolver,
                world_time_config=world_time_config,
            )

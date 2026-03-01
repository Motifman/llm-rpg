"""ObservationEventHandler のテスト（正常・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.observation.handlers.observation_event_handler import ObservationEventHandler
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.observation.services.observation_formatter import ObservationFormatter
from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.event.map_events import GatewayTriggeredEvent
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.event.status_events import PlayerGoldEarnedEvent
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


def _make_status(player_id: int, spot_id: int = 1) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(1000),
        hp=Hp.create(100, 100),
        mp=Mp.create(50, 50),
        stamina=Stamina.create(100, 100),
        current_spot_id=SpotId(spot_id),
        current_coordinate=Coordinate(0, 0, 0),
    )


class TestObservationEventHandler:
    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def unit_of_work_factory(self, data_store):
        class Factory:
            def __init__(self, ds):
                self._ds = ds
            def create(self):
                return InMemoryUnitOfWork(
                    unit_of_work_factory=self, data_store=self._ds
                )
        return Factory(data_store)

    @pytest.fixture
    def buffer(self):
        return DefaultObservationContextBuffer()

    @pytest.fixture
    def physical_map_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    @pytest.fixture
    def resolver(self, status_repo, physical_map_repo):
        return create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=physical_map_repo,
        )

    @pytest.fixture
    def formatter(self):
        return ObservationFormatter()

    @pytest.fixture
    def handler(self, resolver, formatter, buffer, unit_of_work_factory):
        return ObservationEventHandler(
            resolver=resolver,
            formatter=formatter,
            buffer=buffer,
            unit_of_work_factory=unit_of_work_factory,
        )

    def test_handle_gateway_triggered_appends_observation_to_buffer(
        self, handler, buffer, status_repo
    ):
        """GatewayTriggeredEvent 処理で本人に観測が蓄積される"""
        status_repo.save(_make_status(1, spot_id=1))
        event = GatewayTriggeredEvent.create(
            aggregate_id=GatewayId(1),
            aggregate_type="Gateway",
            gateway_id=GatewayId(1),
            spot_id=SpotId(1),
            object_id=WorldObjectId(1),
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
            player_id_value=1,
        )
        handler.handle(event)
        entries = buffer.get_observations(PlayerId(1))
        assert len(entries) == 1
        assert "到着" in entries[0].output.prose
        assert entries[0].output.structured.get("type") == "gateway_arrival"

    def test_handle_player_gold_earned_appends_to_buffer(self, handler, buffer):
        """PlayerGoldEarnedEvent で観測が蓄積される"""
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        handler.handle(event)
        entries = buffer.get_observations(PlayerId(1))
        assert len(entries) == 1
        assert "100" in entries[0].output.prose

    def test_handle_unknown_event_does_not_raise_and_adds_nothing(self, handler, buffer):
        """未知のイベントでは resolver が空を返し観測は追加されない"""
        class UnknownEvent:
            occurred_at = None
        handler.handle(UnknownEvent())
        assert len(buffer.get_observations(PlayerId(1))) == 0

    def test_handle_when_resolver_raises_propagates_after_system_error_wrap(
        self, buffer, formatter, data_store
    ):
        """Resolver が例外を投げた場合、SystemErrorException でラップされて伝播する"""
        class Factory:
            def __init__(self, ds):
                self._ds = ds
            def create(self):
                return InMemoryUnitOfWork(
                    unit_of_work_factory=self, data_store=self._ds
                )
        broken_resolver = MagicMock()
        broken_resolver.resolve.side_effect = RuntimeError("repo error")
        handler = ObservationEventHandler(
            resolver=broken_resolver,
            formatter=formatter,
            buffer=buffer,
            unit_of_work_factory=Factory(data_store),
        )
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=10,
            total_gold=1010,
        )
        with pytest.raises(SystemErrorException, match="Observation.*failed"):
            handler.handle(event)

    def test_handle_when_formatter_raises_propagates_after_system_error_wrap(
        self, resolver, buffer, data_store
    ):
        """Formatter が例外を投げた場合、SystemErrorException でラップされて伝播する"""
        class Factory:
            def __init__(self, ds):
                self._ds = ds
            def create(self):
                return InMemoryUnitOfWork(
                    unit_of_work_factory=self, data_store=self._ds
                )
        broken_formatter = MagicMock()
        broken_formatter.format.side_effect = RuntimeError("format error")
        handler = ObservationEventHandler(
            resolver=resolver,
            formatter=broken_formatter,
            buffer=buffer,
            unit_of_work_factory=Factory(data_store),
        )
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=10,
            total_gold=1010,
        )
        with pytest.raises(SystemErrorException, match="Observation.*failed"):
            handler.handle(event)

    def test_handle_when_buffer_append_raises_propagates_after_system_error_wrap(
        self, resolver, formatter, data_store
    ):
        """Buffer.append が例外を投げた場合、SystemErrorException でラップされて伝播する"""
        class Factory:
            def __init__(self, ds):
                self._ds = ds
            def create(self):
                return InMemoryUnitOfWork(
                    unit_of_work_factory=self, data_store=self._ds
                )
        broken_buffer = MagicMock()
        broken_buffer.append.side_effect = RuntimeError("buffer write error")
        handler = ObservationEventHandler(
            resolver=resolver,
            formatter=formatter,
            buffer=broken_buffer,
            unit_of_work_factory=Factory(data_store),
        )
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=10,
            total_gold=1010,
        )
        with pytest.raises(SystemErrorException, match="Observation.*failed"):
            handler.handle(event)

    def test_handle_when_domain_exception_raised_propagates_unchanged(
        self, buffer, formatter, data_store
    ):
        """Resolver が DomainException を投げた場合、ラップせずそのまま伝播する"""
        class Factory:
            def __init__(self, ds):
                self._ds = ds
            def create(self):
                return InMemoryUnitOfWork(
                    unit_of_work_factory=self, data_store=self._ds
                )
        broken_resolver = MagicMock()
        broken_resolver.resolve.side_effect = DomainException("domain validation failed")
        handler = ObservationEventHandler(
            resolver=broken_resolver,
            formatter=formatter,
            buffer=buffer,
            unit_of_work_factory=Factory(data_store),
        )
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=10,
            total_gold=1010,
        )
        with pytest.raises(DomainException, match="domain validation failed"):
            handler.handle(event)

    def test_handle_when_application_exception_raised_propagates_unchanged(
        self, resolver, buffer, data_store
    ):
        """Formatter が ApplicationException を投げた場合、ラップせずそのまま伝播する"""
        class Factory:
            def __init__(self, ds):
                self._ds = ds
            def create(self):
                return InMemoryUnitOfWork(
                    unit_of_work_factory=self, data_store=self._ds
                )
        broken_formatter = MagicMock()
        broken_formatter.format.side_effect = ApplicationException("app validation failed")
        handler = ObservationEventHandler(
            resolver=resolver,
            formatter=broken_formatter,
            buffer=buffer,
            unit_of_work_factory=Factory(data_store),
        )
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=10,
            total_gold=1010,
        )
        with pytest.raises(ApplicationException, match="app validation failed"):
            handler.handle(event)


class TestObservationEventHandlerRegistry:
    """ObservationEventHandlerRegistry で非同期ハンドラが全観測対象イベント型に登録されること"""

    def test_register_handlers_registers_async_for_all_observed_event_types(self):
        from ai_rpg_world.infrastructure.events.observation_event_handler_registry import (
            ObservationEventHandlerRegistry,
        )
        from ai_rpg_world.domain.world.event.map_events import GatewayTriggeredEvent

        handler = MagicMock()
        registry = ObservationEventHandlerRegistry(observation_handler=handler)
        event_publisher = MagicMock()

        registry.register_handlers(event_publisher)

        calls = event_publisher.register_handler.call_args_list
        assert len(calls) >= 10
        event_types_registered = {c[0][0] for c in calls}
        assert GatewayTriggeredEvent in event_types_registered
        for call in calls:
            assert call[1]["is_synchronous"] is False
            assert call[0][1] is handler

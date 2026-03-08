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
from ai_rpg_world.application.llm.services.llm_player_resolver import SetBasedLlmPlayerResolver
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
from ai_rpg_world.domain.world.service.world_time_config_service import (
    DefaultWorldTimeConfigService,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.event.status_events import (
    PlayerDownedEvent,
    PlayerGoldEarnedEvent,
    PlayerLocationChangedEvent,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)


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

    def test_handle_player_location_changed_appends_observation_to_buffer(
        self, handler, buffer, status_repo
    ):
        """PlayerLocationChangedEvent 処理で本人に観測が蓄積される"""
        status_repo.save(_make_status(1, spot_id=1))
        event = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(0, 0, 0),
        )
        handler.handle(event)
        entries = buffer.get_observations(PlayerId(1))
        assert len(entries) == 1
        assert "現在地" in entries[0].output.prose
        assert entries[0].output.structured.get("type") == "current_location"

    def test_handle_when_no_game_time_provider_entry_has_no_game_time_label(
        self, handler, buffer
    ):
        """game_time_provider 未設定時は観測エントリの game_time_label が None"""
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        handler.handle(event)
        entries = buffer.get_observations(PlayerId(1))
        assert len(entries) == 1
        assert entries[0].game_time_label is None

    def test_handle_when_game_time_provider_and_config_set_entry_has_game_time_label(
        self, resolver, formatter, buffer, unit_of_work_factory
    ):
        """game_time_provider と world_time_config を渡すと観測にゲーム内時刻ラベルが付与される"""
        game_time_provider = InMemoryGameTimeProvider(initial_tick=3600)
        world_time_config = DefaultWorldTimeConfigService(
            ticks_per_day=86400,
            days_per_month=30,
            months_per_year=12,
        )
        handler = ObservationEventHandler(
            resolver=resolver,
            formatter=formatter,
            buffer=buffer,
            unit_of_work_factory=unit_of_work_factory,
            game_time_provider=game_time_provider,
            world_time_config=world_time_config,
        )
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        handler.handle(event)
        entries = buffer.get_observations(PlayerId(1))
        assert len(entries) == 1
        assert entries[0].game_time_label is not None
        assert "1年1月1日" in entries[0].game_time_label
        assert "01:00:00" in entries[0].game_time_label

    def test_handle_when_only_game_time_provider_set_no_label(
        self, resolver, formatter, buffer, unit_of_work_factory
    ):
        """game_time_provider のみで world_time_config が無いときは game_time_label は None"""
        handler = ObservationEventHandler(
            resolver=resolver,
            formatter=formatter,
            buffer=buffer,
            unit_of_work_factory=unit_of_work_factory,
            game_time_provider=InMemoryGameTimeProvider(0),
            world_time_config=None,
        )
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        handler.handle(event)
        entries = buffer.get_observations(PlayerId(1))
        assert len(entries) == 1
        assert entries[0].game_time_label is None

    def test_handle_when_only_world_time_config_set_no_label(
        self, resolver, formatter, buffer, unit_of_work_factory
    ):
        """world_time_config のみで game_time_provider が無いときは game_time_label は None"""
        handler = ObservationEventHandler(
            resolver=resolver,
            formatter=formatter,
            buffer=buffer,
            unit_of_work_factory=unit_of_work_factory,
            game_time_provider=None,
            world_time_config=DefaultWorldTimeConfigService(ticks_per_day=86400),
        )
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        handler.handle(event)
        entries = buffer.get_observations(PlayerId(1))
        assert len(entries) == 1
        assert entries[0].game_time_label is None

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


class TestObservationEventHandlerLlmTurnScheduling:
    """turn_trigger と llm_player_resolver を渡したときの LLM ターンスケジュール（正常・境界）"""

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
    def turn_trigger(self):
        return MagicMock()

    @pytest.fixture
    def llm_player_resolver_include_one(self):
        """プレイヤー 1 を LLM 制御とするリゾルバ"""
        return SetBasedLlmPlayerResolver({1})

    @pytest.fixture
    def llm_player_resolver_include_two_only(self):
        """プレイヤー 2 のみ LLM 制御とするリゾルバ"""
        return SetBasedLlmPlayerResolver({2})

    def test_handle_when_llm_player_schedules_turn_only_on_schedules_turn(
        self,
        resolver,
        formatter,
        buffer,
        unit_of_work_factory,
        turn_trigger,
        llm_player_resolver_include_one,
    ):
        """schedules_turn=True の観測（PlayerDowned は schedules_turn も breaks_movement も true）で schedule_turn が呼ばれる"""
        handler = ObservationEventHandler(
            resolver=resolver,
            formatter=formatter,
            buffer=buffer,
            unit_of_work_factory=unit_of_work_factory,
            turn_trigger=turn_trigger,
            llm_player_resolver=llm_player_resolver_include_one,
        )
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
        )
        handler.handle(event)

        assert len(buffer.get_observations(PlayerId(1))) == 1
        turn_trigger.schedule_turn.assert_called_once_with(PlayerId(1))

    def test_handle_when_breaks_movement_only_cancels_but_does_not_schedule(
        self,
        resolver,
        buffer,
        unit_of_work_factory,
        turn_trigger,
        llm_player_resolver_include_one,
    ):
        """breaks_movement のみの観測では cancel_movement が呼ばれ schedule_turn は呼ばれない"""
        mock_formatter = MagicMock()
        mock_formatter.format.return_value = __import__(
            "ai_rpg_world.application.observation.contracts.dtos", fromlist=["ObservationOutput"]
        ).ObservationOutput(
            prose="被弾した",
            structured={"type": "damage"},
            schedules_turn=False,
            breaks_movement=True,
        )
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [PlayerId(1)]
        movement_service = MagicMock()
        handler = ObservationEventHandler(
            resolver=mock_resolver,
            formatter=mock_formatter,
            buffer=buffer,
            unit_of_work_factory=unit_of_work_factory,
            turn_trigger=turn_trigger,
            llm_player_resolver=llm_player_resolver_include_one,
            movement_service=movement_service,
        )
        handler.handle(object())

        assert len(buffer.get_observations(PlayerId(1))) == 1
        movement_service.cancel_movement.assert_called_once()
        call_args = movement_service.cancel_movement.call_args[0][0]
        assert call_args.player_id == 1
        turn_trigger.schedule_turn.assert_not_called()

    def test_handle_when_schedules_turn_only_does_not_cancel(
        self,
        resolver,
        buffer,
        unit_of_work_factory,
        turn_trigger,
        llm_player_resolver_include_one,
    ):
        """schedules_turn のみの観測では schedule_turn が呼ばれ cancel_movement は呼ばれない"""
        from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
        mock_formatter = MagicMock()
        mock_formatter.format.return_value = ObservationOutput(
            prose="天気が変わった",
            structured={"type": "weather"},
            schedules_turn=True,
            breaks_movement=False,
        )
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [PlayerId(1)]
        movement_service = MagicMock()
        handler = ObservationEventHandler(
            resolver=mock_resolver,
            formatter=mock_formatter,
            buffer=buffer,
            unit_of_work_factory=unit_of_work_factory,
            turn_trigger=turn_trigger,
            llm_player_resolver=llm_player_resolver_include_one,
            movement_service=movement_service,
        )
        handler.handle(object())

        assert len(buffer.get_observations(PlayerId(1))) == 1
        turn_trigger.schedule_turn.assert_called_once_with(PlayerId(1))
        movement_service.cancel_movement.assert_not_called()

    def test_handle_when_not_llm_player_does_not_schedule_turn(
        self,
        resolver,
        formatter,
        buffer,
        unit_of_work_factory,
        turn_trigger,
        llm_player_resolver_include_two_only,
    ):
        """割り込み観測でも LLM プレイヤーでなければ schedule_turn は呼ばれない"""
        handler = ObservationEventHandler(
            resolver=resolver,
            formatter=formatter,
            buffer=buffer,
            unit_of_work_factory=unit_of_work_factory,
            turn_trigger=turn_trigger,
            llm_player_resolver=llm_player_resolver_include_two_only,
        )
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
        )
        handler.handle(event)

        assert len(buffer.get_observations(PlayerId(1))) == 1
        turn_trigger.schedule_turn.assert_not_called()

    def test_handle_when_turn_trigger_none_does_not_schedule(self, resolver, formatter, buffer, unit_of_work_factory, llm_player_resolver_include_one):
        """turn_trigger が None のとき schedule_turn は呼ばれない（通常の観測のみ）"""
        handler = ObservationEventHandler(
            resolver=resolver,
            formatter=formatter,
            buffer=buffer,
            unit_of_work_factory=unit_of_work_factory,
            turn_trigger=None,
            llm_player_resolver=llm_player_resolver_include_one,
        )
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        handler.handle(event)

        assert len(buffer.get_observations(PlayerId(1))) == 1

    def test_handle_when_llm_player_resolver_none_does_not_schedule(self, resolver, formatter, buffer, unit_of_work_factory, turn_trigger):
        """llm_player_resolver が None のとき schedule_turn は呼ばれない"""
        handler = ObservationEventHandler(
            resolver=resolver,
            formatter=formatter,
            buffer=buffer,
            unit_of_work_factory=unit_of_work_factory,
            turn_trigger=turn_trigger,
            llm_player_resolver=None,
        )
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        handler.handle(event)

        assert len(buffer.get_observations(PlayerId(1))) == 1
        turn_trigger.schedule_turn.assert_not_called()

    def test_handle_when_non_interrupting_event_does_not_schedule_turn(
        self,
        resolver,
        formatter,
        buffer,
        unit_of_work_factory,
        turn_trigger,
        llm_player_resolver_include_one,
    ):
        """LLM プレイヤーでも schedules_turn/breaks_movement=False の観測では schedule_turn しない"""
        handler = ObservationEventHandler(
            resolver=resolver,
            formatter=formatter,
            buffer=buffer,
            unit_of_work_factory=unit_of_work_factory,
            turn_trigger=turn_trigger,
            llm_player_resolver=llm_player_resolver_include_one,
        )
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )
        handler.handle(event)

        assert len(buffer.get_observations(PlayerId(1))) == 1
        turn_trigger.schedule_turn.assert_not_called()

    def test_handle_when_schedule_turn_raises_propagates_as_system_error_exception(
        self,
        resolver,
        formatter,
        buffer,
        unit_of_work_factory,
        llm_player_resolver_include_one,
    ):
        """割り込み観測で schedule_turn が例外を投げた場合、SystemErrorException でラップされて伝播する"""
        turn_trigger = MagicMock()
        turn_trigger.schedule_turn.side_effect = RuntimeError("schedule_turn failed")
        handler = ObservationEventHandler(
            resolver=resolver,
            formatter=formatter,
            buffer=buffer,
            unit_of_work_factory=unit_of_work_factory,
            turn_trigger=turn_trigger,
            llm_player_resolver=llm_player_resolver_include_one,
        )
        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
        )

        with pytest.raises(SystemErrorException, match="Observation.*failed"):
            handler.handle(event)

        assert len(buffer.get_observations(PlayerId(1))) == 1
        turn_trigger.schedule_turn.assert_called_once_with(PlayerId(1))


class TestObservationEventHandlerRegistry:
    """ObservationEventHandlerRegistry で非同期ハンドラが全観測対象イベント型に登録されること"""

    def test_register_handlers_registers_async_for_all_observed_event_types(self):
        from ai_rpg_world.infrastructure.events.observation_event_handler_registry import (
            ObservationEventHandlerRegistry,
        )
        from ai_rpg_world.domain.combat.event.combat_events import HitBoxCreatedEvent
        from ai_rpg_world.domain.skill.event.skill_events import SkillCooldownStartedEvent
        from ai_rpg_world.domain.player.event.status_events import PlayerLocationChangedEvent

        handler = MagicMock()
        registry = ObservationEventHandlerRegistry(observation_handler=handler)
        event_publisher = MagicMock()

        registry.register_handlers(event_publisher)

        calls = event_publisher.register_handler.call_args_list
        assert len(calls) >= 10
        event_types_registered = {c[0][0] for c in calls}
        assert PlayerLocationChangedEvent in event_types_registered
        assert HitBoxCreatedEvent not in event_types_registered
        assert SkillCooldownStartedEvent not in event_types_registered
        for call in calls:
            assert call[1]["is_synchronous"] is False
            assert call[0][1] is handler

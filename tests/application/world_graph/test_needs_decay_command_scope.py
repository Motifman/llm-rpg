"""needs decayの状態とeventが確定境界に追随することを保証する。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.world_graph.spot_graph_needs_decay_stage_service import (
    SpotGraphNeedsDecayStageService,
)
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_tick_command_repository_provider import (
    InMemoryPlayerStatusTickCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionFactory,
)


def _make_status(*, player_id: int, hunger: int, hp: int = 100) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    status = PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1, 1, 1, 1, 1, 0, 0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=hp, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
    )
    status.increase_need(NeedType.HUNGER, hunger)
    return status


def _build_stage(
    store: InMemoryDataStore,
    *,
    observed_hp: list[int],
) -> tuple[SpotGraphNeedsDecayStageService, InMemoryPlayerStatusRepository]:
    repository = InMemoryPlayerStatusRepository(store)
    dispatcher = CommandEventDispatcher(failure_observer=lambda *args: None)

    def observe_after_commit(event: BaseDomainEvent) -> None:
        if isinstance(event, PlayerDownedEvent):
            status = repository.find_by_id(PlayerId(1))
            assert status is not None
            observed_hp.append(status.hp.value)

    dispatcher.register_after_commit(
        BaseDomainEvent,
        observe_after_commit,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    scope_factory = CommandScopeFactory(
        InMemoryUnitOfWorkTransactionFactory(store),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=(InMemoryPlayerStatusTickCommandRepositoryProviderFactory()),
    )
    stage = SpotGraphNeedsDecayStageService(
        rates={NeedType.HUNGER: 1, NeedType.FATIGUE: 1},
        starvation_damage_per_tick=1,
        command_scope_factory=scope_factory,
    )
    return stage, repository


class TestNeedsDecayCommandScope:
    """needs decayの全player更新と確定後副作用を一括で検証する。"""

    def test_missing_scope_rejects_without_legacy_dependencies(self) -> None:
        """旧repository・publisherを保持せず、scope未配線なら実行を拒否する。"""
        stage = SpotGraphNeedsDecayStageService()

        assert not hasattr(stage, "_player_status_repository")
        assert not hasattr(stage, "_event_publisher")

        with pytest.raises(RuntimeError, match="CommandScopeFactory"):
            stage.run(WorldTick(1))

    def test_success_observers_read_committed_status(self) -> None:
        """致死飢餓eventはstatus確定後にだけ届く。"""
        store = InMemoryDataStore()
        observed_hp: list[int] = []
        stage, repository = _build_stage(store, observed_hp=observed_hp)
        repository.save(_make_status(player_id=1, hunger=99, hp=1))

        stage.run(WorldTick(1))

        status = repository.find_by_id(PlayerId(1))
        assert status is not None
        assert status.hp.value == 0
        assert status.needs.get(NeedType.HUNGER).value == 100  # type: ignore[union-attr]
        assert observed_hp == [0]

    def test_save_failure_rolls_back_all_players_and_suppresses_side_effects(
        self,
    ) -> None:
        """一括保存失敗では全員のneeds・HPを戻しeventを出さない。"""
        store = InMemoryDataStore()
        observed_hp: list[int] = []
        stage, repository = _build_stage(store, observed_hp=observed_hp)
        repository.save(_make_status(player_id=1, hunger=99, hp=1))
        repository.save(_make_status(player_id=2, hunger=10, hp=100))
        original_save_all = InMemoryPlayerStatusRepository.save_all

        def fail_after_staging(self, statuses):
            original_save_all(self, statuses)
            raise RuntimeError("needs save failed")

        with (
            patch.object(
                InMemoryPlayerStatusRepository,
                "save_all",
                fail_after_staging,
            ),
            pytest.raises(RuntimeError, match="needs save failed"),
        ):
            stage.run(WorldTick(1))

        first = repository.find_by_id(PlayerId(1))
        second = repository.find_by_id(PlayerId(2))
        assert first is not None and second is not None
        assert first.hp.value == 1
        assert first.needs.get(NeedType.HUNGER).value == 99  # type: ignore[union-attr]
        assert second.needs.get(NeedType.HUNGER).value == 10  # type: ignore[union-attr]
        assert observed_hp == []

    def test_cleanup_failure_after_commit_keeps_status_and_reaches_caller(self) -> None:
        """commit後の資源解放が失敗しても進めたneedsは確定したまま残り、CommandPostCommitExceptionが呼出し側へ届く。"""
        store = InMemoryDataStore()
        stage, repository = _build_stage(store, observed_hp=[])
        repository.save(_make_status(player_id=1, hunger=99))
        original_release = store.release_uow_transaction

        def release_then_fail() -> None:
            original_release()
            raise RuntimeError("transaction release failed")

        store.release_uow_transaction = release_then_fail  # type: ignore[method-assign]

        with pytest.raises(CommandPostCommitException):
            stage.run(WorldTick(1))

        status = repository.find_by_id(PlayerId(1))
        assert status is not None
        assert status.needs.get(NeedType.HUNGER).value == 100  # type: ignore[union-attr]

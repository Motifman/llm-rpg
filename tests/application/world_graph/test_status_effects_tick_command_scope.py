"""状態異常tick stageの状態更新と成功eventが同じ確定境界に属することを保証する。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.world_graph.status_effects_tick_stage_service import (
    StatusEffectsTickStageService,
)
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
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


def _make_status(hp: int = 100) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1, 1, 1, 1, 1, 0, 0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=hp, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
    )


def _build_stage(
    *,
    store: InMemoryDataStore,
    observed_hp: list[int],
) -> tuple[StatusEffectsTickStageService, InMemoryPlayerStatusRepository, MagicMock]:
    repository = InMemoryPlayerStatusRepository(store)
    dispatcher = CommandEventDispatcher()

    def observe_after_commit(event: BaseDomainEvent) -> None:
        if isinstance(event, PlayerDownedEvent):
            persisted = repository.find_by_id(PlayerId(1))
            assert persisted is not None
            observed_hp.append(persisted.hp.value)

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
        repository_provider_factory=(
            InMemoryPlayerStatusTickCommandRepositoryProviderFactory()
        ),
    )
    legacy_publisher = MagicMock()
    stage = StatusEffectsTickStageService(
        repository,
        event_publisher=legacy_publisher,
        command_scope_factory=scope_factory,
    )
    return stage, repository, legacy_publisher


class TestStatusEffectsTickCommandScope:
    """状態異常stageが保存とPlayerDownedEventを一括確定することを保証する。"""

    def test_success_event_observes_committed_player_status(self) -> None:
        """致死ダメージの観測はHP0の保存が確定した後にだけ届く。"""
        store = InMemoryDataStore()
        observed_hp: list[int] = []
        stage, repository, legacy_publisher = _build_stage(
            store=store,
            observed_hp=observed_hp,
        )
        status = _make_status(hp=1)
        status.add_status_effect(
            StatusEffect(
                effect_type=StatusEffectType.BLEEDING,
                value=1.0,
                expiry_tick=WorldTick(10),
            )
        )
        repository.save(status)

        stage.run(WorldTick(1))

        persisted = repository.find_by_id(PlayerId(1))
        assert persisted is not None
        assert persisted.hp.value == 0
        assert observed_hp == [0]
        legacy_publisher.publish_all.assert_not_called()

    def test_save_failure_rolls_back_state_and_suppresses_success_event(self) -> None:
        """全員保存が失敗するとHPと状態異常を戻し、成功eventを配送しない。"""
        store = InMemoryDataStore()
        observed_hp: list[int] = []
        stage, repository, legacy_publisher = _build_stage(
            store=store,
            observed_hp=observed_hp,
        )
        status = _make_status(hp=1)
        status.add_status_effect(
            StatusEffect(
                effect_type=StatusEffectType.BLEEDING,
                value=1.0,
                expiry_tick=WorldTick(10),
            )
        )
        repository.save(status)
        original_save_all = InMemoryPlayerStatusRepository.save_all

        def fail_after_staging(self, statuses):
            original_save_all(self, statuses)
            raise RuntimeError("status save failed")

        with patch.object(
            InMemoryPlayerStatusRepository,
            "save_all",
            fail_after_staging,
        ), pytest.raises(RuntimeError, match="status save failed"):
            stage.run(WorldTick(1))

        persisted = repository.find_by_id(PlayerId(1))
        assert persisted is not None
        assert persisted.hp.value == 1
        assert len(persisted.active_effects) == 1
        assert observed_hp == []
        legacy_publisher.publish_all.assert_not_called()

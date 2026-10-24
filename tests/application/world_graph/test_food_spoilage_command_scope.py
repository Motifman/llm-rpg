"""食料劣化stageの確定境界契約。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.world_graph.food_spoilage_stage_service import (
    FoodSpoilageStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.event.item_event import ItemSpoiledEvent
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.value_object.spoilage import (
    STATE_KEY_ACQUIRED_AT_TICK,
    STATE_KEY_SPOILED,
)
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_food_spoilage_command_repository_provider import (
    InMemoryFoodSpoilageCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionFactory,
)

SPEC_ID = ItemSpecId.create(101)


def test_missing_scope_rejects_before_legacy_repository_access() -> None:
    """旧repository・callbackを保持せず、腐敗対象があれば未配線を拒否する。"""
    stage = FoodSpoilageStageService(
        spoilable_specs={SPEC_ID: 4},
    )

    assert not hasattr(stage, "_item_repository")
    assert not hasattr(stage, "_spoiled_callback")
    assert not hasattr(stage, "_spoiled_batch_callback")

    with pytest.raises(RuntimeError, match="CommandScopeFactory"):
        stage.run(WorldTick(4))


def _spec() -> ItemSpec:
    return ItemSpec(
        item_spec_id=SPEC_ID,
        name="生の魚",
        item_type=ItemType.QUEST,
        rarity=Rarity.COMMON,
        description="生の魚",
        max_stack_size=MaxStackSize(1),
        spoils_after_ticks=4,
    )


def _scope_factory(
    store: InMemoryDataStore,
    handlers: Sequence[Callable[[ItemSpoiledEvent], None]],
) -> CommandScopeFactory:
    dispatcher = CommandEventDispatcher(failure_observer=lambda *args: None)
    for handler in handlers:
        dispatcher.register_after_commit(
            ItemSpoiledEvent,
            handler,
            channel=DeliveryChannel.OBSERVATION,
            guarantee=DeliveryGuarantee.BEST_EFFORT,
        )
    return CommandScopeFactory(
        InMemoryUnitOfWorkTransactionFactory(store),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=(
            InMemoryFoodSpoilageCommandRepositoryProviderFactory()
        ),
    )


def _stage_with_two_items(
    *,
    handlers: Sequence[Callable[[ItemSpoiledEvent], None]] = (),
) -> tuple[InMemoryDataStore, InMemoryItemRepository, FoodSpoilageStageService]:
    store = InMemoryDataStore()
    repository = InMemoryItemRepository(store)
    for value in (7001, 7002):
        item = ItemAggregate.create(
            item_instance_id=ItemInstanceId(value),
            item_spec=_spec(),
            quantity=1,
        )
        item.merge_state({STATE_KEY_ACQUIRED_AT_TICK: 0})
        repository.save(item)
    stage = FoodSpoilageStageService(
        spoilable_specs={SPEC_ID: 4},
        command_scope_factory=_scope_factory(store, handlers),
    )
    return store, repository, stage


def test_events_observe_all_items_after_commit() -> None:
    """ItemSpoiledEventは、対象itemがすべて確定した後にだけ届く。"""
    observations: list[tuple[int, tuple[bool, bool]]] = []
    repository: InMemoryItemRepository

    def states() -> tuple[bool, bool]:
        return tuple(
            bool(repository.find_by_id(ItemInstanceId(value)).state[STATE_KEY_SPOILED])
            for value in (7001, 7002)
        )

    _store, repository, stage = _stage_with_two_items(
        handlers=(
            lambda event: observations.append(
                (event.item_instance_id.value, states())
            ),
        ),
    )

    stage.run(WorldTick(4))

    assert observations == [
        (7001, (True, True)),
        (7002, (True, True)),
    ]


def test_second_save_failure_rolls_back_all_items_and_skips_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """途中保存失敗は全itemを開始前へ戻し、腐敗eventを一件も配送しない。"""
    observed: list[int] = []
    _store, repository, stage = _stage_with_two_items(
        handlers=(lambda event: observed.append(event.item_instance_id.value),),
    )
    original_save = InMemoryItemRepository.save
    save_count = 0

    def fail_after_second_save(self, aggregate):
        nonlocal save_count
        result = original_save(self, aggregate)
        save_count += 1
        if save_count == 2:
            raise RuntimeError("second item save failed")
        return result

    monkeypatch.setattr(InMemoryItemRepository, "save", fail_after_second_save)

    with pytest.raises(RuntimeError, match="second item save failed"):
        stage.run(WorldTick(4))

    assert observed == []
    for value in (7001, 7002):
        state = repository.find_by_id(ItemInstanceId(value)).state
        assert state.get(STATE_KEY_SPOILED) is not True
        assert state[STATE_KEY_ACQUIRED_AT_TICK] == 0


def test_event_observer_failure_keeps_commit_and_continues_delivery(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """確定後observer失敗はitemを戻さず、後続observerも継続する。"""
    observed: list[int] = []
    _store, repository, stage = _stage_with_two_items(
        handlers=(
            lambda _event: (_ for _ in ()).throw(
                RuntimeError("food observation failed")
            ),
            lambda event: observed.append(event.item_instance_id.value),
        ),
    )

    with caplog.at_level(logging.WARNING):
        stage.run(WorldTick(4))

    assert observed == [7001, 7002]
    assert "Best-effort after-commit handler failed" in caplog.text
    assert all(
        repository.find_by_id(ItemInstanceId(value)).state[STATE_KEY_SPOILED]
        for value in (7001, 7002)
    )


def test_post_commit_cleanup_failure_still_notifies_committed_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit済みcleanup失敗でも腐敗を通知し、確定後例外を維持する。"""
    observed: list[int] = []
    store, repository, stage = _stage_with_two_items(
        handlers=(lambda event: observed.append(event.item_instance_id.value),),
    )
    original_release = store.release_uow_transaction

    def fail_after_release() -> None:
        original_release()
        raise RuntimeError("food spoilage cleanup failed")

    monkeypatch.setattr(store, "release_uow_transaction", fail_after_release)

    with pytest.raises(CommandPostCommitException):
        stage.run(WorldTick(4))

    assert observed == [7001, 7002]
    assert all(
        repository.find_by_id(ItemInstanceId(value)).state[STATE_KEY_SPOILED]
        for value in (7001, 7002)
    )

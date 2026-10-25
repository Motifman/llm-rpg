"""休眠中の戦闘とモンスターのイベント対応・順序・失敗時の取り消しを守る。"""

from types import SimpleNamespace

import pytest

from ai_rpg_world.application.common.command_scope import CommandScope
from ai_rpg_world.domain.combat.event.combat_events import HitBoxHitRecordedEvent
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.event.monster_events import (
    MonsterDecidedToInteractEvent,
    MonsterDecidedToMoveEvent,
    MonsterDecidedToUseSkillEvent,
    MonsterDiedEvent,
    MonsterFedEvent,
    MonsterRespawnedEvent,
    MonsterSpawnedEvent,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.eventing import DeliveryChannel, DeliveryGuarantee
from ai_rpg_world.infrastructure.events.combat_event_handler_registry import CombatEventHandlerRegistry
from ai_rpg_world.infrastructure.events.command_event_dispatcher import CommandEventDispatcher
from ai_rpg_world.infrastructure.events.monster_event_handler_registry import MonsterEventHandlerRegistry
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork

_COMBAT = [
    (HitBoxHitRecordedEvent, 0), (HitBoxHitRecordedEvent, 1),
    (MonsterDiedEvent, 2), (MonsterDiedEvent, 3), (MonsterDiedEvent, 4),
    (MonsterSpawnedEvent, 5), (MonsterRespawnedEvent, 5),
]
_MONSTER = [
    (MonsterDecidedToMoveEvent, 0), (MonsterDecidedToUseSkillEvent, 1),
    (MonsterDecidedToInteractEvent, 2), (MonsterFedEvent, 3),
]
_CASES = [("combat", event, index) for event, index in _COMBAT] + [("monster", event, index) for event, index in _MONSTER]


def _registry(kind, callback):
    count, registry = (6, CombatEventHandlerRegistry) if kind == "combat" else (4, MonsterEventHandlerRegistry)
    return registry(*(SimpleNamespace(handle=lambda event, index=index: callback(index, event)) for index in range(count)))


def _event(event_type):
    common = dict(aggregate_id=MonsterId(1), aggregate_type="MonsterAggregate")
    if event_type is HitBoxHitRecordedEvent:
        return event_type.create(aggregate_id=HitBoxId(1), aggregate_type="HitBoxAggregate", owner_id=WorldObjectId(1), target_id=WorldObjectId(2), hit_coordinate=Coordinate(0, 0, 0))
    if event_type is MonsterDiedEvent:
        return event_type.create(**common, respawn_tick=10, exp=1, gold=1)
    if event_type in (MonsterSpawnedEvent, MonsterRespawnedEvent):
        return event_type.create(**common, coordinate={"x": 0, "y": 0, "z": 0}, spot_id=SpotId(1))
    if event_type is MonsterFedEvent:
        return event_type.create(aggregate_id=WorldObjectId(1), aggregate_type="WorldObject", actor_id=WorldObjectId(1), target_id=WorldObjectId(2), target_coordinate=Coordinate(0, 0, 0))
    common.update(actor_id=WorldObjectId(1), spot_id=SpotId(1), current_tick=WorldTick(0))
    if event_type is MonsterDecidedToMoveEvent:
        return event_type.create(**common, coordinate={"x": 1, "y": 0, "z": 0})
    if event_type is MonsterDecidedToUseSkillEvent:
        return event_type.create(**common, skill_slot_index=0, target_id=None)
    return event_type.create(**common, target_id=WorldObjectId(2))


def _command_scope(kind, callback, store):
    transaction = InMemoryUnitOfWork(data_store=store)
    dispatcher = CommandEventDispatcher(failure_observer=lambda *args: pytest.fail("確定前の失敗を握りつぶさない"))

    def receive(index, event):
        assert transaction.is_in_transaction()
        callback(index, event)

    _registry(kind, receive).register_command_handlers(dispatcher)
    return CommandScope(InMemoryUnitOfWorkTransactionAdapter(transaction), sync_dispatcher=dispatcher, after_commit_handoff=dispatcher), dispatcher


@pytest.mark.parametrize("kind,event_type,index", _CASES)
def test_registered_event_reaches_its_original_receiver(kind, event_type, index) -> None:
    """既存の11通りの登録は、同じイベントで同じ受け手のhandleを確定前に呼ぶ。"""
    received = []
    scope, _ = _command_scope(kind, lambda index, event: received.append((index, event)), InMemoryDataStore())
    event = _event(event_type)
    with scope as context:
        context.collect(event)
    assert (index, event) in received


@pytest.mark.parametrize("kind,event_type,expected", [
    ("combat", HitBoxHitRecordedEvent, [0, 1]), ("combat", MonsterDiedEvent, [2, 3, 4]),
    ("combat", MonsterSpawnedEvent, [5]), ("combat", MonsterRespawnedEvent, [5]),
    ("monster", MonsterDecidedToMoveEvent, [0]), ("monster", MonsterDecidedToUseSkillEvent, [1]),
    ("monster", MonsterDecidedToInteractEvent, [2]), ("monster", MonsterFedEvent, [3]),
])
def test_receivers_run_in_original_order_before_commit(kind, event_type, expected) -> None:
    """対象のイベントを集めて確定すると、従来の受け手だけを登録順に呼ぶ。"""
    calls = []
    store = InMemoryDataStore()
    scope, _ = _command_scope(kind, lambda index, event: calls.append(index), store)
    with scope as context:
        context.collect(_event(event_type))
        assert calls == []
    assert calls == expected


@pytest.mark.parametrize("kind,event_type,index", _CASES)
def test_required_failure_rolls_back_and_skips_after_commit(kind, event_type, index) -> None:
    """11通りの各受け手が失敗すると保存状態を戻し、後続と確定後の受け手を呼ばない。"""
    store = InMemoryDataStore()
    original = store.next_world_object_id
    calls = []

    def fail(receiver, event):
        calls.append(receiver)
        if receiver == index:
            raise RuntimeError("受け手が失敗")

    scope, dispatcher = _command_scope(kind, fail, store)
    dispatcher.register_after_commit(
        event_type, lambda event: calls.append("after"),
        channel=DeliveryChannel.AUXILIARY, guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    with pytest.raises(RuntimeError, match="受け手が失敗"):
        with scope as context:
            store.next_world_object_id = 99
            context.collect(_event(event_type))
    assert store.next_world_object_id == original
    assert calls[-1] == index
    assert "after" not in calls

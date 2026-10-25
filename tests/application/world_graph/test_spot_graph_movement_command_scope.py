"""SpotGraph移動の開始・進行・中断が一つの確定境界に従うことを保証する。"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import Mock

import pytest
from tests.domain.player.aggregate.test_player_status_aggregate import (
    create_test_status_aggregate,
)

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.player.services.departed_position_store import (
    DepartedPositionStore,
)
from ai_rpg_world.application.world_graph.spot_graph_movement_application_service import (
    SpotGraphMovementApplicationService,
    SpotTravelBlockedReason,
)
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.passage_condition_type import (
    PassageConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    EntityEnteredSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage_condition import (
    PassageCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_movement_command_repository_provider import (
    InMemoryMovementCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.interaction_rollback_participants import (
    build_movement_rollback_participants,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    RollbackParticipantTransactionFactory,
)

_PLAYER_ID = PlayerId(1)
_FIRST = SpotId.create(1)
_SECOND = SpotId.create(2)
_THIRD = SpotId.create(3)


def _graph(*, required_flag: str | None = None) -> SpotGraphAggregate:
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    for spot_id in (_FIRST, _SECOND, _THIRD):
        graph.add_spot(
            SpotNode(
                spot_id=spot_id,
                name=f"S{int(spot_id)}",
                description="command scope試験用",
                category=SpotCategoryEnum.OTHER,
                parent_id=None,
            )
        )
    for connection_id, origin, destination in (
        (ConnectionId.create(1), _FIRST, _SECOND),
        (ConnectionId.create(2), _SECOND, _THIRD),
    ):
        graph.add_connection(
            SpotConnection(
                connection_id=connection_id,
                from_spot_id=origin,
                to_spot_id=destination,
                name=f"{int(origin)}-{int(destination)}",
                description="",
                travel_ticks=0,
                is_bidirectional=False,
                passage_conditions=(
                    [
                        PassageCondition(
                            condition_type=PassageConditionTypeEnum.FLAG_SET,
                            flag_name=required_flag,
                        )
                    ]
                    if required_flag is not None
                    else []
                ),
            )
        )
    graph.place_entity(EntityId.create(1), _FIRST)
    graph.clear_events()
    return graph


@dataclass
class _PerceptionPolicy:
    departed: bool = False

    def is_departed(self, player_id: PlayerId) -> bool:
        assert player_id == _PLAYER_ID
        return self.departed


def _service(*, departed: bool = False, required_flag: str | None = None):
    data_store = InMemoryDataStore()
    status_repository = InMemoryPlayerStatusRepository(data_store)
    status_repository.save(create_test_status_aggregate(player_id=1))
    graph_repository = InMemorySpotGraphRepository(_graph(required_flag=required_flag))
    departed_positions = DepartedPositionStore()
    if departed:
        departed_positions.place(_PLAYER_ID, _FIRST)
    dispatcher = CommandEventDispatcher(failure_observer=lambda *args: None)
    factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_movement_rollback_participants(
                departed_positions=departed_positions,
                spot_graph=graph_repository,
            ),
        ),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=(
            InMemoryMovementCommandRepositoryProviderFactory(
                spot_graph=graph_repository,
            )
        ),
    )
    service = SpotGraphMovementApplicationService(
        graph_repository,
        status_repository,
        departed_position_store=departed_positions,
        player_perception_policy=_PerceptionPolicy(departed=departed),
        command_scope_factory=factory,
    )
    return service, status_repository, graph_repository, departed_positions, dispatcher


def _start(service: SpotGraphMovementApplicationService) -> None:
    service.start_travel_to_spot(
        _PLAYER_ID,
        _THIRD,
        frozenset(),
        frozenset(),
    )


def test_public_mutations_reject_missing_command_scope_before_repository_access() -> None:
    """確定区間が未配線なら5つの公開更新入口はrepositoryへ触れず拒否する。"""
    graph_repository = Mock()
    status_repository = Mock()
    graph_repository.find_graph.side_effect = AssertionError("未配線時にgraphを読んではならない")
    status_repository.find_by_id.side_effect = AssertionError("未配線時にstatusを読んではならない")
    status_repository.save.side_effect = AssertionError("未配線時にstatusを保存してはならない")
    service = SpotGraphMovementApplicationService(
        graph_repository,
        status_repository,
    )
    calls = (
        lambda: service.move_to_sub_location(_PLAYER_ID, None),
        lambda: service.start_travel_to_spot(
            _PLAYER_ID,
            _SECOND,
            frozenset(),
            frozenset(),
        ),
        lambda: service.advance_spot_travel_one_tick(
            _PLAYER_ID,
            frozenset(),
            frozenset(),
        ),
        lambda: service.cancel_spot_travel(_PLAYER_ID),
        lambda: service.restore_spot_travel_state(
            _PLAYER_ID,
            PlayerSpotNavigationState.at_rest(_FIRST),
        ),
    )

    for call in calls:
        with pytest.raises(RuntimeError, match="CommandScopeFactoryが未配線"):
            call()

    graph_repository.find_graph.assert_not_called()
    status_repository.find_by_id.assert_not_called()
    status_repository.save.assert_not_called()


def test_sub_location_save_failure_preserves_the_previous_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """sub-location保存が失敗すると変更前の位置へ戻す。"""
    service, statuses, _, _, _ = _service()
    original_save = InMemoryPlayerStatusRepository.save

    def save_then_fail(self, status) -> None:
        original_save(self, status)
        raise RuntimeError("sub-location save failed")

    monkeypatch.setattr(InMemoryPlayerStatusRepository, "save", save_then_fail)

    with pytest.raises(RuntimeError, match="sub-location save failed"):
        service.move_to_sub_location(_PLAYER_ID, SubLocationId.create(7))

    restored = statuses.find_by_id(_PLAYER_ID)
    assert restored is not None
    assert restored.spot_navigation_state is None


def test_start_save_failure_preserves_the_resting_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """移動開始のstatus保存が失敗すると経路予約を残さない。"""
    service, statuses, _, _, _ = _service()
    before_nav = statuses.find_by_id(_PLAYER_ID).spot_navigation_state
    original_save = InMemoryPlayerStatusRepository.save

    def save_then_fail(self, status) -> None:
        original_save(self, status)
        raise RuntimeError("start save failed")

    monkeypatch.setattr(InMemoryPlayerStatusRepository, "save", save_then_fail)

    with pytest.raises(RuntimeError, match="start save failed"):
        _start(service)

    assert statuses.find_by_id(_PLAYER_ID).spot_navigation_state == before_nav


def test_second_crossing_failure_rolls_back_first_crossing_and_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1 tickの2区間目が失敗すると1区間目の位置と新navigationも残さない。"""
    service, statuses, graphs, _, _ = _service()
    _start(service)
    before_nav = statuses.find_by_id(_PLAYER_ID).spot_navigation_state
    original_move = SpotGraphAggregate.move_entity
    calls = 0

    def fail_second(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second crossing failed")
        return original_move(self, *args, **kwargs)

    monkeypatch.setattr(SpotGraphAggregate, "move_entity", fail_second)

    with pytest.raises(RuntimeError, match="second crossing failed"):
        service.advance_spot_travel_one_tick(
            _PLAYER_ID,
            frozenset(),
            frozenset(),
        )

    assert graphs.find_graph().get_entity_spot(EntityId.create(1)) == _FIRST
    assert statuses.find_by_id(_PLAYER_ID).spot_navigation_state == before_nav
    assert graphs.find_graph().get_events() == []


def test_crossing_events_observe_the_fully_committed_tick() -> None:
    """2区間の移動観測が届く時点で位置とnavigationは最終到着済みである。"""
    service, statuses, graphs, _, dispatcher = _service()
    _start(service)
    observations: list[tuple[str, SpotId, bool]] = []
    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda event: observations.append(
            (
                type(event).__name__,
                graphs.find_graph().get_entity_spot(EntityId.create(1)),
                statuses.find_by_id(_PLAYER_ID).spot_navigation_state.is_traveling,
            )
        ),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )

    result = service.advance_spot_travel_one_tick(
        _PLAYER_ID,
        frozenset(),
        frozenset(),
    )

    assert result is not None
    assert result.entered_spot_ids == (_SECOND, _THIRD)
    assert [name for name, _, _ in observations] == [
        "EntityLeftSpotEvent",
        "EntityEnteredSpotEvent",
        "EntityLeftSpotEvent",
        "EntityEnteredSpotEvent",
    ]
    assert all(spot_id == _THIRD for _, spot_id, _ in observations)
    assert all(not is_traveling for _, _, is_traveling in observations)
    assert graphs.find_graph().get_events() == []


def test_status_save_failure_rolls_back_graph_and_emits_no_crossing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """graph移動後のstatus保存が失敗しても位置と観測を開始前へ戻す。"""
    service, statuses, graphs, _, dispatcher = _service()
    _start(service)
    before_nav = statuses.find_by_id(_PLAYER_ID).spot_navigation_state
    delivered: list[BaseDomainEvent] = []
    dispatcher.register_after_commit(
        BaseDomainEvent,
        delivered.append,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    original_save = InMemoryPlayerStatusRepository.save

    def save_then_fail(self, status) -> None:
        original_save(self, status)
        raise RuntimeError("status save failed")

    monkeypatch.setattr(InMemoryPlayerStatusRepository, "save", save_then_fail)

    with pytest.raises(RuntimeError, match="status save failed"):
        service.advance_spot_travel_one_tick(
            _PLAYER_ID,
            frozenset(),
            frozenset(),
        )

    assert graphs.find_graph().get_entity_spot(EntityId.create(1)) == _FIRST
    assert statuses.find_by_id(_PLAYER_ID).spot_navigation_state == before_nav
    assert delivered == []


def test_required_event_failure_rolls_back_all_crossings() -> None:
    """commit前必須の到着処理が失敗すると複数区間とnavigationを戻す。"""
    service, statuses, graphs, _, dispatcher = _service()
    _start(service)
    before_nav = statuses.find_by_id(_PLAYER_ID).spot_navigation_state
    dispatcher.register_required_before_commit(
        EntityEnteredSpotEvent,
        lambda event, context: (_ for _ in ()).throw(RuntimeError("arrival processing failed")),
    )

    with pytest.raises(RuntimeError, match="arrival processing failed"):
        service.advance_spot_travel_one_tick(
            _PLAYER_ID,
            frozenset(),
            frozenset(),
        )

    assert graphs.find_graph().get_entity_spot(EntityId.create(1)) == _FIRST
    assert statuses.find_by_id(_PLAYER_ID).spot_navigation_state == before_nav


def test_departed_multi_crossing_failure_restores_position_and_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """退場者の2区間目が失敗すると別位置storeとnavigationを両方戻す。"""
    service, statuses, _, departed_positions, _ = _service(departed=True)
    _start(service)
    before_nav = statuses.find_by_id(_PLAYER_ID).spot_navigation_state
    original_move = departed_positions.move
    calls = 0

    def fail_second(player_id: PlayerId, spot_id: SpotId) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("departed second crossing failed")
        original_move(player_id, spot_id)

    monkeypatch.setattr(departed_positions, "move", fail_second)

    with pytest.raises(RuntimeError, match="departed second crossing failed"):
        service.advance_spot_travel_one_tick(
            _PLAYER_ID,
            frozenset(),
            frozenset(),
        )

    assert departed_positions.find(_PLAYER_ID) == _FIRST
    assert statuses.find_by_id(_PLAYER_ID).spot_navigation_state == before_nav


def test_departed_crossing_rechecks_passage_and_abandons_travel() -> None:
    """開始後に通行条件が失われた退場者は、例外にならず位置を進めずに移動を取りやめる (#1559)。"""
    service, statuses, _, departed_positions, _ = _service(
        departed=True,
        required_flag="door_open",
    )
    service.start_travel_to_spot(
        _PLAYER_ID,
        _THIRD,
        frozenset(),
        frozenset({"door_open"}),
    )

    result = service.advance_spot_travel_one_tick(
        _PLAYER_ID,
        frozenset(),
        frozenset(),
    )

    assert departed_positions.find(_PLAYER_ID) == _FIRST
    nav = statuses.find_by_id(_PLAYER_ID).spot_navigation_state
    assert not nav.is_traveling
    assert nav.current_spot_id == _FIRST
    assert result is not None
    assert result.blocked is not None
    assert result.blocked.reason is SpotTravelBlockedReason.PASSAGE_CONDITION
    assert result.blocked.condition_message == "条件を満たしていません"


def test_cancel_save_failure_preserves_the_travel_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """中断状態の保存が失敗すると元の移動予約を残す。"""
    service, statuses, _, _, _ = _service()
    _start(service)
    before_nav = statuses.find_by_id(_PLAYER_ID).spot_navigation_state
    original_save = InMemoryPlayerStatusRepository.save

    def save_then_fail(self, status) -> None:
        original_save(self, status)
        raise RuntimeError("cancel save failed")

    monkeypatch.setattr(InMemoryPlayerStatusRepository, "save", save_then_fail)

    with pytest.raises(RuntimeError, match="cancel save failed"):
        service.cancel_spot_travel(_PLAYER_ID)

    assert statuses.find_by_id(_PLAYER_ID).spot_navigation_state == before_nav

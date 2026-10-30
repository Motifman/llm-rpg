"""本番の tend_to_player が復活と観測を一つの確定境界で扱うことを保証する。"""

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.event.status_events import PlayerRevivedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
    GameEndConditionEvaluator,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)

_SCENARIO = Path("data/scenarios/survival_island_v4_coop.json")


def _executor(runtime) -> SpotGraphToolExecutor:
    services = SpotGraphWorldServices(
        interaction=runtime._interaction_service,
        exploration=runtime._exploration_service,
        world_flags=runtime._world_flag_state,
        game_end_evaluator=GameEndConditionEvaluator(),
        exploration_progress=runtime._exploration_progress,
        movement=runtime._movement_service,
    )
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=runtime._player_inventory_repo,
        item_repository=runtime._item_repo,
        event_publisher=runtime._speech_event_publisher,
        player_status_repository=runtime._player_status_repo,
        speech_service=runtime._speech_service,
        tend_to_player_command_scope_factory=(runtime._tend_to_player_command_scope_factory),
        runtime=runtime,
    )


def _down(runtime, player_id: PlayerId) -> None:
    """蘇生command試験の開始状態として整合したダウンepisodeを作る。"""
    status = runtime._player_status_repo.find_by_id(player_id)
    assert status is not None
    status.apply_damage(status.hp.value)
    events = tuple(status.get_events())
    status.clear_events()
    runtime._player_status_repo.save(status)
    runtime._speech_event_publisher.publish_all(events)
    spot_id = runtime._spot_graph_repo.find_graph().get_entity_spot(EntityId.create(int(player_id)))
    current_tick = int(runtime.current_tick())
    runtime._fallen_body_registry.record(
        player_id,
        spot_id,
        WorldTick(current_tick),
    )
    runtime._death_grace_timer.register(player_id, downed_at_tick=current_tick)


def _tend(executor: SpotGraphToolExecutor, actor: PlayerId, target: PlayerId):
    return executor._tend_to_player(
        int(actor),
        {
            "target_player_id": int(target),
            "target_display_name": "ノア",
            "inner_thought": "助ける",
        },
    )


def test_world_runtime_exposes_tend_to_player_command_scope_factory() -> None:
    """出荷runtimeは tend_to_player 用CommandScope factoryを保持する。"""
    runtime = create_world_runtime(_SCENARIO)

    assert runtime._tend_to_player_command_scope_factory is not None


def test_status_save_failure_rolls_back_revive_without_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """復活statusの保存が失敗すると、ダウン状態を戻して復活を観測させない。"""
    runtime = create_world_runtime(_SCENARIO)
    actor = PlayerId(1)
    target = PlayerId(2)
    _down(runtime, target)
    assert runtime._death_grace_timer.is_pending(target)
    assert runtime._fallen_body_registry.find(target) is not None
    delivered: list[PlayerRevivedEvent] = []
    original_publish_all = runtime._speech_event_publisher.publish_all

    def observe(events) -> None:
        delivered.extend(event for event in events if isinstance(event, PlayerRevivedEvent))
        original_publish_all(events)

    monkeypatch.setattr(runtime._speech_event_publisher, "publish_all", observe)
    original_save = InMemoryPlayerStatusRepository.save

    def fail_after_save(repository, aggregate) -> None:
        original_save(repository, aggregate)
        if aggregate.player_id == target and not aggregate.is_down:
            raise RuntimeError("revived status save failed")

    monkeypatch.setattr(InMemoryPlayerStatusRepository, "save", fail_after_save)

    result = _tend(_executor(runtime), actor, target)

    restored = runtime._player_status_repo.find_by_id(target)
    assert result.success is False
    assert restored is not None and restored.is_down is True
    assert runtime._death_grace_timer.is_pending(target)
    assert runtime._fallen_body_registry.find(target) is not None
    assert delivered == []


def test_grace_cancellation_failure_rolls_back_revive_without_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """猶予取消が失敗すると蘇生・身体・猶予・観測を開始前へ戻す。"""
    runtime = create_world_runtime(_SCENARIO)
    actor = PlayerId(1)
    target = PlayerId(2)
    _down(runtime, target)
    original_cancel = runtime._death_grace_timer.cancel

    def fail_after_cancel(player_id, **kwargs) -> None:
        original_cancel(player_id, **kwargs)
        raise RuntimeError("grace cancellation failed")

    monkeypatch.setattr(runtime._death_grace_timer, "cancel", fail_after_cancel)
    delivered: list[PlayerRevivedEvent] = []
    original_publish_all = runtime._speech_event_publisher.publish_all

    def observe(events) -> None:
        delivered.extend(event for event in events if isinstance(event, PlayerRevivedEvent))
        original_publish_all(events)

    monkeypatch.setattr(runtime._speech_event_publisher, "publish_all", observe)

    result = _tend(_executor(runtime), actor, target)

    restored = runtime._player_status_repo.find_by_id(target)
    assert result.success is False
    assert result.error_code == "SYSTEM_ERROR"
    assert restored is not None and restored.is_down is True
    assert runtime._death_grace_timer.is_pending(target)
    assert runtime._fallen_body_registry.find(target) is not None
    assert delivered == []


def test_body_removal_failure_rolls_back_revive_without_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """身体削除が失敗すると蘇生・身体・猶予・観測を開始前へ戻す。"""
    runtime = create_world_runtime(_SCENARIO)
    actor = PlayerId(1)
    target = PlayerId(2)
    _down(runtime, target)
    original_remove = runtime._fallen_body_registry.remove

    def fail_after_remove(player_id) -> None:
        original_remove(player_id)
        raise RuntimeError("body removal failed")

    monkeypatch.setattr(runtime._fallen_body_registry, "remove", fail_after_remove)
    delivered: list[PlayerRevivedEvent] = []
    original_publish_all = runtime._speech_event_publisher.publish_all

    def observe(events) -> None:
        delivered.extend(event for event in events if isinstance(event, PlayerRevivedEvent))
        original_publish_all(events)

    monkeypatch.setattr(runtime._speech_event_publisher, "publish_all", observe)

    result = _tend(_executor(runtime), actor, target)

    restored = runtime._player_status_repo.find_by_id(target)
    assert result.success is False
    assert result.error_code == "SYSTEM_ERROR"
    assert restored is not None and restored.is_down is True
    assert runtime._death_grace_timer.is_pending(target)
    assert runtime._fallen_body_registry.find(target) is not None
    assert delivered == []


def test_success_observes_the_committed_revived_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """復活eventはstatus確定後に一度だけ配送し、猶予と身体を後処理する。"""
    runtime = create_world_runtime(_SCENARIO)
    actor = PlayerId(1)
    target = PlayerId(2)
    _down(runtime, target)
    observed_is_down: list[bool] = []
    original_publish_all = runtime._speech_event_publisher.publish_all

    def observe(events) -> None:
        for event in events:
            if not isinstance(event, PlayerRevivedEvent):
                continue
            committed = runtime._player_status_repo.find_by_id(target)
            assert committed is not None
            observed_is_down.append(committed.is_down)
            assert runtime._death_grace_timer.is_pending(target) is False
            assert runtime._fallen_body_registry.find(target) is None
        original_publish_all(events)

    monkeypatch.setattr(runtime._speech_event_publisher, "publish_all", observe)

    result = _tend(_executor(runtime), actor, target)

    assert result.success is True
    assert observed_is_down == [False]
    assert runtime._death_grace_timer.is_pending(target) is False
    assert runtime._fallen_body_registry.find(target) is None

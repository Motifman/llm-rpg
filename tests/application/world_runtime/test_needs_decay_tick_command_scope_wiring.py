"""本番runtimeがneeds decayを独立した確定境界へ接続することを保証する。"""

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.player.value_object.agent_need import NeedType


def test_world_runtime_injects_shared_player_status_tick_scope() -> None:
    """needs decayと状態異常は同じprovider構成のscope factoryを共有する。"""
    runtime = create_world_runtime(Path("data/scenarios/survival_island_v2_short.json"))

    needs_stage = runtime._simulation_service._needs_decay_stage
    status_effects_stage = runtime._simulation_service._status_effects_stage
    assert needs_stage is not None
    assert status_effects_stage is not None
    assert needs_stage._command_scope_factory is not None
    assert needs_stage._command_scope_factory is status_effects_stage._command_scope_factory
    assert not hasattr(needs_stage, "_player_status_repository")
    assert not hasattr(needs_stage, "_event_publisher")


def test_lethal_needs_tick_rolls_back_player_lifecycle_when_grace_registration_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """猶予登録の途中失敗ではHP・身体・猶予・観測を開始前へ戻す。"""
    runtime = create_world_runtime(Path("data/scenarios/survival_island_v2_short.json"))
    player_id = runtime.get_player_ids()[0]
    status = runtime._player_status_repo.find_by_id(player_id)
    assert status is not None
    status.apply_damage(status.hp.value - 1)
    status.increase_need(NeedType.HUNGER, 100)
    runtime._player_status_repo.save(status)

    delivered: list[PlayerDownedEvent] = []
    original_publish_all = runtime._speech_event_publisher.publish_all

    def observe(events) -> None:
        delivered.extend(event for event in events if isinstance(event, PlayerDownedEvent))
        original_publish_all(events)

    monkeypatch.setattr(runtime._speech_event_publisher, "publish_all", observe)
    original_register = runtime._death_grace_timer.register

    def fail_after_register(target, downed_at_tick) -> None:
        original_register(target, downed_at_tick)
        raise RuntimeError("needs grace registration failed")

    monkeypatch.setattr(
        runtime._death_grace_timer,
        "register",
        fail_after_register,
    )
    needs_stage = runtime._simulation_service._needs_decay_stage
    assert needs_stage is not None

    with pytest.raises(Exception, match="needs grace registration failed"):
        needs_stage.run(WorldTick(1))

    restored = runtime._player_status_repo.find_by_id(player_id)
    assert restored is not None
    assert restored.hp.value == 1
    assert restored.is_down is False
    assert restored.needs.get(NeedType.HUNGER).value == 100  # type: ignore[union-attr]
    assert runtime._death_grace_timer.is_pending(player_id) is False
    assert runtime._fallen_body_registry.find(player_id) is None
    assert delivered == []

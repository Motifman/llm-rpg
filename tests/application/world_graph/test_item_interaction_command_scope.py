"""道具に宣言されたinteractionが一つのCommandScopeで確定することを保証する。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.world_graph.interaction_cooldown_store import (
    item_action_key,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.interaction_cooldown_scope import (
    InteractionCooldownScope,
)
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


_DRILL = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "station_drill.json"
)
_KUZE = PlayerId(3)
_ROOMS = (
    "observatory",
    "medbay",
    "greenhouse",
    "comms",
    "fuel_bay",
    "hall",
    "corridor",
    "storage",
    "machine_room",
)


@pytest.fixture()
def runtime():
    return create_world_runtime(_DRILL)


def _terminal_spec(runtime) -> ItemSpecId:
    return ItemSpecId.create(
        runtime.id_mapper.get_int("item_spec", "control_terminal")
    )


def _all_room_lighting(runtime) -> tuple[LightingEnum, ...]:
    graph = runtime._spot_graph_repo.find_graph()
    return tuple(
        graph.get_spot(
            SpotId.create(runtime.id_mapper.get_int("spot", spot_name))
        ).atmosphere.lighting
        for spot_name in _ROOMS
    )


def _world_cooldown_tick(runtime, action_name: str) -> int | None:
    action_def = runtime._interaction_service._item_interaction_def(
        _terminal_spec(runtime), action_name
    )
    assert action_def is not None
    return runtime._interaction_cooldown_store.last_success_tick(
        _KUZE,
        item_action_key(int(_terminal_spec(runtime)), action_def.cooldown_key),
        scope=InteractionCooldownScope.WORLD,
    )


def _bulkhead_panel_state(runtime) -> dict[str, object]:
    spot_id = SpotId.create(runtime.id_mapper.get_int("spot", "observatory"))
    object_id = SpotObjectId.create(
        runtime.id_mapper.get_int("object", "bulkhead_panel")
    )
    interior = runtime._spot_interior_repo.find_by_spot_id(spot_id)
    assert interior is not None
    panel = interior.get_object(object_id)
    assert panel is not None
    return dict(panel.state)


def test_success_event_observes_committed_graph_and_cooldown(runtime) -> None:
    """成功イベントの配送時には全室の暗転と世界共通待ち時間が確定済みである。"""
    observations: list[tuple[tuple[LightingEnum, ...], int | None]] = []
    scope_factory = runtime._interaction_service._interaction_command_scope_factory
    dispatcher = scope_factory._sync_dispatcher
    dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda _: observations.append(
            (_all_room_lighting(runtime), _world_cooldown_tick(runtime, "cut_power"))
        ),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )

    runtime.do_interact_with_item(_KUZE, _terminal_spec(runtime), "cut_power")

    assert observations
    assert all(
        lighting == (LightingEnum.DARK,) * len(_ROOMS) and cooldown_tick == 0
        for lighting, cooldown_tick in observations
    )


def test_required_event_failure_rolls_back_graph_cooldown_and_delivery(runtime) -> None:
    """commit前必須処理が失敗すると全室・待ち時間を戻し成功イベントを渡さない。"""
    delivered: list[BaseDomainEvent] = []
    scope_factory = runtime._interaction_service._interaction_command_scope_factory
    dispatcher = scope_factory._sync_dispatcher
    dispatcher.register_required_before_commit(
        BaseDomainEvent,
        lambda event, context: (_ for _ in ()).throw(
            RuntimeError("item interaction sync failed")
        ),
    )
    dispatcher.register_after_commit(
        BaseDomainEvent,
        delivered.append,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )

    with pytest.raises(RuntimeError, match="item interaction sync failed"):
        runtime.do_interact_with_item(_KUZE, _terminal_spec(runtime), "cut_power")

    assert _all_room_lighting(runtime) == (LightingEnum.BRIGHT,) * len(_ROOMS)
    assert _world_cooldown_tick(runtime, "cut_power") is None
    assert delivered == []


def test_graph_save_failure_rolls_back_remote_interior_and_allows_retry(
    runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    """遠隔物体の保存後にgraph保存が失敗しても物体と待ち時間を戻し再実行できる。"""
    repository = runtime._spot_graph_repo
    original_save = repository.save
    save_calls = 0

    def fail_once(graph) -> None:
        nonlocal save_calls
        save_calls += 1
        if save_calls == 1:
            raise RuntimeError("graph save failed")
        original_save(graph)

    with monkeypatch.context() as patcher:
        patcher.setattr(repository, "save", fail_once)
        with pytest.raises(RuntimeError, match="graph save failed"):
            runtime.do_interact_with_item(
                _KUZE,
                _terminal_spec(runtime),
                "seal_bulkhead",
            )

    assert _bulkhead_panel_state(runtime) == {}
    assert _world_cooldown_tick(runtime, "seal_bulkhead") is None

    runtime.do_interact_with_item(
        _KUZE,
        _terminal_spec(runtime),
        "seal_bulkhead",
    )

    assert "sealed_at_tick" in _bulkhead_panel_state(runtime)
    assert _world_cooldown_tick(runtime, "seal_bulkhead") == 0

"""対人interactionが二者の状態を一つのCommandScopeで確定することを保証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerInteractedWithPlayerEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from tests.support.overflow_sinks import IGNORE_OVERFLOW


_RELAY = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "scenarios"
    / "relay_puzzle_demo.json"
)
_ACTOR = PlayerId(1)
_TARGET = PlayerId(2)

_STRIKE_DEF = {
    "action_name": "strike_down",
    "display_label": "殴り倒す",
    "preconditions": [{"condition_type": "ALWAYS"}],
    "effects": [
        {
            "effect_type": "APPLY_DAMAGE",
            "target": "TARGET_PLAYER",
            "parameters": {"damage": 9999},
        }
    ],
    "cooldown_ticks": 5,
}

_LOOT_DEF = {
    "action_name": "loot_from_downed",
    "display_label": "持ち物を奪う",
    "preconditions": [
        {"condition_type": "TARGET_PLAYER_IS_INCAPACITATED"},
        {
            "condition_type": "TARGET_HAS_ITEM",
            "item_spec_id_parameter_key": "item_spec_id",
        },
    ],
    "effects": [
        {
            "effect_type": "REMOVE_ITEM",
            "target": "TARGET_PLAYER",
            "parameters": {"item_spec_id_parameter": "item_spec_id"},
        },
        {
            "effect_type": "GIVE_ITEM",
            "target": "ACTOR",
            "parameters": {"item_spec_id_parameter": "item_spec_id"},
        },
    ],
}


def _runtime(tmp_path: Path, interaction: dict):
    scenario = json.loads(_RELAY.read_text(encoding="utf-8"))
    scenario["player_interactions"] = [interaction]
    path = tmp_path / "player_interaction_scope.json"
    path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    runtime = create_world_runtime(path)
    graph = runtime._spot_graph_repo.find_graph()
    actor_spot = graph.get_entity_spot(EntityId.create(int(_ACTOR)))
    graph.unplace_entity(EntityId.create(int(_TARGET)))
    graph.place_entity(EntityId.create(int(_TARGET)), actor_spot)
    runtime._spot_graph_repo.save(graph)
    return runtime


def _dispatcher(runtime):
    scope_factory = runtime._player_interaction_service._interaction_command_scope_factory
    return scope_factory._sync_dispatcher


def _owned_spec_ids(runtime, player_id: PlayerId) -> set[int]:
    inventory = runtime._player_inventory_repo.find_by_id(player_id)
    assert inventory is not None
    return {
        spec_id.value
        for spec_id in collect_owned_item_spec_ids_from_inventory(
            inventory, runtime._item_repo
        )
    }


def _knock_out(runtime, player_id: PlayerId) -> None:
    status = runtime._player_status_repo.find_by_id(player_id)
    assert status is not None
    status.apply_damage(status.hp.value)
    events = tuple(status.get_events())
    status.clear_events()
    runtime._player_status_repo.save(status)
    runtime._speech_event_publisher.publish_all(events)


def test_success_event_observes_committed_status_and_cooldown(tmp_path: Path) -> None:
    """成功観測が届く時点では対象の昏倒と行為者の待ち時間が確定済みである。"""
    runtime = _runtime(tmp_path, _STRIKE_DEF)
    observations: list[tuple[bool, int | None]] = []
    _dispatcher(runtime).register_after_commit(
        PlayerInteractedWithPlayerEvent,
        lambda _: observations.append(
            (
                runtime._player_status_repo.find_by_id(_TARGET).is_down,
                runtime._interaction_cooldown_store.last_success_tick(
                    _ACTOR, "strike_down"
                ),
            )
        ),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )

    runtime.do_interact_with_player(_ACTOR, _TARGET, "strike_down")

    assert observations == [(True, 0)]


def test_required_event_failure_rolls_back_status_cooldown_and_delivery(
    tmp_path: Path,
) -> None:
    """commit前必須処理が失敗するとHP・昏倒・待ち時間・成功配送を残さない。"""
    runtime = _runtime(tmp_path, _STRIKE_DEF)
    before = runtime._player_status_repo.find_by_id(_TARGET)
    assert before is not None
    before_hp = before.hp.value
    delivered: list[PlayerInteractedWithPlayerEvent] = []
    dispatcher = _dispatcher(runtime)
    dispatcher.register_required_before_commit(
        PlayerInteractedWithPlayerEvent,
        lambda event, context: (_ for _ in ()).throw(
            RuntimeError("player interaction sync failed")
        ),
    )
    dispatcher.register_after_commit(
        PlayerInteractedWithPlayerEvent,
        delivered.append,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )

    with pytest.raises(RuntimeError, match="player interaction sync failed"):
        runtime.do_interact_with_player(_ACTOR, _TARGET, "strike_down")

    after = runtime._player_status_repo.find_by_id(_TARGET)
    assert after is not None
    assert after.hp.value == before_hp
    assert after.is_down is False
    assert runtime._interaction_cooldown_store.last_success_tick(
        _ACTOR, "strike_down"
    ) is None
    assert runtime._death_grace_timer.is_pending(_TARGET) is False
    assert delivered == []


def test_actor_inventory_save_failure_rolls_back_both_inventories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """対象から削除後に行為者保存が失敗しても品物を複製・消失させない。"""
    runtime = _runtime(tmp_path, _LOOT_DEF)
    spec = next(iter(runtime._item_spec_repo.find_all()))
    grant_item_specs_to_inventory(
        _TARGET,
        (spec.item_spec_id,),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )
    _knock_out(runtime, _TARGET)
    before_actor = _owned_spec_ids(runtime, _ACTOR)
    before_target = _owned_spec_ids(runtime, _TARGET)
    original_save = InMemoryPlayerInventoryRepository.save

    def save_then_fail_for_actor(self, inventory) -> None:
        original_save(self, inventory)
        if inventory.player_id == _ACTOR:
            raise RuntimeError("actor inventory save failed")

    monkeypatch.setattr(
        InMemoryPlayerInventoryRepository,
        "save",
        save_then_fail_for_actor,
    )

    with pytest.raises(RuntimeError, match="actor inventory save failed"):
        runtime.do_interact_with_player(
            _ACTOR,
            _TARGET,
            "loot_from_downed",
            interaction_parameters={"item": spec.name},
        )

    assert _owned_spec_ids(runtime, _ACTOR) == before_actor
    assert _owned_spec_ids(runtime, _TARGET) == before_target

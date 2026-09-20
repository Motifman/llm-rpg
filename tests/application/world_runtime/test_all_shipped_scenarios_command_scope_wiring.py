"""全出荷シナリオの本番更新入口が確定区間へ接続されることを保証する。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIOS = tuple(sorted(Path("data/scenarios").glob("*.json")))


def _simulation_scope_owners(runtime: Any) -> dict[str, Any]:
    simulation = runtime._simulation_service
    owners: dict[str, Any] = {}
    for field in (
        "_scenario_event_stage",
        "_reactive_binding_stage",
        "_reactive_object_state_stage",
        "_sync_action_resolver_stage",
        "_environment_stage",
        "_day_night_stage",
        "_needs_decay_stage",
        "_monster_spawn_stage",
        "_monster_behavior_stage",
        "_food_spoilage_stage",
        "_player_outcome_rule_stage",
        "_death_grace_stage",
        "_trade_offer_expiry_stage",
        "_market_order_expiry_stage",
        "_status_effects_stage",
    ):
        owner = getattr(simulation, field)
        if owner is not None:
            owners[field] = getattr(owner, "_service", owner)
    return owners


def _runtime_scope_owners(runtime: Any) -> dict[str, Any]:
    return {
        "item_transfer": runtime._item_transfer_service,
        "movement": runtime._movement_service,
        "exploration": runtime._exploration_service,
        "player_trade": runtime._player_trade_service,
        "merchant_trade": runtime._merchant_trade_service,
        "market": runtime._market_service,
        "spot_interaction": runtime._interaction_service,
        "player_interaction": runtime._player_interaction_service,
        "meeting": runtime._meeting_command_service,
        **_simulation_scope_owners(runtime),
    }


@pytest.mark.parametrize("scenario_path", _SCENARIOS, ids=lambda path: path.stem)
def test_every_shipped_scenario_wires_all_present_command_scope_owners(
    scenario_path: Path,
) -> None:
    """各シナリオで存在する全更新serviceはfactoryを一つ以上持ち、未配線を残さない。"""
    runtime = create_world_runtime(scenario_path)

    for label, owner in _runtime_scope_owners(runtime).items():
        fields = tuple(
            name for name in vars(owner) if "command_scope_factory" in name
        )
        assert fields, f"{scenario_path.name}: {label} has no scope factory field"
        assert all(getattr(owner, field) is not None for field in fields), (
            f"{scenario_path.name}: {label} has an unwired scope factory"
        )

    for field in (
        "_use_item_command_scope_factory",
        "_tend_to_player_command_scope_factory",
        "_prepare_action_command_scope_factory",
    ):
        assert getattr(runtime, field) is not None, (
            f"{scenario_path.name}: runtime.{field} is unwired"
        )

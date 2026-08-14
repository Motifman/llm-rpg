"""異常中の緊急招集と、遺体報告・隔壁の例外を保証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI, _SENA, _KUZE = (PlayerId(i) for i in (1, 2, 3))
_REFUSAL_REASON = "異常が続いている間は緊急招集できない。"
_REFUSAL_ALTERNATIVE = "倒れている者を見つけたなら、その場で報告できる。"
_BULKHEAD_CONNECTIONS = ("observatory_to_medbay", "observatory_to_comms")


@pytest.fixture()
def runtime():
    return create_world_runtime(_DRILL)


def _terminal(runtime) -> ItemSpecId:
    return ItemSpecId.create(
        runtime.id_mapper.get_int("item_spec", "control_terminal")
    )


def _sabotage(runtime, action_name: str) -> None:
    runtime.do_interact_with_item(_KUZE, _terminal(runtime), action_name)


def _press(runtime, player_id: PlayerId = _SENA):
    return runtime.do_interact(
        player_id,
        "emergency_button",
        "press_emergency_button",
    )


def _messages(result) -> str:
    return "\n".join(result.messages)


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.teleport_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _bulkhead_passages_are_open(runtime) -> bool:
    graph = runtime._spot_graph_repo.find_graph()
    return all(
        graph.get_connection(
            ConnectionId.create(runtime.id_mapper.get_int("connection", name))
        ).passage.traversable
        for name in _BULKHEAD_CONNECTIONS
    )


def test_blackout_blocks_the_button_without_spending_it(runtime) -> None:
    """停電中は理由と遺体報告の代替を返し、個人の招集回数を消費しない。"""
    _sabotage(runtime, "cut_power")

    result = _press(runtime)

    assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM
    assert runtime._game_phase_store.has_emergency_button(_SENA) is True
    assert _REFUSAL_REASON in _messages(result)
    assert _REFUSAL_ALTERNATIVE in _messages(result)


def test_fuel_freeze_blocks_the_button(runtime) -> None:
    """燃料凍結中は、会議で解除するための緊急ボタンを入口で拒否する。"""
    _sabotage(runtime, "freeze_fuel")

    result = _press(runtime)

    assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM
    assert _REFUSAL_REASON in _messages(result)


def test_bulkhead_sabotage_does_not_block_the_button(runtime) -> None:
    """隔壁が降りている間も、扉妨害の例外として緊急招集は成立する。"""
    _sabotage(runtime, "seal_bulkhead")
    assert "bulkhead_sealed" in runtime._world_flag_state.as_frozen_set()

    _press(runtime)

    assert runtime._game_phase_store.current.phase is GamePhase.MEETING


def test_button_keeps_its_one_use_rule_without_an_active_condition(runtime) -> None:
    """異常が無ければ従来どおり一度だけ押せ、二度目は回数制限で拒否される。"""
    _press(runtime)
    runtime.end_meeting(reason="vote_concluded")

    second = _press(runtime)

    assert "二度" in _messages(second)


def test_body_report_still_starts_a_meeting_during_blackout(runtime) -> None:
    """停電中でも遺体報告は緊急ボタンの制限を通らず、会議を開始する。"""
    _sabotage(runtime, "cut_power")
    runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")

    result = runtime.report_body(_SENA, _MORI)

    assert result.success is True
    assert runtime._game_phase_store.current.phase is GamePhase.MEETING
    assert "power_out" in runtime._world_flag_state.as_frozen_set()


def test_bulkhead_flag_clears_when_both_passages_reopen(runtime) -> None:
    """隔壁の例外フラグは自動復帰と同じ4 tick境界で降り、古い異常を残さない。"""
    _sabotage(runtime, "seal_bulkhead")

    for _ in range(3):
        runtime.advance_tick()
    assert "bulkhead_sealed" in runtime._world_flag_state.as_frozen_set()
    assert _bulkhead_passages_are_open(runtime) is False

    runtime.advance_tick()

    assert "bulkhead_sealed" not in runtime._world_flag_state.as_frozen_set()
    assert _bulkhead_passages_are_open(runtime) is True


def test_every_condition_explicitly_declares_whether_it_blocks_the_button() -> None:
    """異常追加時の記入漏れを既定値へ縮退させず、三条件の意図を宣言で読める。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    declarations = {
        entry["flag"]: entry["blocks_emergency_button"]
        for entry in raw["ongoing_conditions"]
    }

    assert declarations == {
        "power_out": True,
        "fuel_frozen": True,
        "bulkhead_sealed": False,
    }


def test_missing_button_blocking_declaration_is_rejected() -> None:
    """blocks_emergency_button を省略した異常は、効いたつもりになる前に拒否する。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    del raw["ongoing_conditions"][0]["blocks_emergency_button"]

    with pytest.raises(
        ScenarioLoadError,
        match=r"ongoing_conditions\[0\].*blocks_emergency_button",
    ):
        ScenarioLoader().load_from_dict(raw)


def test_non_boolean_button_blocking_declaration_is_rejected() -> None:
    """blocks_emergency_button の未知表現を真偽へ暗黙変換せず拒否する。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    raw["ongoing_conditions"][0]["blocks_emergency_button"] = "false"

    with pytest.raises(
        ScenarioLoadError,
        match=r"ongoing_conditions\[0\].*blocks_emergency_button",
    ):
        ScenarioLoader().load_from_dict(raw)

"""station_drill の進行中異常が、状態に応じて全員の最終指示直前へ出ることを保証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI = PlayerId(1)
_KUZE = PlayerId(3)
_POWER_MESSAGE = "配電が落ちている。機関室の主配電盤で復旧できる。"
_FUEL_MESSAGE = (
    "燃料が凍りはじめている。燃料庫の解氷弁と機関室の送油弁を"
    "二人で同時に開ける必要がある。"
)
_ONGOING_HEADER = "【進行中の異常】"
_ELAPSED_HEADER = "【時間の経過】"
_INSTRUCTION = "利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。"


@pytest.fixture()
def runtime():
    return create_world_runtime(_DRILL)


def _terminal_spec(runtime) -> ItemSpecId:
    return ItemSpecId.create(
        runtime.id_mapper.get_int("item_spec", "control_terminal")
    )


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _user_prompt(runtime, player_id: PlayerId) -> str:
    return runtime.build_full_prompt(player_id)["messages"][1]["content"]


def test_cut_power_puts_the_active_blackout_in_every_player_prompt(runtime) -> None:
    """実際の cut_power が power_out を立て、8人全員へ復旧場所を常時表示する。"""
    runtime.do_interact_with_item(_KUZE, _terminal_spec(runtime), "cut_power")

    assert "power_out" in runtime._world_flag_state.as_frozen_set()
    assert len(runtime.get_player_ids()) == 8
    for player_id in runtime.get_player_ids():
        user = _user_prompt(runtime, player_id)
        assert _ONGOING_HEADER in user
        assert _POWER_MESSAGE in user
        assert _FUEL_MESSAGE not in user


def test_freeze_fuel_puts_only_the_active_critical_condition_in_the_prompt(
    runtime,
) -> None:
    """燃料凍結だけが成立中なら、時間を足さず復旧要件だけを継続表示する。"""
    runtime.do_interact_with_item(_KUZE, _terminal_spec(runtime), "freeze_fuel")

    user = _user_prompt(runtime, _MORI)
    assert _FUEL_MESSAGE in user
    assert _POWER_MESSAGE not in user
    assert "あと" not in user.split(_ONGOING_HEADER, 1)[1].split(_INSTRUCTION, 1)[0]


def test_restore_power_removes_the_blackout_from_every_player_prompt(runtime) -> None:
    """主配電盤で復旧に成功すると power_out と進行中異常の停電行が消える。"""
    runtime.do_interact_with_item(_KUZE, _terminal_spec(runtime), "cut_power")
    _move(runtime, _MORI, "machine_room")
    runtime.do_interact(_MORI, "main_distribution_panel", "restore_power")

    assert "power_out" not in runtime._world_flag_state.as_frozen_set()
    for player_id in runtime.get_player_ids():
        assert _POWER_MESSAGE not in _user_prompt(runtime, player_id)


def test_no_active_condition_omits_the_whole_section(runtime) -> None:
    """進行中の宣言フラグが一つも無ければ、空の見出しもプロンプトへ出さない。"""
    for player_id in runtime.get_player_ids():
        assert _ONGOING_HEADER not in _user_prompt(runtime, player_id)


def test_only_fuel_freeze_declares_meeting_start_resolution_effects() -> None:
    """会議で解ける異常は on_meeting_start の有無だけで区別する。"""
    loaded = ScenarioLoader().load_from_file(_DRILL)

    conditions = {condition.flag: condition for condition in loaded.ongoing_conditions}
    assert conditions["power_out"].on_meeting_start == ()
    assert [
        effect.effect_type.value
        for effect in conditions["fuel_frozen"].on_meeting_start
    ] == ["RESOLVE_ONGOING_CONDITION", "SHOW_MESSAGE"]
    assert [
        effect.effect_type.value for effect in conditions["fuel_frozen"].resolution
    ] == ["CLEAR_FLAG", "SET_FLAG"]


def test_active_condition_remains_in_the_variable_tail_before_instruction(runtime) -> None:
    """実プロンプトでは異常一覧も直近の出来事より後の可変な末尾へ置かれる。"""
    runtime.do_interact_with_item(_KUZE, _terminal_spec(runtime), "cut_power")

    user = _user_prompt(runtime, _MORI)
    section = f"{_ONGOING_HEADER}\n- {_POWER_MESSAGE}"
    assert user.index("【直近の出来事】") < user.index(_ONGOING_HEADER)
    assert user.index(_ONGOING_HEADER) < user.index(_ELAPSED_HEADER)
    assert section in user
    assert user.endswith(_INSTRUCTION)


def test_departed_player_also_sees_the_active_condition(runtime) -> None:
    """死亡後に手番を持つ幽霊にも、生存者と同じ進行中異常の事実が届く。"""
    runtime.do_interact_with_item(_KUZE, _terminal_spec(runtime), "cut_power")
    runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")
    runtime.advance_tick()

    assert runtime._departed_position_store.find(_MORI) is not None
    assert _POWER_MESSAGE in _user_prompt(runtime, _MORI)


def test_ongoing_condition_rejects_a_flag_that_nothing_can_set() -> None:
    """SET_FLAG も初期値も無いフラグの表示宣言は、起動時に原因つきで拒否する。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    raw["ongoing_conditions"].append(
        {"flag": "power_ot", "message": "存在しない異常。"}
    )

    with pytest.raises(ScenarioLoadError, match=r"ongoing_conditions.*power_ot"):
        ScenarioLoader().load_from_dict(raw)


@pytest.mark.parametrize("unknown_key", ["critical", "critcal", "unknown"])
def test_ongoing_condition_rejects_unknown_keys(unknown_key: str) -> None:
    """効かない追加キーは黙って無視せず、宣言位置を示して読み込みを止める。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    raw["ongoing_conditions"][0][unknown_key] = True

    with pytest.raises(ScenarioLoadError, match=rf"ongoing_conditions\[0\].*{unknown_key}"):
        ScenarioLoader().load_from_dict(raw)


def test_meeting_resolution_rejects_an_empty_effect_list() -> None:
    """会議で解けると宣言しながら効果が空なら、省略へ縮退せず読み込みを止める。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    raw["ongoing_conditions"][0]["on_meeting_start"] = []

    with pytest.raises(ScenarioLoadError, match=r"on_meeting_start.*空"):
        ScenarioLoader().load_from_dict(raw)


def test_condition_resolution_must_clear_its_own_active_flag() -> None:
    """共通 resolution が成立条件の flag を降ろさなければ、解決したふりをする前に拒否する。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    raw["ongoing_conditions"][1]["resolution"][0]["parameters"][
        "flag_name"
    ] = "power_out"

    with pytest.raises(ScenarioLoadError, match=r"fuel_frozen.*CLEAR_FLAG"):
        ScenarioLoader().load_from_dict(raw)


def test_meeting_resolution_rejects_effects_without_a_global_application_path() -> None:
    """会議境界で適用できない物体効果は、警告だけで捨てず読み込み時に拒否する。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    raw["ongoing_conditions"][1]["on_meeting_start"].append(
        {
            "effect_type": "CHANGE_ATMOSPHERE",
            "parameters": {"target_spot": "hall", "lighting": "BRIGHT"},
        }
    )

    with pytest.raises(ScenarioLoadError, match=r"未対応.*CHANGE_ATMOSPHERE"):
        ScenarioLoader().load_from_dict(raw)


def test_meeting_resolution_does_not_count_as_the_condition_flag_producer() -> None:
    """解決効果の SET_FLAG だけで初めて成立する循環的な異常宣言は拒否する。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    raw["ongoing_conditions"].append(
        {
            "flag": "self_created_condition",
            "message": "発生経路のない異常。",
            "resolution": [
                {
                    "effect_type": "SET_FLAG",
                    "parameters": {"flag_name": "self_created_condition"},
                },
                {
                    "effect_type": "CLEAR_FLAG",
                    "parameters": {"flag_name": "self_created_condition"},
                },
            ],
            "on_meeting_start": [
                {
                    "effect_type": "RESOLVE_ONGOING_CONDITION",
                    "parameters": {"flag": "self_created_condition"},
                },
            ],
        }
    )

    with pytest.raises(ScenarioLoadError, match=r"self_created_condition.*宣言されていません"):
        ScenarioLoader().load_from_dict(raw)


def test_resolve_effect_rejects_a_condition_without_resolution() -> None:
    """RESOLVE_ONGOING_CONDITION の参照先に resolution が無ければ起動前に拒否する。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    raw["synchronized_action_groups"][0]["on_complete"][0]["parameters"][
        "flag"
    ] = "power_out"

    with pytest.raises(ScenarioLoadError, match=r"resolution.*power_out"):
        ScenarioLoader().load_from_dict(raw)

"""所持道具に宣言した操作が prompt から実行まで一続きになることを保証する。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    GameRuntimeManager,
)
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    SessionCreateRequest,
)


_SCENARIO = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "scenarios"
    / "item_interaction_demo.json"
)
_OWNER, _OTHER = PlayerId(1), PlayerId(2)


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _radio_spec(runtime) -> ItemSpecId:
    return ItemSpecId.create(runtime.id_mapper.get_int("item_spec", "portable_radio"))


def _executor(runtime) -> SpotGraphToolExecutor:
    """実 runtime へ interact を渡す最小 executor を作る。"""
    from unittest.mock import MagicMock

    return SpotGraphToolExecutor(
        spot_graph_world_services=SpotGraphWorldServices(
            interaction=MagicMock(),
            exploration=MagicMock(),
            world_flags=MagicMock(as_frozen_set=MagicMock(return_value=frozenset())),
            game_end_evaluator=MagicMock(),
            exploration_progress=MagicMock(),
            movement=MagicMock(),
            simulation=None,
        ),
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
        runtime=runtime,
    )


def _latest_action(runtime, player_id: PlayerId):
    entries = runtime._action_result_store.get_recent(player_id, 1)
    assert entries
    return entries[0]


def test_owner_prompt_offers_item_actions_in_the_inventory_row(runtime) -> None:
    """所持者の実 prompt は道具名と実行可能な action_name を同じ行に出す。"""
    user = runtime.build_full_prompt(_OWNER)["messages"][1]["content"]

    row = next(line for line in user.splitlines() if '"携帯無線機"' in line)

    assert '応答を試す → "hail_the_mainland"' in row
    assert '電池を確かめる → "check_battery"' in row


def test_item_action_applies_its_declared_effect(runtime) -> None:
    """所持道具の操作を実行すると宣言した結果文と世界フラグが適用される。"""
    result = runtime.do_interact_with_item(
        _OWNER, _radio_spec(runtime), "hail_the_mainland"
    )

    assert result.messages == ("雑音の向こうで短い応答が返った。",)
    assert "radio_hailed" in runtime._world_flag_state.as_frozen_set()


def test_interact_executor_dispatches_the_held_item_target(runtime) -> None:
    """既存 interact の解決後引数は専用 tool を増やさず道具操作へ到達する。"""
    result = _executor(runtime)._interact(
        int(_OWNER),
        {
            "item_spec_id": int(_radio_spec(runtime)),
            "action_name": "hail_the_mainland",
            "inner_thought": "応答を確かめる。",
        },
    )

    assert result.success is True
    assert "短い応答" in result.message
    assert "radio_hailed" in runtime._world_flag_state.as_frozen_set()


def test_llm_handler_resolves_and_executes_the_held_item_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """実 handler は target_label を道具 ID へ解決し、executor まで運ぶ。"""
    monkeypatch.setenv("SPOT_GRAPH_TICK_LOOP_ENABLED", "false")
    manager = GameRuntimeManager(
        scenarios_dir=_SCENARIO.parent,
        characters_path=tmp_path / "characters.json",
    )
    character = manager.create_character(CharacterCreateRequest(name="通信士"))
    summary = manager.create_session(
        SessionCreateRequest(
            world_id="item_interaction_demo",
            character_ids=[character.id],
        )
    )
    state = manager._sessions[summary.session_id]
    state.llm_wiring.llm_client = StubLlmClient(
        tool_call_to_return={
            "name": "interact",
            "arguments": {
                "target_label": "携帯無線機",
                "action_name": "hail_the_mainland",
                "inner_thought": "遠くへ呼びかける。",
                "expected_result": "応答が返る。",
            },
        }
    )
    player_id = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))

    result = state.llm_wiring.run_turn(player_id)

    assert result.success is True
    assert "radio_hailed" in state.runtime._world_flag_state.as_frozen_set()
    assert _latest_action(state.runtime, player_id).identifier_arguments == {
        "action_name": "hail_the_mainland",
        "target_label": "携帯無線機",
    }


def test_unknown_item_action_is_reported_as_a_missing_name(runtime) -> None:
    """道具に無い action_name は前提条件失敗へ混ぜず、発明した名前として返す。"""
    result = _executor(runtime)._interact(
        int(_OWNER),
        {
            "item_spec_id": int(_radio_spec(runtime)),
            "action_name": "repair_the_radio",
            "inner_thought": "直せるか試す。",
        },
    )

    assert result.success is False
    assert result.error_code == "INTERACTION_ACTION_NOT_FOUND"
    assert "repair_the_radio" in result.message
    assert "表示に無い名前は推測しない" in result.remediation


def test_non_owner_neither_sees_nor_can_call_the_item_action(runtime) -> None:
    """未所持者には操作を宣伝せず、内部 ID を直接渡しても実行を拒否する。"""
    user = runtime.build_full_prompt(_OTHER)["messages"][1]["content"]

    assert "hail_the_mainland" not in user
    inventory = user.split("所持アイテム:", 1)[-1].split("\n\n", 1)[0]
    assert '"携帯無線機"' not in inventory
    with pytest.raises(InteractionNotAllowedException, match="持っていない"):
        runtime.do_interact_with_item(
            _OTHER, _radio_spec(runtime), "hail_the_mainland"
        )


def test_cooldown_is_independent_per_action_name(runtime) -> None:
    """道具の A を使った直後でも、同じ品目に宣言した B は実行できる。"""
    spec_id = _radio_spec(runtime)
    runtime.do_interact_with_item(_OWNER, spec_id, "hail_the_mainland")

    result = runtime.do_interact_with_item(_OWNER, spec_id, "check_battery")

    assert result.messages == ("電池はまだ残っている。",)


def test_two_instances_share_the_same_item_spec_cooldown(runtime) -> None:
    """同じ道具を 2 個持っても、品目単位の待ち時間を迂回できない。"""
    spec_id = _radio_spec(runtime)
    runtime.do_interact_with_item(_OWNER, spec_id, "hail_the_mainland")

    with pytest.raises(InteractionNotAllowedException, match="まだそれはできない"):
        runtime.do_interact_with_item(_OWNER, spec_id, "hail_the_mainland")

    user = runtime.build_full_prompt(_OWNER)["messages"][1]["content"]
    assert 'いまできない: 応答を試す → "hail_the_mainland"' in user


def test_unmet_item_precondition_stays_visible_with_its_reason(runtime) -> None:
    """前提を満たさない道具操作も、物体操作と同じ断り付きで所持品行に残る。"""
    user = runtime.build_full_prompt(_OWNER)["messages"][1]["content"]

    assert (
        'いまできない: 観測記録を送る → "send_weather_report"'
        "（送る観測記録がまだ無い。）" in user
    )


def test_hidden_item_action_is_neither_named_nor_executable(runtime) -> None:
    """役割を伏せる道具操作は物体と同じ判断で一覧から落とし、執行側でも拒否する。"""
    user = runtime.build_full_prompt(_OWNER)["messages"][1]["content"]

    assert "open_service_channel" not in user
    assert "保守回線を開く" not in user
    with pytest.raises(InteractionNotAllowedException, match="権限は無い"):
        runtime.do_interact_with_item(
            _OWNER, _radio_spec(runtime), "open_service_channel"
        )


def test_living_inventory_stays_private_but_fallen_inventory_is_visible(runtime) -> None:
    """生者の所持品は他人へ漏らさず、倒れた相手の道具名は従来どおり表示する。"""
    before = runtime.build_full_prompt(_OTHER)["messages"][1]["content"]
    assert '"携帯無線機"' not in before

    status = runtime._player_status_repo.find_by_id(_OWNER)
    status.apply_damage(status.hp.value)
    runtime._player_status_repo.save(status)

    after = runtime.build_full_prompt(_OTHER)["messages"][1]["content"]
    assert "携帯無線機" in after
    # 他人の道具は対象の状態として見えるだけで、操作は所持者以外へ宣伝しない。
    assert "hail_the_mainland" not in after

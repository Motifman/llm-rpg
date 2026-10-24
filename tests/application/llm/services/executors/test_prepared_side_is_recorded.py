"""二人で合わせる操作の片側を受け持つと、その行動の結果が 1 件記録され、本人の【直近の出来事】に出る。

interact は合わせる操作の名前なら準備の登録 (`_prepare_action`) に回す。phase_b は
成功した interact を「do_interact が記録済み」とみなして汎用の記録を飛ばす。準備の
登録は do_interact を通らないので、どこも記録せず、本人は弁を受け持ったことを
次の手番で読めなかった。
"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_DRILL = Path(__file__).resolve().parents[5] / "data" / "scenarios" / "station_drill.json"
_MORI, _KUZE = PlayerId(1), PlayerId(3)


def _frozen_runtime_with_mori_at_the_valve():
    runtime = create_world_runtime(_DRILL)
    runtime.do_interact_with_item(
        _KUZE,
        ItemSpecId.create(runtime.id_mapper.get_int("item_spec", "control_terminal")),
        "freeze_fuel",
    )
    graph = runtime._spot_graph_repo.find_graph()
    graph.teleport_entity(
        EntityId.create(int(_MORI)), SpotId.create(runtime.id_mapper.get_int("spot", "fuel_bay"))
    )
    runtime._spot_graph_repo.save(graph)
    return runtime


def _wiring(runtime, tool_call):
    return _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=StubLlmClient(tool_call_to_return=tool_call),
    )


class TestTheTakenSideIsRecorded:
    """interact で合わせる操作の片側を受け持ったとき、行動の結果が残ることを保証する。"""

    def test_taking_one_side_records_one_action_result(self) -> None:
        """弁を interact で受け持つと、その人の行動の結果がちょうど 1 件増え、「まだ動いていない」と残る。"""
        runtime = _frozen_runtime_with_mori_at_the_valve()
        wiring = _wiring(
            runtime,
            {
                "name": "interact",
                "arguments": {
                    "target_label": "解氷弁",
                    "action_name": "open_thaw_valve",
                    "inner_thought": "弁を受け持つ",
                },
            },
        )
        before = len(runtime._action_result_store.get_recent(_MORI, 100))

        result = wiring.run_turn(_MORI)

        assert result.success is True
        recorded = runtime._action_result_store.get_recent(_MORI, 100)[before:]
        assert len(recorded) == 1
        assert "まだ動いていない" in recorded[0].result_summary

    def test_the_taken_side_appears_in_recent_events(self) -> None:
        """受け持った次の手番のプロンプトで、【直近の出来事】に、どの対象で受け持ったかが出る。"""
        runtime = _frozen_runtime_with_mori_at_the_valve()
        wiring = _wiring(
            runtime,
            {
                "name": "interact",
                "arguments": {
                    "target_label": "解氷弁",
                    "action_name": "open_thaw_valve",
                    "inner_thought": "弁を受け持つ",
                },
            },
        )
        wiring.run_turn(_MORI)

        user_text = runtime.build_full_prompt(_MORI)["messages"][1]["content"]

        recent = user_text.split("【直近の出来事】", 1)[1].split("【", 1)[0]
        assert "「解氷弁」で解氷弁を開く準備をする" in recent
        assert "受け持った" in recent

    def test_a_refused_side_is_recorded_once(self) -> None:
        """同じ人が両方の弁を受け持とうとして 2 つ目を断られたとき、断られた行動の結果は 1 件だけ記録される。"""
        runtime = _frozen_runtime_with_mori_at_the_valve()
        _wiring(
            runtime,
            {
                "name": "interact",
                "arguments": {"target_label": "解氷弁", "action_name": "open_thaw_valve", "inner_thought": "弁を受け持つ"},
            },
        ).run_turn(_MORI)
        graph = runtime._spot_graph_repo.find_graph()
        graph.teleport_entity(
            EntityId.create(int(_MORI)), SpotId.create(runtime.id_mapper.get_int("spot", "machine_room"))
        )
        runtime._spot_graph_repo.save(graph)
        second = _wiring(
            runtime,
            {
                "name": "interact",
                "arguments": {"target_label": "送油弁", "action_name": "open_oil_feed_valve", "inner_thought": "もう一方も"},
            },
        )
        before = len(runtime._action_result_store.get_recent(_MORI, 100))

        result = second.run_turn(_MORI)

        assert result.success is False
        assert result.error_code == "INTERACTION_PRECONDITION_FAILED"
        assert len(runtime._action_result_store.get_recent(_MORI, 100)[before:]) == 1

    def test_the_refusal_advice_names_no_action(self) -> None:
        """2 つ目の弁を断られたときの対処文は、どちらの操作名も出さない (他の人に頼む言葉にそのまま使われる)。"""
        runtime = _frozen_runtime_with_mori_at_the_valve()
        _wiring(
            runtime,
            {
                "name": "interact",
                "arguments": {"target_label": "解氷弁", "action_name": "open_thaw_valve", "inner_thought": "弁を受け持つ"},
            },
        ).run_turn(_MORI)
        graph = runtime._spot_graph_repo.find_graph()
        graph.teleport_entity(
            EntityId.create(int(_MORI)), SpotId.create(runtime.id_mapper.get_int("spot", "machine_room"))
        )
        runtime._spot_graph_repo.save(graph)

        result = _wiring(
            runtime,
            {
                "name": "interact",
                "arguments": {"target_label": "送油弁", "action_name": "open_oil_feed_valve", "inner_thought": "もう一方も"},
            },
        ).run_turn(_MORI)

        assert result.error_code == "INTERACTION_PRECONDITION_FAILED"
        assert "open_thaw_valve" not in result.remediation
        assert "open_oil_feed_valve" not in result.remediation


class TestTheTakenSideIsToldByItsDisplayName:
    """受け持ったことを伝える文が、操作名ではなく表示名で語ることを保証する。"""

    def test_result_uses_the_display_label_not_the_action_name(self) -> None:
        """弁を受け持つと、結果の文は「「解氷弁を開く準備をする」を受け持った」と表示名で語り、open_thaw_valve は出ない。"""
        runtime = _frozen_runtime_with_mori_at_the_valve()
        wiring = _wiring(
            runtime,
            {
                "name": "interact",
                "arguments": {"target_label": "解氷弁", "action_name": "open_thaw_valve", "inner_thought": "弁を受け持つ"},
            },
        )

        result = wiring.run_turn(_MORI)

        assert "「解氷弁を開く準備をする」を受け持った" in result.message
        assert "open_thaw_valve" not in result.message

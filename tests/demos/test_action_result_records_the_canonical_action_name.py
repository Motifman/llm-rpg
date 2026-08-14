"""行動の記録に、実際に呼んだ tool の再利用可能な引数を残す。

``action_summary`` は「「見晴らしの岩」で「海を見渡す」」のように display_label で
書かれる。意味で読み返せるようにした判断 (#928) はそのままだが、**その文からは
実際に呼んだ名前を復元できない**。

行動を記憶や分析へ渡すとき、何を呼んだのかが分からないと再現も突き合わせも
できない。表示は変えず、事実として別に持つ。

この段階では **記録するだけ** で、プロンプトの表示は一切変わらない。表示へ出す
判断は別に行う。
"""

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.demos.station_drill_lighting_helpers import darken_spot
from tests.demos._world_runtime_helpers import create_world_runtime_session


_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI, _KUZE = PlayerId(1), PlayerId(3)


def _latest_action(runtime, player_id: PlayerId):
    entries = runtime._action_result_store.get_recent(player_id, 1)
    assert entries, "行動結果が記録されていない"
    return entries[0]


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity_id = EntityId.create(int(player_id))
    graph.unplace_entity(entity_id)
    graph.place_entity(
        entity_id, SpotId.create(runtime.id_mapper.get_int("spot", spot))
    )
    runtime._spot_graph_repo.save(graph)


def test_object_interaction_records_the_arguments_that_were_called() -> None:
    """物体操作は対象名と action_name を構造化して記録する。"""
    runtime = create_world_runtime(_SCENARIO)

    runtime.do_interact(_MORI, "duty_board", "read_board")

    entry = _latest_action(runtime, _MORI)
    assert entry.identifier_arguments == {
        "action_name": "read_board",
        "target_label": "当番表",
    }
    # 表示は従来どおり display_label のまま。両方が別々に残る。
    assert "当番表を読む" in entry.action_summary
    assert "read_board" not in entry.action_summary


def test_llm_handler_keeps_the_labels_sent_before_resolver_conversion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """LLM の成功経路は resolver 前の対象名を行動履歴まで運ぶ。

    ``interact`` の resolver は ``target_label`` を内部の ``object_id`` へ
    置き換える。handler が呼び出し時の射影を運ばないと、executor 側で
    ``action_name`` は作り直せても対象名だけが静かに消える。実際の handler
    経路を通し、モデルが送った再利用可能な名前が両方残ることを固定する。
    """
    stub = StubLlmClient(
        tool_call_to_return={
            "name": "interact",
            "arguments": {
                "target_label": "当番表",
                "action_name": "read_board",
                "inner_thought": "当番を確かめる。",
                "expected_result": "担当が分かる。",
            },
        }
    )
    state = create_world_runtime_session(
        monkeypatch,
        tmp_path,
        stub,
        world_id="station_drill",
    )
    player_id = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))

    result = state.llm_wiring.run_turn(player_id)

    assert result.success is True
    entry = _latest_action(state.runtime, player_id)
    assert entry.identifier_arguments == {
        "action_name": "read_board",
        "target_label": "当番表",
    }


def test_object_interaction_call_reaches_the_real_prompt() -> None:
    """成功した操作の正規引数が、実 prompt の直近出来事へ呼び出し形で届く。"""
    runtime = create_world_runtime(_SCENARIO)

    runtime.do_interact(_MORI, "duty_board", "read_board")
    user = runtime.build_full_prompt(_MORI)["messages"][1]["content"]

    call_line = next(line for line in user.splitlines() if "呼び出し: interact(" in line)
    assert 'action_name="read_board"' in call_line
    assert 'target_label="当番表"' in call_line
    # 対象名は写せる値なので引用するが、渡せない表示名は引用しない。
    assert "「当番表」で当番表を読む" in user
    assert "「当番表を読む」" not in user


def test_failed_interaction_does_not_expose_rejected_call_as_a_prompt_example(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """handler で失敗した interaction は呼び出し行を prompt に残さない。"""
    stub = StubLlmClient(
        tool_call_to_return={
            "name": "interact",
            "arguments": {
                "target_label": "配膳用の裏口",
                "action_name": "進む",
                "inner_thought": "ここから物資庫へ進む。",
                "expected_result": "物資庫へ着く。",
            },
        }
    )
    state = create_world_runtime_session(
        monkeypatch,
        tmp_path,
        stub,
        world_id="station_drill",
    )
    player_id = PlayerId(int(state.runtime.scenario.player_spawns[0].player_id))

    result = state.llm_wiring.run_turn(player_id)
    user = state.runtime.build_full_prompt(player_id)["messages"][1]["content"]

    assert result.success is False
    assert "[失敗]" in user
    assert "INVALID_TARGET_LABEL" in user
    assert "呼び出し:" not in user
    assert 'action_name="進む"' not in user


def test_person_interaction_records_the_arguments_that_were_called() -> None:
    """対人操作も対象名と action_name を同じ構造で記録する。"""
    runtime = create_world_runtime(_SCENARIO)
    for pid in (_KUZE, _MORI):
        _move(runtime, pid, "corridor")
    darken_spot(runtime)

    runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")

    entry = _latest_action(runtime, _KUZE)
    assert entry.identifier_arguments == {
        "action_name": "strike_down",
        "target_label": "モリ",
    }
    assert "人を襲う" in entry.action_summary


def test_tools_without_identifier_arguments_leave_the_mapping_empty() -> None:
    """完全一致引数を持たない直接実行の記録は空のままにする。

    探索や移動には呼ぶべき interaction 名が無い。無いものを埋めると、
    あとで「この行動は何を呼んだか」を問うたときに嘘になる。
    """
    runtime = create_world_runtime(_SCENARIO)

    runtime.do_explore(_MORI)

    entry = _latest_action(runtime, _MORI)
    assert entry.identifier_arguments == {}

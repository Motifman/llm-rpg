"""行動の記録に、実際に呼んだ interaction の正規名を残す。

``action_summary`` は「「見晴らしの岩」で「海を見渡す」」のように display_label で
書かれる。意味で読み返せるようにした判断 (#928) はそのままだが、**その文からは
実際に呼んだ名前を復元できない**。

行動を記憶や分析へ渡すとき、何を呼んだのかが分からないと再現も突き合わせも
できない。表示は変えず、事実として別に持つ。

この段階では **記録するだけ** で、プロンプトの表示は一切変わらない。表示へ出す
判断は別に行う。
"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


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


def test_object_interaction_records_the_name_that_was_called() -> None:
    """物体への操作は、表示名ではなく呼んだ action_name を記録する。"""
    runtime = create_world_runtime(_SCENARIO)

    runtime.do_interact(_MORI, "duty_board", "read_board")

    entry = _latest_action(runtime, _MORI)
    assert entry.action_name == "read_board"
    # 表示は従来どおり display_label のまま。両方が別々に残る。
    assert "当番表を読む" in entry.action_summary
    assert "read_board" not in entry.action_summary


def test_person_interaction_records_the_name_that_was_called() -> None:
    """対人の操作も同じく、呼んだ action_name を記録する。"""
    runtime = create_world_runtime(_SCENARIO)
    for pid in (_KUZE, _MORI):
        _move(runtime, pid, "corridor")

    runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")

    entry = _latest_action(runtime, _KUZE)
    assert entry.action_name == "strike_down"
    assert "背後から襲う" in entry.action_summary


def test_tools_without_an_action_name_leave_it_empty() -> None:
    """action_name を持たない tool の記録は空のままにする。

    移動や発話には呼ぶべき interaction 名が無い。無いものを埋めると、
    あとで「この行動は何を呼んだか」を問うたときに嘘になる。
    """
    runtime = create_world_runtime(_SCENARIO)

    runtime.do_wait(_MORI, reason="様子を見る")

    entry = _latest_action(runtime, _MORI)
    assert entry.action_name is None

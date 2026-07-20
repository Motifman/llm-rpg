"""WorldRuntime.do_interact が interaction service に current_tick を渡すことを固定する。

備蓄プール (OBJECT_STOCK_AT_LEAST / CONSUME_OBJECT_STOCK) の lazy 再生は
current_tick が無いと働かない。LLM の採取主経路 (spot_graph_interact →
do_interact) がここを通るため、current_tick を渡し忘れると採取源が永久枯渇する
(reactive_binding も pool 化で削除済み)。domain service 直叩きテストでは
この配線抜けを検出できないため、do_interact 経由で固定する (codex #761 CRITICAL)。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.world_runtime.world_runtime import WorldRuntime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _fake_runtime() -> MagicMock:
    """do_interact が触る collaborator を差した runtime スタブ。

    id_mapper 等は WorldRuntime では property なので、実インスタンスには
    set できない。self を MagicMock にして unbound do_interact を呼ぶ
    (属性は自動で MagicMock を返し、id/tick/graph だけ実値を設定する)。
    """
    rt = MagicMock()
    rt.id_mapper.get_int.return_value = 1
    graph = MagicMock()
    graph.get_entity_spot.return_value = SpotId.create(1)
    graph._graph_id = SpotGraphId.create(1)
    rt._spot_graph_repo.find_graph.return_value = graph
    rt._interaction_service.execute_interaction.return_value = MagicMock(messages=[])
    rt.current_tick.return_value = 42
    rt._object_display_name_at_player_spot.return_value = "貝の岩棚"
    rt._interaction_action_label_ja.return_value = "採る"
    return rt


class TestDoInteractPassesCurrentTick:
    def test_current_tick_forwarded_to_execute_interaction(self) -> None:
        """do_interact は execute_interaction に WorldTick(current_tick()) を渡す。"""
        rt = _fake_runtime()
        # unbound で呼ぶ (self=rt スタブ)。
        WorldRuntime.do_interact(rt, PlayerId(1), "shellfish_rocks", "gather_shellfish")
        _, kwargs = rt._interaction_service.execute_interaction.call_args
        assert kwargs.get("current_tick") == WorldTick(42)

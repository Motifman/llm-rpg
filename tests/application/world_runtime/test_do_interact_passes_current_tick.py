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
from ai_rpg_world.domain.world_graph.event.spot_graph_event import SpotObjectInteractedEvent
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
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
    obj = MagicMock()
    obj.interactions = (
        InteractionDef(
            action_name="gather_shellfish",
            display_label="貝を採る",
            preconditions=(),
            effects=(),
            witness_observation_message="{actor}が岩棚で貝を採った。",
        ),
    )
    interior = MagicMock()
    interior.get_object.return_value = obj
    rt._spot_interior_repo.find_by_spot_id.return_value = interior
    rt._interaction_service.execute_interaction.return_value = MagicMock(
        messages=[],
        action_display_label="貝を採る",
    )
    rt.current_tick.return_value = 42
    rt._object_display_name_at_player_spot.return_value = "貝の岩棚"
    return rt


class TestDoInteractPassesCurrentTick:
    def test_declared_display_label_is_used_in_action_result(self) -> None:
        """直近の出来事にはaction_nameでなく実行したInteractionDefの意味表示を残す。"""
        rt = _fake_runtime()

        WorldRuntime.do_interact(
            rt,
            PlayerId(1),
            "shellfish_rocks",
            "gather_shellfish",
        )

        action_summary = rt._record_action_result.call_args.args[1]
        assert action_summary == "「貝の岩棚」で「貝を採る」"

    def test_current_tick_forwarded_to_execute_interaction(self) -> None:
        """do_interact は execute_interaction に WorldTick(current_tick()) を渡す。"""
        rt = _fake_runtime()
        # unbound で呼ぶ (self=rt スタブ)。
        WorldRuntime.do_interact(rt, PlayerId(1), "shellfish_rocks", "gather_shellfish")
        _, kwargs = rt._interaction_service.execute_interaction.call_args
        assert kwargs.get("current_tick") == WorldTick(42)

    def test_do_interact_does_not_add_duplicate_interacted_event(self) -> None:
        """do_interact は SpotObjectInteractedEvent を自分では積まない (二重発火の防止)。

        成功イベントの組み立ては ``SpotInteractionApplicationService`` 側に一本化
        されている。かつては do_interact でも 2 件目を積んでいたが、その event は
        ``witness_policy`` を渡しておらず既定の SAME_SPOT になるため、ACTOR_ONLY
        の秘匿行為が同スポットの第三者に漏れ、SAME_SPOT では同じ観測が 2 件届いて
        いた。目撃者用文面と表示ラベルが正規経路の event に載ることは
        tests/application/world_graph/test_spot_graph_event_publication.py の
        ``test_publishes_spot_object_interacted_event`` が固定している。
        """
        rt = _fake_runtime()
        WorldRuntime.do_interact(rt, PlayerId(1), "shellfish_rocks", "gather_shellfish")

        add_event = rt._spot_graph_repo.find_graph.return_value.add_event
        interacted = [
            call.args[0]
            for call in add_event.call_args_list
            if call.args and isinstance(call.args[0], SpotObjectInteractedEvent)
        ]
        assert interacted == [], (
            "do_interact が SpotObjectInteractedEvent を積んでいる。"
            "witness_policy を持たない 2 件目が復活すると ACTOR_ONLY が貫通する。"
            f"events={interacted}"
        )

    def test_interact_success_runs_distant_cue_boundary_detection(self) -> None:
        """do_interact 成功後は、object state 変更で active 化した cue を即時検出する。"""
        rt = _fake_runtime()

        WorldRuntime.do_interact(rt, PlayerId(1), "shellfish_rocks", "gather_shellfish")

        rt._evaluate_distant_cue_appearances.assert_called_once()

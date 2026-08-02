"""WorldRuntime.do_listen が行動可能者だけを聴覚観測へ渡す試験。"""

from unittest.mock import MagicMock

from ai_rpg_world.application.world_runtime.world_runtime import WorldRuntime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


def test_do_listen_excludes_downed_players_and_returns_no_partial_count() -> None:
    """倒れた人を人数候補から除き、環境音だけの部分的な件数は返さない。"""
    runtime = object.__new__(WorldRuntime)
    graph = MagicMock()
    runtime._spot_graph_repo = MagicMock()
    runtime._spot_graph_repo.find_graph.return_value = graph

    active = MagicMock(player_id=PlayerId(2), is_down=False)
    downed = MagicMock(player_id=PlayerId(3), is_down=True)
    runtime._player_status_repo = MagicMock()
    runtime._player_status_repo.find_all.return_value = [active, downed]
    runtime._process_graph_events = MagicMock()

    result = runtime.do_listen(PlayerId(1))

    assert result is None
    graph.emit_listen_carefully.assert_called_once_with(
        EntityId.create(1), moving_entity_ids=frozenset({EntityId.create(2)}),
    )
    runtime._process_graph_events.assert_called_once_with()

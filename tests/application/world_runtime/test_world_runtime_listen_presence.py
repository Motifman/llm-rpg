"""WorldRuntime.do_listen が行動可能者だけを聴覚観測へ渡す試験。"""

from unittest.mock import MagicMock

from ai_rpg_world.application.world_runtime.world_runtime import WorldRuntime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotPresenceListenedEvent,
    SpotSoundHeardEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _sound_event() -> SpotSoundHeardEvent:
    return SpotSoundHeardEvent.create(
        aggregate_id=SpotGraphId.create(1),
        aggregate_type="SpotGraphAggregate",
        entity_id=EntityId.create(1),
        spot_id=SpotId.create(1),
        source_spot_id=SpotId.create(2),
        intensity="FAINT",
    )


def _presence_event() -> SpotPresenceListenedEvent:
    return SpotPresenceListenedEvent.create(
        aggregate_id=SpotGraphId.create(1),
        aggregate_type="SpotGraphAggregate",
        entity_id=EntityId.create(1),
        spot_id=SpotId.create(1),
        source_spot_id=SpotId.create(2),
        hops=1,
        moving_occupants=1,
    )


def test_do_listen_excludes_downed_players_and_keeps_sound_event_count() -> None:
    """倒れた人を人数候補から除き、戻り値は新しい環境音の件数だけにする。"""
    runtime = object.__new__(WorldRuntime)
    graph = MagicMock()
    stale_sound = _sound_event()
    graph.get_events.side_effect = [
        (stale_sound,),
        (stale_sound, _presence_event(), _sound_event()),
    ]
    runtime._spot_graph_repo = MagicMock()
    runtime._spot_graph_repo.find_graph.return_value = graph

    active = MagicMock(player_id=PlayerId(2), is_down=False)
    downed = MagicMock(player_id=PlayerId(3), is_down=True)
    runtime._player_status_repo = MagicMock()
    runtime._player_status_repo.find_all.return_value = [active, downed]
    runtime._process_graph_events = MagicMock()

    count = runtime.do_listen(PlayerId(1))

    assert count == 1
    graph.emit_listen_carefully.assert_called_once_with(
        EntityId.create(1), moving_entity_ids=frozenset({EntityId.create(2)}),
    )
    runtime._process_graph_events.assert_called_once_with()

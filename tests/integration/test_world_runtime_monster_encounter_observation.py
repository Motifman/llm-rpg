"""モンスターに初めて出会ったときの観測を runtime 経路で保証する。"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.runtime_config_helpers import runtime_config


_SCENARIO_PATH = Path("data/scenarios/survival_island_v4_coop.json")


def test_visible_monster_encounter_observation_is_emitted_only_once() -> None:
    """monster が見える spot に入ると遭遇観測が1回だけ入り、再表示では重複しない。"""
    runtime = create_world_runtime(_SCENARIO_PATH, config=runtime_config())
    player_id = runtime.get_player_ids()[0]
    graph = runtime._spot_graph_repo.find_graph()
    plane_wreck = SpotId.create(runtime.id_mapper.get_int("spot", "plane_wreck"))
    entity_id = EntityId.create(player_id.value)
    graph.unplace_entity(entity_id)
    graph.place_entity(entity_id, plane_wreck)

    first = runtime._state_builder.build_snapshot(player_id.value)
    assert first is not None
    first_entries = runtime._obs_buffer.get_observations(player_id)

    assert len(first_entries) == 1
    output = first_entries[0].output
    assert output.structured["type"] == "monster_encountered"
    assert output.structured["display_name"] == "廃拠点の野犬"
    assert "廃拠点の野犬が同じ場所にいることに気づいた" in output.prose
    assert "観測拠点の廃屋を縄張りにする獰猛な野犬" in output.prose
    assert output.schedules_turn is True

    second = runtime._state_builder.build_snapshot(player_id.value)
    assert second is not None
    second_entries = runtime._obs_buffer.get_observations(player_id)

    assert len(second_entries) == 1

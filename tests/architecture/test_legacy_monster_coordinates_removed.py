"""モンスター個体の配置がスポットとMonsterIdだけを受け取る境界を守る。"""

import inspect

from ai_rpg_world.application.world_graph.spot_graph_monster_spawn_stage_service import (
    MonsterSpawnSlot,
    SpotGraphMonsterSpawnStageService,
)
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.infrastructure.scenario.models import ScenarioMonsterPlacement
from ai_rpg_world.infrastructure.scenario.parse_actors import parse_monster_placement


def test_monster_placement_has_no_tile_coordinate_or_object_id():
    """集約と配置定義は、旧座標と世界物体IDを入力にも公開属性にも持たない。"""
    for method in (MonsterAggregate, MonsterAggregate.create, MonsterAggregate.reconstitute):
        assert (
            not {"coordinate", "world_object_id", "initial_spawn_coordinate"}
            & inspect.signature(method).parameters.keys()
        )
    for name in ("coordinate", "world_object_id", "get_respawn_coordinate", "update_map_placement", "record_evasion"):
        assert not hasattr(MonsterAggregate, name)
    assert "coordinate" not in MonsterSpawnSlot.__dataclass_fields__
    assert not {"coordinate_x", "coordinate_y", "coordinate_z"} & ScenarioMonsterPlacement.__dataclass_fields__.keys()


def test_monster_repository_and_spawn_do_not_allocate_world_object_ids():
    """配置サービスに旧IDの採番口はなく、保存先も世界物体IDでモンスターを検索しない。"""
    assert "world_object_id_factory" not in inspect.signature(SpotGraphMonsterSpawnStageService).parameters
    assert not hasattr(MonsterRepository, "find_by_world_object_id")
    assert not hasattr(MonsterRepository, "generate_world_object_id_for_npc")


def test_old_placement_coordinates_are_ignored():
    """旧シナリオにcoordinateがあっても読まず、テンプレートとスポットだけで配置する。"""
    placement = parse_monster_placement({"template": "wolf", "spot": "forest", "coordinate": {"x": 42}}, 0)
    assert placement == ScenarioMonsterPlacement(template_string_id="wolf", spot_string_id="forest")

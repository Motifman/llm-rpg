"""station_drill の停電前提を、初期照明に依存せず試験へ作る補助。"""

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum


def darken_spot(runtime, spot_name: str = "corridor") -> None:
    """指定した部屋を停電させ、暗所に関する試験の前提を明示する。"""
    graph = runtime._spot_graph_repo.find_graph()
    graph.update_spot_atmosphere(
        SpotId.create(runtime.id_mapper.get_int("spot", spot_name)),
        lighting=LightingEnum.DARK,
    )
    runtime._spot_graph_repo.save(graph)

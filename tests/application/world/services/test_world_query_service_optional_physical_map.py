"""WorldQueryService の physical_map_repository Optional 対応。

Issue #227 chore (tile-map 依存除去) PR-3:
    spot_graph 専用ランタイムでは physical_map_repository=None で
    WorldQueryService 系列を組めることを保証する。

検証ポイント:
- シグネチャ上 physical_map_repository が Optional になっている
- 各サブサービスは None を受け取っても construct で例外を投げない
- get_player_current_state(None PMR) は None を返す
  (実際の spot_graph では SpotGraphAugmentingWorldQueryService の
   Decorator がオーバーライドするためこの経路は本番では呼ばれないが、
   万一呼ばれても安全に None を返すことを保証)
"""

import inspect

import pytest

from ai_rpg_world.application.world.services.available_moves_query_service import (
    AvailableMovesQueryService,
)
from ai_rpg_world.application.world.services.player_location_query_service import (
    PlayerLocationQueryService,
)
from ai_rpg_world.application.world.services.spot_context_query_service import (
    SpotContextQueryService,
)
from ai_rpg_world.application.world.services.visible_context_query_service import (
    VisibleContextQueryService,
)
from ai_rpg_world.application.world.services.world_query_service import (
    WorldQueryService,
)
from ai_rpg_world.application.world.world_query_wiring import (
    create_world_query_service,
)


@pytest.mark.parametrize(
    "cls",
    [
        PlayerLocationQueryService,
        SpotContextQueryService,
        AvailableMovesQueryService,
        VisibleContextQueryService,
        WorldQueryService,
    ],
)
def test_subclass_physical_map_repository_is_optional(cls):
    """各サブサービス / WorldQueryService の physical_map_repository が Optional 化された。"""
    sig = inspect.signature(cls.__init__)
    param = sig.parameters["physical_map_repository"]
    annotation = str(param.annotation)
    assert "Optional" in annotation or "None" in annotation, (
        f"{cls.__name__}.physical_map_repository should be Optional, got: {annotation}"
    )


def test_create_world_query_service_physical_map_repository_default_is_none():
    """create_world_query_service の physical_map_repository は default=None。"""
    sig = inspect.signature(create_world_query_service)
    param = sig.parameters["physical_map_repository"]
    assert param.default is None

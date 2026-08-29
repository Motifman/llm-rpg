"""interactionの公開更新入口が確定区間なしで旧repositoryへ戻らない契約。"""

from unittest.mock import Mock

import pytest

from ai_rpg_world.application.world_graph.player_interaction_application_service import (
    PlayerInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


def _untouchable(name: str) -> Mock:
    dependency = Mock(name=name)
    for method_name in (
        "find_graph",
        "find_by_id",
        "find_by_spot_id",
        "find_by_spec_id",
        "publish_all",
        "save",
    ):
        getattr(dependency, method_name).side_effect = AssertionError(
            f"{name}.{method_name} was touched"
        )
    return dependency


def _spot_service() -> tuple[SpotInteractionApplicationService, tuple[Mock, ...]]:
    dependencies = tuple(
        _untouchable(name)
        for name in ("graph", "interiors", "inventories", "items", "item_specs")
    )
    service = SpotInteractionApplicationService(
        spot_graph_repository=dependencies[0],
        spot_interior_repository=dependencies[1],
        player_inventory_repository=dependencies[2],
        item_repository=dependencies[3],
        item_spec_repository=dependencies[4],
        world_flag_state=MutableWorldFlagState(),
    )
    return service, dependencies


@pytest.mark.parametrize("entry", ("object", "item"))
def test_spot_interaction_updates_require_scope_before_repository_access(
    entry: str,
) -> None:
    """物体・道具操作はscope未配線ならrepositoryへ触れる前に拒否する。"""
    service, dependencies = _spot_service()

    with pytest.raises(RuntimeError, match="CommandScopeFactoryが未配線"):
        if entry == "object":
            service.execute_interaction(PlayerId(1), SpotObjectId.create(1), "use")
        else:
            service.execute_item_interaction(PlayerId(1), ItemSpecId.create(1), "use")

    assert all(dependency.mock_calls == [] for dependency in dependencies)


def test_player_interaction_update_requires_scope_before_repository_access() -> None:
    """対人操作はscope未配線ならrepositoryへ触れる前に拒否する。"""
    dependencies = tuple(
        _untouchable(name)
        for name in ("graph", "inventories", "items", "item_specs", "statuses")
    )
    interaction = Mock(action_name="help", effects=())
    service = PlayerInteractionApplicationService(
        spot_graph_repository=dependencies[0],
        player_inventory_repository=dependencies[1],
        item_repository=dependencies[2],
        item_spec_repository=dependencies[3],
        player_status_repository=dependencies[4],
        player_life_query=Mock(),
        fallen_body_registry=Mock(),
        world_flag_state=MutableWorldFlagState(),
        player_interactions=(interaction,),
    )

    with pytest.raises(RuntimeError, match="CommandScopeFactoryが未配線"):
        service.execute(PlayerId(1), PlayerId(2), "help")

    assert all(dependency.mock_calls == [] for dependency in dependencies)

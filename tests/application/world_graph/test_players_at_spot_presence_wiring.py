"""PLAYERS_AT_SPOT precondition が実人数で判定されることの配線テスト。

`SpotInteractionApplicationService.execute_interaction` は従来
`spot_presence_count` を domain service に渡しておらず、domain 側の既定値 1 が
常に使われていた。その結果 PLAYERS_AT_SPOT (「N 人がその場に居ないと実行
できない」) は**何人集まっても常に 1 人と判定され、要求 2 人以上の
interaction は構造的に実行不可能**だった (P12 協力シナリオの E2E で発覚した
静かな失敗)。本テストは app 層経由の実行で「1 人なら拒否 / 2 人なら成功」の
両方向を振る舞いとして固定する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import (
    InMemoryItemSpecRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)

ACTOR_ID = 1
PARTNER_ID = 2
SPOT_ID = 1
LEVER_OBJECT_ID = 10


def _build_app(*, partner_at_spot: bool):
    """PLAYERS_AT_SPOT (2 人) を要求するレバーと、actor (+任意で相方) を組む。"""
    lever_def = InteractionDef(
        action_name="pull_heavy_lever",
        display_label="重いレバーを二人で引く",
        preconditions=(
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.PLAYERS_AT_SPOT,
                required_player_count=2,
                failure_message="一人では動かない。もう一人必要だ。",
            ),
        ),
        effects=(
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.SET_FLAG,
                parameters={"flag_name": "lever_pulled"},
            ),
        ),
    )
    lever = SpotObject(
        object_id=SpotObjectId.create(LEVER_OBJECT_ID),
        name="heavy_lever",
        description="d",
        object_type=SpotObjectTypeEnum.SWITCH,
        state={},
        interactions=(lever_def,),
    )
    spot = SpotNode(
        spot_id=SpotId.create(SPOT_ID),
        name="engine_room",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(spot)
    graph.place_entity(EntityId.create(ACTOR_ID), SpotId.create(SPOT_ID))
    if partner_at_spot:
        graph.place_entity(EntityId.create(PARTNER_ID), SpotId.create(SPOT_ID))
    graph.clear_events()

    spot_graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository()
    interior_repo.save(SpotId.create(SPOT_ID), SpotInterior((), (lever,), (), ()))

    data_store = InMemoryDataStore()
    inventory_repo = InMemoryPlayerInventoryRepository(data_store)
    inventory_repo.save(PlayerInventoryAggregate(player_id=PlayerId(ACTOR_ID)))

    flags = MutableWorldFlagState()
    app = SpotInteractionApplicationService(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        player_inventory_repository=inventory_repo,
        item_repository=InMemoryItemRepository(data_store),
        item_spec_repository=InMemoryItemSpecRepository(),
        world_flag_state=flags,
        player_status_repository=InMemoryPlayerStatusRepository(data_store),
    )
    return app, flags


class TestPlayersAtSpotPresenceWiring:
    """PLAYERS_AT_SPOT が graph の実プレイヤー数で判定されることを保証する。"""

    def test_solo_actor_is_rejected(self) -> None:
        """スポットに actor 1 人だけのとき、2 人要求の interaction は
        InteractionNotAllowedException で拒否され、flag は立たない。"""
        app, flags = _build_app(partner_at_spot=False)
        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                PlayerId(ACTOR_ID),
                SpotObjectId.create(LEVER_OBJECT_ID),
                "pull_heavy_lever",
            )
        assert "lever_pulled" not in flags.as_frozen_set()

    def test_two_players_at_spot_succeed(self) -> None:
        """同じスポットに 2 人いれば実行でき、effect (SET_FLAG) が反映される。

        修正前はここが必ず失敗した (spot_presence_count が渡されず常に 1)。"""
        app, flags = _build_app(partner_at_spot=True)
        app.execute_interaction(
            PlayerId(ACTOR_ID),
            SpotObjectId.create(LEVER_OBJECT_ID),
            "pull_heavy_lever",
        )
        assert "lever_pulled" in flags.as_frozen_set()

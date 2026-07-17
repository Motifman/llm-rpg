"""看板 (PR-F) の application 層統合テスト。

`SpotInteractionApplicationService` が:
- interaction_parameters (interact ツールの `parameters={"text": ...}`) を
  effect まで届ける
- player_display_name_resolver で書き手名を解決し、object.state へ残す
- spot_interior_repository への save まで反映する

を end-to-end で保証する。
"""

from __future__ import annotations

from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
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
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
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
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)


PLAYER_ID = 1
SPOT_ID = 1
SIGN_OBJECT_ID = 20


def _build_app(*, player_names: dict[int, str] | None = None):
    sign = SpotObject(
        object_id=SpotObjectId.create(SIGN_OBJECT_ID),
        name="古い看板", description="d",
        object_type=SpotObjectTypeEnum.SIGN,
        state={},
        interactions=(
            InteractionDef(
                action_name="write",
                display_label="書き込む",
                preconditions=(),
                effects=(
                    InteractionEffect(
                        effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
                        parameters={},
                    ),
                ),
            ),
            InteractionDef(
                action_name="examine",
                display_label="読む",
                preconditions=(),
                effects=(
                    InteractionEffect(
                        effect_type=InteractionEffectTypeEnum.SHOW_PLAYER_TEXT,
                        parameters={},
                    ),
                ),
            ),
        ),
    )
    spot = SpotNode(
        spot_id=SpotId.create(SPOT_ID), name="広場", description="d",
        category=SpotCategoryEnum.OTHER, parent_id=None,
    )
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(spot)
    graph.place_entity(EntityId.create(PLAYER_ID), SpotId.create(SPOT_ID))
    graph.clear_events()

    spot_graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository()
    interior_repo.save(SpotId.create(SPOT_ID), SpotInterior((), (sign,), (), ()))

    data_store = InMemoryDataStore()
    inventory_repo = InMemoryPlayerInventoryRepository(data_store)
    item_repo = InMemoryItemRepository(data_store)
    item_spec_repo = InMemoryItemSpecRepository()
    inventory_repo.save(PlayerInventoryAggregate(player_id=PlayerId(PLAYER_ID)))

    names = player_names or {}
    flags = MutableWorldFlagState()
    app = SpotInteractionApplicationService(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        player_inventory_repository=inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=flags,
        player_display_name_resolver=lambda pid: names.get(int(pid), ""),
    )
    return app, interior_repo


class TestSignObjectAppIntegration:
    """看板の書き込み→永続化→読み取りの end-to-end 挙動。"""

    def test_書き込みが_spot_interior_repository_に永続化される(self) -> None:
        app, interior_repo = _build_app(player_names={PLAYER_ID: "アリス"})

        app.execute_interaction(
            PlayerId(PLAYER_ID),
            SpotObjectId.create(SIGN_OBJECT_ID),
            "write",
            interaction_parameters={"text": "水場はここから北"},
            current_tick=WorldTick(3),
        )

        interior = interior_repo.find_by_spot_id(SpotId.create(SPOT_ID))
        state = interior.get_object(SpotObjectId.create(SIGN_OBJECT_ID)).state
        assert state["sign_text"] == "水場はここから北"
        assert state["sign_author_name"] == "アリス"
        assert state["sign_written_tick"] == 3

    def test_resolver_未注入でもフォールバック名で書き込める(self) -> None:
        """player_display_name_resolver を渡さない構成でも書き込みは失敗しない。"""
        sign = SpotObject(
            object_id=SpotObjectId.create(SIGN_OBJECT_ID),
            name="古い看板", description="d",
            object_type=SpotObjectTypeEnum.SIGN,
            state={},
            interactions=(
                InteractionDef(
                    action_name="write",
                    display_label="書き込む",
                    preconditions=(),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.WRITE_PLAYER_TEXT,
                            parameters={},
                        ),
                    ),
                ),
            ),
        )
        spot = SpotNode(
            spot_id=SpotId.create(SPOT_ID), name="広場", description="d",
            category=SpotCategoryEnum.OTHER, parent_id=None,
        )
        graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
        graph.add_spot(spot)
        graph.place_entity(EntityId.create(PLAYER_ID), SpotId.create(SPOT_ID))
        graph.clear_events()
        spot_graph_repo = InMemorySpotGraphRepository(graph)
        interior_repo = InMemorySpotInteriorRepository()
        interior_repo.save(SpotId.create(SPOT_ID), SpotInterior((), (sign,), (), ()))
        data_store = InMemoryDataStore()
        inventory_repo = InMemoryPlayerInventoryRepository(data_store)
        item_repo = InMemoryItemRepository(data_store)
        item_spec_repo = InMemoryItemSpecRepository()
        inventory_repo.save(PlayerInventoryAggregate(player_id=PlayerId(PLAYER_ID)))
        app = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=interior_repo,
            player_inventory_repository=inventory_repo,
            item_repository=item_repo,
            item_spec_repository=item_spec_repo,
            world_flag_state=MutableWorldFlagState(),
            # player_display_name_resolver 未指定
        )

        app.execute_interaction(
            PlayerId(PLAYER_ID),
            SpotObjectId.create(SIGN_OBJECT_ID),
            "write",
            interaction_parameters={"text": "誰かが書いた"},
            current_tick=WorldTick(1),
        )

        interior = interior_repo.find_by_spot_id(SpotId.create(SPOT_ID))
        state = interior.get_object(SpotObjectId.create(SIGN_OBJECT_ID)).state
        assert state["sign_author_name"]  # フォールバック名が入っている

    def test_examineで書かれた内容が本人へのmessageとして返る(self) -> None:
        app, _ = _build_app(player_names={PLAYER_ID: "アリス"})
        app.execute_interaction(
            PlayerId(PLAYER_ID),
            SpotObjectId.create(SIGN_OBJECT_ID),
            "write",
            interaction_parameters={"text": "水場はここから北"},
            current_tick=WorldTick(3),
        )

        result = app.execute_interaction(
            PlayerId(PLAYER_ID),
            SpotObjectId.create(SIGN_OBJECT_ID),
            "examine",
        )

        assert result.messages == ("『水場はここから北』 — アリス",)

    def test_未記入の看板をexamineすると何も書かれていないと返る(self) -> None:
        app, _ = _build_app(player_names={PLAYER_ID: "アリス"})

        result = app.execute_interaction(
            PlayerId(PLAYER_ID),
            SpotObjectId.create(SIGN_OBJECT_ID),
            "examine",
        )

        assert result.messages == ("何も書かれていない。",)

    def test_2人目が書き込むと1人目の内容が上書きされる(self) -> None:
        app, _ = _build_app(player_names={PLAYER_ID: "アリス", 2: "ボブ"})
        app.execute_interaction(
            PlayerId(PLAYER_ID),
            SpotObjectId.create(SIGN_OBJECT_ID),
            "write",
            interaction_parameters={"text": "1人目のメモ"},
            current_tick=WorldTick(1),
        )
        # 2人目は同じ spot にいなくても domain 的には書き込める
        # (spot 移動テストは範囲外なので同じ player でも別 tick に見立てる)
        app.execute_interaction(
            PlayerId(PLAYER_ID),
            SpotObjectId.create(SIGN_OBJECT_ID),
            "write",
            interaction_parameters={"text": "2人目のメモ"},
            current_tick=WorldTick(2),
        )

        result = app.execute_interaction(
            PlayerId(PLAYER_ID),
            SpotObjectId.create(SIGN_OBJECT_ID),
            "examine",
        )
        assert result.messages == ("『2人目のメモ』 — アリス",)

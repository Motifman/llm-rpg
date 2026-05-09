"""Phase 4-D-2 PR 2: アプリ層配線 (player state save) の統合テスト。

`SpotInteractionApplicationService` が:
- player_status_repository から acting_player_status を load
- domain service に渡す
- `result.acting_player_state_changed=True` のときだけ save する
- precondition 拒否時は save が呼ばれない

を end-to-end で保証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
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


PLAYER_ID = 1
SPOT_ID = 1
ALTAR_OBJECT_ID = 10


def _build_app(
    *,
    player_initial_state: dict | None = None,
    interaction: InteractionDef,
):
    """player + 1 spot + 1 object (altar) を持つ最小ゲーム空間。"""
    altar = SpotObject(
        object_id=SpotObjectId.create(ALTAR_OBJECT_ID),
        name="altar", description="d",
        object_type=SpotObjectTypeEnum.OTHER,
        state={}, interactions=(interaction,),
    )
    spot = SpotNode(
        spot_id=SpotId.create(SPOT_ID), name="shrine", description="d",
        category=SpotCategoryEnum.OTHER, parent_id=None,
    )
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(spot)
    graph.place_entity(EntityId.create(PLAYER_ID), SpotId.create(SPOT_ID))
    graph.clear_events()

    spot_graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository()
    interior_repo.save(SpotId.create(SPOT_ID), SpotInterior((), (altar,), (), ()))

    data_store = InMemoryDataStore()
    status_repo = InMemoryPlayerStatusRepository(data_store)
    inventory_repo = InMemoryPlayerInventoryRepository(data_store)
    item_repo = InMemoryItemRepository(data_store)
    item_spec_repo = InMemoryItemSpecRepository()

    exp_table = ExpTable(100, 1.5)
    status = PlayerStatusAggregate(
        player_id=PlayerId(PLAYER_ID),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=100, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
        spot_navigation_state=PlayerSpotNavigationState.at_rest(SpotId.create(SPOT_ID)),
        state=player_initial_state,
    )
    status_repo.save(status)
    inventory_repo.save(PlayerInventoryAggregate(player_id=PlayerId(PLAYER_ID)))

    flags = MutableWorldFlagState()
    app = SpotInteractionApplicationService(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        player_inventory_repository=inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=flags,
        player_status_repository=status_repo,
    )
    return app, status_repo


class TestPlayerStateAppIntegration:
    """SpotInteractionApplicationService 経由の player.state 永続化動作。"""

    def test_change_player_state_persists_via_app_service(self) -> None:
        """CHANGE_PLAYER_STATE effect が app service 経由で永続化される。"""
        interaction = InteractionDef(
            action_name="touch_altar",
            display_label="祭壇に触れる",
            preconditions=(),
            effects=(
                InteractionEffect(
                    effect_type=InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
                    parameters={"state_updates": {"blessed": True}},
                ),
                InteractionEffect(
                    effect_type=InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK,
                    parameters={"state_key": "blessed_at_tick"},
                ),
            ),
        )
        app, status_repo = _build_app(interaction=interaction)

        app.execute_interaction(
            PlayerId(PLAYER_ID),
            SpotObjectId.create(ALTAR_OBJECT_ID),
            "touch_altar",
            current_tick=WorldTick(5),
        )

        # repository 経由で再読み込み → state が反映されている
        reloaded = status_repo.find_by_id(PlayerId(PLAYER_ID))
        assert reloaded is not None
        assert reloaded.state == {"blessed": True, "blessed_at_tick": 5}

    def test_player_state_is_precondition_blocks_interaction(self) -> None:
        """PLAYER_STATE_IS が一致しない場合 interaction が拒否される。"""
        interaction = InteractionDef(
            action_name="touch_altar",
            display_label="祭壇に触れる",
            preconditions=(
                InteractionCondition(
                    condition_type=InteractionConditionTypeEnum.PLAYER_STATE_IS,
                    required_state={"blessed": True},
                    failure_message="祝福を受けていない",
                ),
            ),
            effects=(),
        )
        # 初期 state は空 → blessed=True を満たさない
        app, status_repo = _build_app(interaction=interaction)

        with pytest.raises(InteractionNotAllowedException, match="祝福"):
            app.execute_interaction(
                PlayerId(PLAYER_ID),
                SpotObjectId.create(ALTAR_OBJECT_ID),
                "touch_altar",
            )

    def test_save_not_called_when_state_unchanged(self) -> None:
        """precondition 拒否などで state が変わらない場合、save は呼ばれない。"""
        interaction = InteractionDef(
            action_name="touch_altar",
            display_label="祭壇に触れる",
            preconditions=(
                InteractionCondition(
                    condition_type=InteractionConditionTypeEnum.PLAYER_STATE_IS,
                    required_state={"blessed": True},
                ),
            ),
            effects=(
                InteractionEffect(
                    effect_type=InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
                    parameters={"state_updates": {"x": 1}},
                ),
            ),
        )
        app, status_repo = _build_app(interaction=interaction)

        save_count = {"n": 0}
        original_save = status_repo.save

        def counting_save(s):
            save_count["n"] += 1
            return original_save(s)

        status_repo.save = counting_save  # type: ignore[assignment]

        # precondition 拒否
        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                PlayerId(PLAYER_ID),
                SpotObjectId.create(ALTAR_OBJECT_ID),
                "touch_altar",
            )
        assert save_count["n"] == 0

    def test_full_round_trip_change_then_match(self) -> None:
        """1 回目で CHANGE_PLAYER_STATE → 2 回目に PLAYER_STATE_IS で通過。"""
        # まず state を blessed=True にする interaction
        bless_interaction = InteractionDef(
            action_name="bless",
            display_label="祝福を授ける",
            preconditions=(),
            effects=(
                InteractionEffect(
                    effect_type=InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
                    parameters={"state_updates": {"blessed": True}},
                ),
            ),
        )
        # blessed=True を要求する interaction
        require_interaction = InteractionDef(
            action_name="enter_holy_zone",
            display_label="聖域に入る",
            preconditions=(
                InteractionCondition(
                    condition_type=InteractionConditionTypeEnum.PLAYER_STATE_IS,
                    required_state={"blessed": True},
                ),
            ),
            effects=(),
        )
        # 1 つの object に 2 アクション持たせる
        altar = SpotObject(
            object_id=SpotObjectId.create(ALTAR_OBJECT_ID),
            name="altar", description="d",
            object_type=SpotObjectTypeEnum.OTHER,
            state={}, interactions=(bless_interaction, require_interaction),
        )
        app, status_repo = _build_app(interaction=bless_interaction)
        # 上の helper は 1 interaction のみ受け付けるので、interior を直接置き換える
        # (test 専用 hack)
        from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior as _Int
        # 既存の interior を 2 アクションある altar で上書き
        # 実装簡略化: helper を回避して 2 interaction の altar を再保存
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId as _SpotId
        # InMemorySpotInteriorRepository は private 領域にアクセス
        interior_repo = app._spot_interior_repository  # type: ignore[attr-defined]
        interior_repo.save(_SpotId.create(SPOT_ID), _Int((), (altar,), (), ()))

        # 1 回目: blessed=False のままなので enter_holy_zone は拒否
        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                PlayerId(PLAYER_ID),
                SpotObjectId.create(ALTAR_OBJECT_ID),
                "enter_holy_zone",
            )

        # bless を実行 → state 更新
        app.execute_interaction(
            PlayerId(PLAYER_ID),
            SpotObjectId.create(ALTAR_OBJECT_ID),
            "bless",
        )
        assert status_repo.find_by_id(PlayerId(PLAYER_ID)).state == {"blessed": True}

        # 2 回目: 通る
        app.execute_interaction(
            PlayerId(PLAYER_ID),
            SpotObjectId.create(ALTAR_OBJECT_ID),
            "enter_holy_zone",
        )

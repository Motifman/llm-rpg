"""スポットグラフ アプリケーションサービスからのイベント発火テスト。

interaction / exploration がそれぞれ EventPublisher 経由で
ドメインイベントを発火することを検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.spot_exploration_application_service import (
    SpotExplorationApplicationService,
)
from ai_rpg_world.application.world_graph.spot_exploration_progress_store import (
    InMemorySpotExplorationProgressStore,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotExploredEvent,
    SpotObjectInteractedEvent,
    SpotObjectStateChangedEvent,
    SpotPlayerStateChangedInSpotEvent,
    SpotPublicEffectObservedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum


def _build_graph_with_entity(spot_id: SpotId, entity_id: EntityId) -> SpotGraphAggregate:
    """エンティティが1つのスポットに配置されたグラフを構築する。"""
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    node = SpotNode(spot_id=spot_id, name="テスト部屋", description="テスト用", category=SpotCategoryEnum.DUNGEON, parent_id=None)
    graph.add_spot(node)
    graph.place_entity(entity_id, spot_id)
    graph.clear_events()  # 配置イベントをクリア
    return graph


def _simple_object() -> SpotObject:
    """メッセージ表示のみのシンプルなオブジェクト"""
    return SpotObject(
        object_id=SpotObjectId.create(10),
        name="石碑",
        description="古い文字が刻まれている",
        object_type=SpotObjectTypeEnum.SIGN,
        state={},
        interactions=(
            InteractionDef(
                action_name="read",
                display_label="読む",
                preconditions=(),
                effects=(
                    InteractionEffect(
                        effect_type=InteractionEffectTypeEnum.SHOW_MESSAGE,
                        parameters={"message": "古代文字が書かれている"},
                    ),
                ),
            ),
        ),
    )


def _make_interior(obj: SpotObject) -> SpotInterior:
    return SpotInterior((), (obj,), (), ())


class TestInteractionEventPublication:
    """SpotInteractionApplicationService のイベント発火テスト"""

    def test_publishes_spot_object_interacted_event(self):
        """操作完了時に SpotObjectInteractedEvent が publish される"""
        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        interior = _make_interior(_simple_object())

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None
        item_spec_repo = MagicMock()
        event_publisher = MagicMock()

        svc = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=item_spec_repo,
            world_flag_state=MutableWorldFlagState(),
            event_publisher=event_publisher,
        )

        result = svc.execute_interaction(player_id, SpotObjectId.create(10), "read")

        # publish_all が呼ばれたことを確認
        event_publisher.publish_all.assert_called_once()
        published_events = event_publisher.publish_all.call_args[0][0]

        # SpotObjectInteractedEvent が含まれること
        interacted = [e for e in published_events if isinstance(e, SpotObjectInteractedEvent)]
        assert len(interacted) == 1
        assert interacted[0].entity_id == entity_id
        assert interacted[0].spot_id == spot_id
        assert interacted[0].object_id == SpotObjectId.create(10)
        assert interacted[0].action_name == "read"

    def test_publishes_object_state_changed_event_with_actor_excluded(self):
        """Phase 4-E: PUBLIC_OBSERVABLE な CHANGE_OBJECT_STATE で
        SpotObjectStateChangedEvent が actor_entity_id 付きで発火する。"""
        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        # 火を点ける interaction を持つ燭台
        candle = SpotObject(
            object_id=SpotObjectId.create(20),
            name="燭台",
            description="蝋燭立て",
            object_type=SpotObjectTypeEnum.OTHER,
            state={"lit": False},
            interactions=(
                InteractionDef(
                    action_name="light",
                    display_label="火を点ける",
                    preconditions=(),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.CHANGE_OBJECT_STATE,
                            parameters={
                                "state_updates": {"lit": True},
                                "object_id": 20,
                            },
                        ),
                    ),
                ),
            ),
        )
        interior = _make_interior(candle)

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None
        event_publisher = MagicMock()

        svc = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=MagicMock(),
            world_flag_state=MutableWorldFlagState(),
            event_publisher=event_publisher,
        )

        svc.execute_interaction(player_id, SpotObjectId.create(20), "light")

        published = event_publisher.publish_all.call_args[0][0]
        state_events = [e for e in published if isinstance(e, SpotObjectStateChangedEvent)]
        assert len(state_events) == 1
        ev = state_events[0]
        # actor_entity_id が埋まっていれば recipient strategy 側で actor を除外できる
        assert ev.actor_entity_id == entity_id
        # state_delta に変更箇所が乗っている
        delta_keys = [d.key for d in ev.state_delta]
        assert "lit" in delta_keys

    def test_hidden_player_state_change_does_not_publish_event(self):
        """Phase 4-E: HIDDEN な CHANGE_PLAYER_STATE は観測 event を発火しない。"""
        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        poison_pricker = SpotObject(
            object_id=SpotObjectId.create(30),
            name="毒針",
            description="刺すと毒が回る",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(
                InteractionDef(
                    action_name="prick",
                    display_label="刺す",
                    preconditions=(),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
                            parameters={"state_updates": {"poisoned": True}},
                            # visibility 未指定 → HIDDEN がデフォルト
                        ),
                    ),
                ),
            ),
        )
        interior = _make_interior(poison_pricker)

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None

        # PlayerStatusAggregate を mock で用意 (state を持つ)
        player_status = MagicMock()
        player_status.state = {}
        player_status.merge_state = lambda updates: player_status.state.update(updates)
        player_status_repo = MagicMock()
        player_status_repo.find_by_id.return_value = player_status

        event_publisher = MagicMock()

        svc = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=MagicMock(),
            world_flag_state=MutableWorldFlagState(),
            player_status_repository=player_status_repo,
            event_publisher=event_publisher,
        )

        svc.execute_interaction(player_id, SpotObjectId.create(30), "prick")

        published = event_publisher.publish_all.call_args[0][0]
        # HIDDEN な変化なので SpotPlayerStateChangedInSpotEvent は出ない
        assert not any(isinstance(e, SpotPlayerStateChangedInSpotEvent) for e in published)
        # SpotObjectStateChangedEvent も発火しない (state_updates は player に対するもの)
        state_events = [e for e in published if isinstance(e, SpotObjectStateChangedEvent)]
        assert state_events == []

    def test_publishes_player_state_changed_when_visibility_is_public(self):
        """Phase 4-E: PUBLIC_OBSERVABLE 上書きで CHANGE_PLAYER_STATE が
        SpotPlayerStateChangedInSpotEvent を発火する (姿勢・変装などの想定)。"""
        from ai_rpg_world.domain.world_graph.enum.effect_visibility import (
            EffectVisibility,
        )

        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        # 変装が解けるトリガー
        trigger = SpotObject(
            object_id=SpotObjectId.create(40),
            name="鏡",
            description="姿が映る",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(
                InteractionDef(
                    action_name="reveal",
                    display_label="姿を見る",
                    preconditions=(),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
                            parameters={"state_updates": {"disguised": False}},
                            visibility=EffectVisibility.PUBLIC_OBSERVABLE,
                        ),
                    ),
                ),
            ),
        )
        interior = _make_interior(trigger)

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None

        player_status = MagicMock()
        player_status.state = {"disguised": True}
        player_status.merge_state = lambda updates: player_status.state.update(updates)
        player_status_repo = MagicMock()
        player_status_repo.find_by_id.return_value = player_status

        event_publisher = MagicMock()

        svc = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=MagicMock(),
            world_flag_state=MutableWorldFlagState(),
            player_status_repository=player_status_repo,
            event_publisher=event_publisher,
        )

        svc.execute_interaction(player_id, SpotObjectId.create(40), "reveal")

        published = event_publisher.publish_all.call_args[0][0]
        player_events = [
            e for e in published if isinstance(e, SpotPlayerStateChangedInSpotEvent)
        ]
        assert len(player_events) == 1
        ev = player_events[0]
        assert ev.entity_id == entity_id
        assert any(d.key == "disguised" and d.after is False for d in ev.state_delta)
        # observation_message は空にして formatter に delta_text を組み立てさせる
        assert ev.observation_message == ""

    def test_actor_direct_effects_returned_via_dto_not_event(self):
        """Phase 4-E: ACTOR_DIRECT は SpotInteractionResultDto.direct_effects 経由で
        行為者本人にだけ届き、観測 event にはならない (二重観測防止)。"""
        from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
            AppliedEffectKind,
        )

        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        # 食事で空腹回復 → SATISFY_NEED は ACTOR_DIRECT デフォルト
        meal = SpotObject(
            object_id=SpotObjectId.create(50),
            name="パン",
            description="食料",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(
                InteractionDef(
                    action_name="eat",
                    display_label="食べる",
                    preconditions=(),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.SATISFY_NEED,
                            parameters={"need_type": "HUNGER", "amount": 5},
                        ),
                    ),
                ),
            ),
        )
        interior = _make_interior(meal)

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None
        # SATISFY_NEED は player_status を必要とする
        player_status = MagicMock()
        player_status.satisfy_need = MagicMock()
        player_status.state = {}
        player_status_repo = MagicMock()
        player_status_repo.find_by_id.return_value = player_status
        event_publisher = MagicMock()

        svc = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=MagicMock(),
            world_flag_state=MutableWorldFlagState(),
            player_status_repository=player_status_repo,
            event_publisher=event_publisher,
        )

        result = svc.execute_interaction(player_id, SpotObjectId.create(50), "eat")

        # 行為者本人は direct_effects 経由でサマリを受け取る
        kinds = [e.kind for e in result.direct_effects]
        assert AppliedEffectKind.SATISFY_NEED in kinds

        # 観測 event 側には ACTOR_DIRECT のサマリは流れない
        published = event_publisher.publish_all.call_args[0][0]
        # SATISFY_NEED 用の観測 event はそもそも定義していない (PR2 範囲外)。
        # 念のため SpotObjectStateChangedEvent / SpotPlayerStateChangedInSpotEvent も無いことを確認
        assert not any(isinstance(e, SpotObjectStateChangedEvent) for e in published)
        assert not any(isinstance(e, SpotPlayerStateChangedInSpotEvent) for e in published)

    def test_publishes_public_effect_observed_for_damage(self):
        """Phase 4-E PR 3: APPLY_DAMAGE (PUBLIC_OBSERVABLE デフォルト) は
        SpotPublicEffectObservedEvent kind=DAMAGE で publish される。"""
        from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
            AppliedEffectKind,
        )

        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        spike = SpotObject(
            object_id=SpotObjectId.create(70),
            name="罠",
            description="鋭い棘",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(
                InteractionDef(
                    action_name="step",
                    display_label="踏む",
                    preconditions=(),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.APPLY_DAMAGE,
                            parameters={"damage": 7, "message": "棘に刺さった"},
                        ),
                    ),
                ),
            ),
        )
        interior = _make_interior(spike)

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None
        event_publisher = MagicMock()

        svc = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=MagicMock(),
            world_flag_state=MutableWorldFlagState(),
            event_publisher=event_publisher,
        )

        svc.execute_interaction(player_id, SpotObjectId.create(70), "step")

        published = event_publisher.publish_all.call_args[0][0]
        public_events = [
            e for e in published if isinstance(e, SpotPublicEffectObservedEvent)
        ]
        assert len(public_events) == 1
        ev = public_events[0]
        assert ev.kind == AppliedEffectKind.DAMAGE
        assert ev.actor_entity_id == entity_id

    def test_publishes_public_effect_observed_for_atmosphere(self):
        """Phase 4-E PR 3: CHANGE_ATMOSPHERE は SpotPublicEffectObservedEvent
        kind=ATMOSPHERE_UPDATE で publish される。"""
        from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
            AppliedEffectKind,
        )

        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        switch = SpotObject(
            object_id=SpotObjectId.create(80),
            name="照明スイッチ",
            description="部屋の照明を切る",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(
                InteractionDef(
                    action_name="off",
                    display_label="消す",
                    preconditions=(),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.CHANGE_ATMOSPHERE,
                            parameters={"spot_id": 1, "lighting": "DARK"},
                        ),
                    ),
                ),
            ),
        )
        interior = _make_interior(switch)

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None
        event_publisher = MagicMock()

        svc = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=MagicMock(),
            world_flag_state=MutableWorldFlagState(),
            event_publisher=event_publisher,
        )

        svc.execute_interaction(player_id, SpotObjectId.create(80), "off")

        published = event_publisher.publish_all.call_args[0][0]
        public_events = [
            e for e in published if isinstance(e, SpotPublicEffectObservedEvent)
        ]
        assert len(public_events) == 1
        assert public_events[0].kind == AppliedEffectKind.ATMOSPHERE_UPDATE

    def test_publishes_public_effect_observed_for_status_effect_when_public(self):
        """STATUS_EFFECT は既定 ACTOR_DIRECT だが、PUBLIC_OBSERVABLE 上書きで
        SpotPublicEffectObservedEvent kind=STATUS_EFFECT が発火する。"""
        from ai_rpg_world.domain.world_graph.enum.effect_visibility import (
            EffectVisibility,
        )
        from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
            AppliedEffectKind,
        )

        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        paralysis_trap = SpotObject(
            object_id=SpotObjectId.create(90),
            name="麻痺ガス",
            description="動けなくなる",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(
                InteractionDef(
                    action_name="touch",
                    display_label="触れる",
                    preconditions=(),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.APPLY_STATUS_EFFECT,
                            parameters={
                                "status_effect_type": "PARALYSIS",
                                "value": 1.0,
                                "duration_ticks": 30,
                            },
                            visibility=EffectVisibility.PUBLIC_OBSERVABLE,
                        ),
                    ),
                ),
            ),
        )
        interior = _make_interior(paralysis_trap)

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None
        event_publisher = MagicMock()

        svc = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=MagicMock(),
            world_flag_state=MutableWorldFlagState(),
            event_publisher=event_publisher,
        )

        svc.execute_interaction(player_id, SpotObjectId.create(90), "touch")

        published = event_publisher.publish_all.call_args[0][0]
        public_events = [
            e for e in published if isinstance(e, SpotPublicEffectObservedEvent)
        ]
        assert any(e.kind == AppliedEffectKind.STATUS_EFFECT for e in public_events)

    def test_publishes_public_effect_observed_for_satisfy_need_when_public(self):
        """SATISFY_NEED も PUBLIC_OBSERVABLE 上書きで観測 event が出る
        (例: 派手に飲み食いする様子が他人に見える)。"""
        from ai_rpg_world.domain.world_graph.enum.effect_visibility import (
            EffectVisibility,
        )
        from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
            AppliedEffectKind,
        )

        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        feast = SpotObject(
            object_id=SpotObjectId.create(91),
            name="ごちそう",
            description="豪華な料理",
            object_type=SpotObjectTypeEnum.OTHER,
            state={},
            interactions=(
                InteractionDef(
                    action_name="feast",
                    display_label="食らう",
                    preconditions=(),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.SATISFY_NEED,
                            parameters={"need_type": "HUNGER", "amount": 50},
                            visibility=EffectVisibility.PUBLIC_OBSERVABLE,
                        ),
                    ),
                ),
            ),
        )
        interior = _make_interior(feast)

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None
        player_status = MagicMock()
        player_status.satisfy_need = MagicMock()
        player_status.state = {}
        player_status_repo = MagicMock()
        player_status_repo.find_by_id.return_value = player_status
        event_publisher = MagicMock()

        svc = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=MagicMock(),
            world_flag_state=MutableWorldFlagState(),
            player_status_repository=player_status_repo,
            event_publisher=event_publisher,
        )

        svc.execute_interaction(player_id, SpotObjectId.create(91), "feast")

        published = event_publisher.publish_all.call_args[0][0]
        public_events = [
            e for e in published if isinstance(e, SpotPublicEffectObservedEvent)
        ]
        assert any(e.kind == AppliedEffectKind.SATISFY_NEED for e in public_events)

    def test_no_event_when_publisher_is_none(self):
        """event_publisher=None でもエラーにならない（後方互換）"""
        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        interior = _make_interior(_simple_object())

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None

        svc = SpotInteractionApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=MagicMock(),
            world_flag_state=MutableWorldFlagState(),
            # event_publisher=None (デフォルト)
        )

        # エラーにならないこと
        result = svc.execute_interaction(player_id, SpotObjectId.create(10), "read")
        assert result.messages


class TestExplorationEventPublication:
    """SpotExplorationApplicationService のイベント発火テスト"""

    def test_publishes_spot_explored_event(self):
        """探索完了時に SpotExploredEvent が publish される"""
        spot_id = SpotId.create(1)
        player_id = PlayerId(1)
        entity_id = EntityId.create(1)
        graph = _build_graph_with_entity(spot_id, entity_id)
        interior = _make_interior(_simple_object())

        spot_graph_repo = MagicMock()
        spot_graph_repo.find_graph.return_value = graph
        spot_interior_repo = MagicMock()
        spot_interior_repo.find_by_spot_id.return_value = interior
        inv = PlayerInventoryAggregate(player_id=player_id)
        player_inv_repo = MagicMock()
        player_inv_repo.find_by_id.return_value = inv
        item_repo = MagicMock()
        item_repo.find_by_id.return_value = None
        event_publisher = MagicMock()

        svc = SpotExplorationApplicationService(
            spot_graph_repository=spot_graph_repo,
            spot_interior_repository=spot_interior_repo,
            player_inventory_repository=player_inv_repo,
            item_repository=item_repo,
            item_spec_repository=MagicMock(),
            world_flag_state=MutableWorldFlagState(),
            exploration_progress_store=InMemorySpotExplorationProgressStore(),
            event_publisher=event_publisher,
        )

        result = svc.explore_once(player_id)

        event_publisher.publish.assert_called_once()
        event = event_publisher.publish.call_args[0][0]
        assert isinstance(event, SpotExploredEvent)
        assert event.entity_id == entity_id
        assert event.spot_id == spot_id

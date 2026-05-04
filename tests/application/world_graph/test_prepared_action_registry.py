"""PreparedActionRegistry と PREPARED_ACTION 条件評価のテスト。

協力アクションの「準備→実行」パターンが正しく動作することを検証する。
"""

from __future__ import annotations

from ai_rpg_world.application.world_graph.prepared_action_registry import PreparedActionRegistry
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import SpotInteractionService
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


class TestPreparedActionRegistry:
    """PreparedActionRegistry のユニットテスト"""

    def test_prepare_sets_flag(self) -> None:
        """prepare() でフラグがセットされること"""
        state = MutableWorldFlagState()
        registry = PreparedActionRegistry(state)
        flag = registry.prepare(player_id=1, action_id="hold_door")
        assert flag == "prepared:hold_door:1"
        assert "prepared:hold_door:1" in state.as_frozen_set()

    def test_cancel_removes_flag(self) -> None:
        """cancel() でフラグが除去されること"""
        state = MutableWorldFlagState()
        registry = PreparedActionRegistry(state)
        registry.prepare(player_id=1, action_id="hold_door")
        registry.cancel(player_id=1, action_id="hold_door")
        assert "prepared:hold_door:1" not in state.as_frozen_set()

    def test_cancel_all_for_player(self) -> None:
        """cancel_all_for_player() で指定プレイヤーの全準備が除去されること"""
        state = MutableWorldFlagState()
        registry = PreparedActionRegistry(state)
        registry.prepare(player_id=1, action_id="hold_door")
        registry.prepare(player_id=1, action_id="push_lever")
        registry.prepare(player_id=2, action_id="hold_door")
        registry.cancel_all_for_player(player_id=1)
        flags = state.as_frozen_set()
        assert "prepared:hold_door:1" not in flags
        assert "prepared:push_lever:1" not in flags
        assert "prepared:hold_door:2" in flags  # player 2は残る

    def test_consume_returns_player_id_and_removes(self) -> None:
        """consume() で準備したplayer_idが返り、フラグが除去されること"""
        state = MutableWorldFlagState()
        registry = PreparedActionRegistry(state)
        registry.prepare(player_id=1, action_id="hold_door")
        pid = registry.consume(action_id="hold_door")
        assert pid == 1
        assert "prepared:hold_door:1" not in state.as_frozen_set()

    def test_consume_returns_none_if_not_prepared(self) -> None:
        """prepare されていないaction_idに対してconsumeはNoneを返すこと"""
        state = MutableWorldFlagState()
        registry = PreparedActionRegistry(state)
        pid = registry.consume(action_id="unknown")
        assert pid is None

    def test_action_id_with_colon_raises(self) -> None:
        """action_idにコロンを含む場合ValueErrorが発生すること"""
        state = MutableWorldFlagState()
        registry = PreparedActionRegistry(state)
        import pytest
        with pytest.raises(ValueError, match="must not contain ':'"):
            registry.prepare(player_id=1, action_id="a:b")

    def test_is_prepared_static_check(self) -> None:
        """is_prepared() がフラグセットから準備済みかを判定できること"""
        flags = frozenset({"prepared:lever:1", "other_flag"})
        assert PreparedActionRegistry.is_prepared("lever", flags) is True
        assert PreparedActionRegistry.is_prepared("unknown", flags) is False


class TestPreparedActionConditionEvaluation:
    """PREPARED_ACTION 条件と SpotInteractionService の統合テスト"""

    def _cooperative_door(self) -> SpotObject:
        """PREPARED_ACTION 条件付きのドアオブジェクト"""
        return SpotObject(
            object_id=SpotObjectId.create(1),
            name="Heavy Door",
            description="重い扉。一人では開けられない。",
            object_type=SpotObjectTypeEnum.DOOR,
            state={"open": False},
            interactions=(
                InteractionDef(
                    action_name="open",
                    display_label="開ける",
                    preconditions=(
                        InteractionCondition(
                            condition_type=InteractionConditionTypeEnum.PREPARED_ACTION,
                            prepared_action_id="hold_door",
                            failure_message="誰かがドアを支えていないと開けられない。",
                        ),
                    ),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.CHANGE_OBJECT_STATE,
                            parameters={"state_updates": {"open": True}},
                        ),
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.SHOW_MESSAGE,
                            parameters={"message": "協力してドアを開けた！"},
                        ),
                    ),
                ),
            ),
        )

    def test_interaction_fails_without_preparation(self) -> None:
        """準備なしでは協力アクションが失敗すること"""
        svc = SpotInteractionService()
        door = self._cooperative_door()
        idef = svc.find_interaction(door, "open")
        assert idef is not None
        ok, msg = svc.can_interact(idef, door, frozenset(), frozenset())
        assert ok is False
        assert "支えていない" in (msg or "")

    def test_interaction_succeeds_with_preparation(self) -> None:
        """他プレイヤーが準備済みなら協力アクションが成功すること"""
        svc = SpotInteractionService()
        door = self._cooperative_door()
        idef = svc.find_interaction(door, "open")
        assert idef is not None
        flags = frozenset({"prepared:hold_door:1"})
        ok, msg = svc.can_interact(idef, door, frozenset(), flags)
        assert ok is True

    def test_full_cooperation_flow(self) -> None:
        """準備→実行の全フロー: フラグセット→条件クリア→操作実行"""
        state = MutableWorldFlagState()
        registry = PreparedActionRegistry(state)
        # Player 1 が準備
        registry.prepare(player_id=1, action_id="hold_door")
        # Player 2 が操作
        svc = SpotInteractionService()
        door = self._cooperative_door()
        interior = SpotInterior((), (door,), (), ())
        result = svc.execute_interaction(
            interior,
            SpotObjectId.create(1),
            "open",
            frozenset(),
            state.as_frozen_set(),
        )
        assert "協力してドアを開けた" in " ".join(result.messages)


class TestPlayersAtSpotCondition:
    """PLAYERS_AT_SPOT 条件のテスト"""

    def _multi_player_switch(self) -> SpotObject:
        return SpotObject(
            object_id=SpotObjectId.create(2),
            name="Heavy Switch",
            description="2人で押す必要がある。",
            object_type=SpotObjectTypeEnum.SWITCH,
            state={},
            interactions=(
                InteractionDef(
                    action_name="push",
                    display_label="押す",
                    preconditions=(
                        InteractionCondition(
                            condition_type=InteractionConditionTypeEnum.PLAYERS_AT_SPOT,
                            required_player_count=2,
                            failure_message="2人以上で押す必要がある。",
                        ),
                    ),
                    effects=(
                        InteractionEffect(
                            effect_type=InteractionEffectTypeEnum.SET_FLAG,
                            parameters={"flag_name": "switch_pressed"},
                        ),
                    ),
                ),
            ),
        )

    def test_fails_with_one_player(self) -> None:
        """1人では PLAYERS_AT_SPOT=2 の条件を満たさないこと"""
        svc = SpotInteractionService()
        sw = self._multi_player_switch()
        idef = svc.find_interaction(sw, "push")
        assert idef is not None
        ok, msg = svc.can_interact(
            idef, sw, frozenset(), frozenset(), spot_presence_count=1
        )
        assert ok is False
        assert "2人" in (msg or "")

    def test_succeeds_with_two_players(self) -> None:
        """2人いれば PLAYERS_AT_SPOT=2 の条件を満たすこと"""
        svc = SpotInteractionService()
        sw = self._multi_player_switch()
        idef = svc.find_interaction(sw, "push")
        assert idef is not None
        ok, msg = svc.can_interact(
            idef, sw, frozenset(), frozenset(), spot_presence_count=2
        )
        assert ok is True

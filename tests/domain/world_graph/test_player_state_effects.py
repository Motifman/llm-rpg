"""Phase 4-D-2 PR 2: プレイヤーの自由 state を操作する effect / precondition のテスト。

PR #118 で `PlayerStatusAggregate.state` を導入したが、シナリオ作家から
扱う DSL 表面が無かった。本 PR で 3 種を追加:

- `CHANGE_PLAYER_STATE` effect — state に部分マージ
- `RECORD_PLAYER_STATE_TICK` effect — current_tick を state[key] に書く
- `PLAYER_STATE_IS` precondition — state を判定

silent failure ガードは Phase 4-A/B/D-1 と同方針 (acting_player_status
未提供で warn + no-op、precondition は False で拒否)。
"""

from __future__ import annotations

import logging

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
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
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _player_status(state: dict | None = None) -> PlayerStatusAggregate:
    """テスト用に最小限の PlayerStatusAggregate を作る。"""
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=100, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
        state=state,
    )


def _empty_interior() -> SpotInterior:
    return SpotInterior((), (), (), ())


def _switch_object() -> SpotObject:
    return SpotObject(
        object_id=SpotObjectId.create(1),
        name="switch",
        description="d",
        object_type=SpotObjectTypeEnum.OTHER,
        state={},
        interactions=(),
    )


def _interaction_with(cond: InteractionCondition) -> InteractionDef:
    return InteractionDef(
        action_name="x",
        display_label="X",
        preconditions=(cond,),
        effects=(),
    )


class TestChangePlayerStateEffect:
    """CHANGE_PLAYER_STATE の挙動。"""

    def test_merges_state_updates_into_acting_player(self) -> None:
        """state_updates が acting_player_status にマージされる。"""
        svc = WorldGraphEffectService()
        status = _player_status(state={"alignment": "good"})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
            parameters={"state_updates": {"poisoned": True, "intensity": "mild"}},
        )
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
            acting_player_status=status,
        )
        # 既存の alignment は保持、新規 2 キーが追加
        assert status.state == {
            "alignment": "good", "poisoned": True, "intensity": "mild",
        }
        assert result.acting_player_state_changed is True

    def test_no_op_and_warn_when_status_is_none(self, caplog) -> None:
        """acting_player_status を渡さないと警告ログ + no-op。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
            parameters={"state_updates": {"poisoned": True}},
        )
        with caplog.at_level(logging.WARNING):
            result = svc.apply_effects(
                interior=_empty_interior(), acting_object=None,
                effects=[effect], world_flags=frozenset(),
                # acting_player_status を渡さない
            )
        assert result.acting_player_state_changed is False
        assert any("acting_player_status" in r.message for r in caplog.records)

    def test_no_op_when_state_updates_not_dict(self, caplog) -> None:
        """state_updates が dict 以外なら警告 + no-op。"""
        svc = WorldGraphEffectService()
        status = _player_status(state={"alignment": "good"})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
            parameters={"state_updates": "alignment=evil"},  # 不正
        )
        with caplog.at_level(logging.WARNING):
            svc.apply_effects(
                interior=_empty_interior(), acting_object=None,
                effects=[effect], world_flags=frozenset(),
                acting_player_status=status,
            )
        # state は元のまま
        assert status.state == {"alignment": "good"}


class TestRecordPlayerStateTickEffect:
    """RECORD_PLAYER_STATE_TICK の挙動。"""

    def test_writes_current_tick_into_player_state(self) -> None:
        """current_tick.value が player.state[state_key] に書き込まれる。"""
        svc = WorldGraphEffectService()
        status = _player_status(state={"poisoned": True})
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK,
            parameters={"state_key": "poisoned_at_tick"},
        )
        svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=[effect], world_flags=frozenset(),
            current_tick=WorldTick(42),
            acting_player_status=status,
        )
        assert status.state == {"poisoned": True, "poisoned_at_tick": 42}

    def test_no_op_when_status_missing(self, caplog) -> None:
        """acting_player_status が None なら警告 + no-op。"""
        svc = WorldGraphEffectService()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK,
            parameters={"state_key": "x"},
        )
        with caplog.at_level(logging.WARNING):
            result = svc.apply_effects(
                interior=_empty_interior(), acting_object=None,
                effects=[effect], world_flags=frozenset(),
                current_tick=WorldTick(1),
            )
        assert result.acting_player_state_changed is False

    def test_no_op_when_current_tick_missing(self, caplog) -> None:
        """current_tick が None なら警告 + no-op。"""
        svc = WorldGraphEffectService()
        status = _player_status()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK,
            parameters={"state_key": "x"},
        )
        with caplog.at_level(logging.WARNING):
            svc.apply_effects(
                interior=_empty_interior(), acting_object=None,
                effects=[effect], world_flags=frozenset(),
                acting_player_status=status,
            )
        assert status.state == {}

    def test_no_op_when_state_key_missing(self, caplog) -> None:
        """state_key が無ければ警告 + no-op。"""
        svc = WorldGraphEffectService()
        status = _player_status()
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK,
            parameters={},
        )
        with caplog.at_level(logging.WARNING):
            svc.apply_effects(
                interior=_empty_interior(), acting_object=None,
                effects=[effect], world_flags=frozenset(),
                current_tick=WorldTick(1),
                acting_player_status=status,
            )
        assert status.state == {}


class TestPlayerStateIsPrecondition:
    """PLAYER_STATE_IS の挙動。"""

    def test_passes_when_state_matches(self) -> None:
        """player.state が required_state と一致なら成立。"""
        svc = SpotInteractionService()
        status = _player_status(state={"disguise": "noble", "fire_resist": True})
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_STATE_IS,
            required_state={"disguise": "noble"},
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is True

    def test_fails_when_state_differs(self) -> None:
        """state が一致しなければ拒否 (custom failure_message が伝わる)。"""
        svc = SpotInteractionService()
        status = _player_status(state={"disguise": "thief"})
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_STATE_IS,
            required_state={"disguise": "noble"},
            failure_message="貴族に変装していない",
        )
        ok, msg = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is False
        assert msg == "貴族に変装していない"

    def test_fails_when_status_is_none(self) -> None:
        """acting_player_status が None なら silent pass を避けるため拒否。"""
        svc = SpotInteractionService()
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_STATE_IS,
            required_state={"disguise": "noble"},
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            # acting_player_status を渡さない
        )
        assert ok is False

    def test_required_state_with_multiple_keys_all_match(self) -> None:
        """複数キーの required_state は全部一致で成立、1 つでも不一致なら拒否。"""
        svc = SpotInteractionService()
        status = _player_status(state={"disguise": "noble", "fire_resist": True})

        cond_pass = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_STATE_IS,
            required_state={"disguise": "noble", "fire_resist": True},
        )
        cond_fail = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_STATE_IS,
            required_state={"disguise": "noble", "fire_resist": False},
        )
        for cond, expected in ((cond_pass, True), (cond_fail, False)):
            ok, _ = svc.can_interact(
                _interaction_with(cond), _switch_object(),
                owned_item_spec_ids=frozenset(),
                world_flags=frozenset(),
                acting_player_status=status,
            )
            assert ok is expected

    def test_missing_required_state_rejected(self) -> None:
        """required_state を渡さない場合は拒否。"""
        svc = SpotInteractionService()
        status = _player_status(state={"x": 1})
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_STATE_IS,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is False


class TestCombinedActingPlayerEffects:
    """1 つの interaction で複数の player effect を発火する積分挙動。"""

    def test_change_and_record_in_one_apply(self) -> None:
        """CHANGE_PLAYER_STATE と RECORD_PLAYER_STATE_TICK を同時に発火し、
        両方が反映 + acting_player_state_changed=True が返る。"""
        svc = WorldGraphEffectService()
        status = _player_status(state={})
        effects = [
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.CHANGE_PLAYER_STATE,
                parameters={"state_updates": {"poisoned": True}},
            ),
            InteractionEffect(
                effect_type=InteractionEffectTypeEnum.RECORD_PLAYER_STATE_TICK,
                parameters={"state_key": "poisoned_at_tick"},
            ),
        ]
        result = svc.apply_effects(
            interior=_empty_interior(), acting_object=None,
            effects=effects, world_flags=frozenset(),
            current_tick=WorldTick(7),
            acting_player_status=status,
        )
        assert status.state == {"poisoned": True, "poisoned_at_tick": 7}
        assert result.acting_player_state_changed is True

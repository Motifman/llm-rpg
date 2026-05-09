"""Phase 4-D-1: プレイヤー状態を判定する precondition のテスト。

新しい 3 種の precondition:

- `PLAYER_NEED_AT_LEAST(need_type, need_threshold)`
  プレイヤーの欲求 (HUNGER / FATIGUE) が threshold 以上のとき成立。
- `PLAYER_HP_RATIO_BELOW(hp_ratio)`
  HP の充足率 (current/max) が hp_ratio 未満のとき成立。
- `PLAYER_HP_RATIO_AT_LEAST(hp_ratio)`
  HP の充足率が hp_ratio 以上のとき成立。BELOW の鏡像。

それぞれ `acting_player_status` を渡されない場合は silent pass を
避けるため拒否する (acting item / target item と同じガード方針)。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.agent_need import AgentNeed, NeedType
from ai_rpg_world.domain.player.value_object.agent_needs import AgentNeeds
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


def _player_status(
    *,
    hp_value: int = 100, hp_max: int = 100,
    hunger: int = 0, fatigue: int = 0,
) -> PlayerStatusAggregate:
    """テスト用に最小限の PlayerStatusAggregate を作る。"""
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(
            max_hp=hp_max, max_mp=50, attack=10, defense=10, speed=10,
            critical_rate=0.05, evasion_rate=0.05,
        ),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=hp_value, max_hp=hp_max),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
        needs=AgentNeeds((
            AgentNeed(need_type=NeedType.HUNGER, value=hunger, max_value=100),
            AgentNeed(need_type=NeedType.FATIGUE, value=fatigue, max_value=100),
        )),
    )


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


class TestPlayerNeedAtLeast:
    """PLAYER_NEED_AT_LEAST: 欲求が閾値以上で成立。"""

    def test_passes_when_need_at_or_above_threshold(self) -> None:
        """HUNGER=70 / threshold=60 → 成立。"""
        svc = SpotInteractionService()
        status = _player_status(hunger=70)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_NEED_AT_LEAST,
            need_type="HUNGER",
            need_threshold=60,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is True

    def test_fails_when_need_below_threshold(self) -> None:
        """HUNGER=30 / threshold=60 → 拒否。"""
        svc = SpotInteractionService()
        status = _player_status(hunger=30)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_NEED_AT_LEAST,
            need_type="HUNGER",
            need_threshold=60,
            failure_message="まだお腹が空いていない",
        )
        ok, msg = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is False
        assert msg == "まだお腹が空いていない"

    def test_passes_at_exact_threshold(self) -> None:
        """境界条件: HUNGER==threshold で成立 (>=)。"""
        svc = SpotInteractionService()
        status = _player_status(hunger=60)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_NEED_AT_LEAST,
            need_type="HUNGER",
            need_threshold=60,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is True

    def test_fails_when_player_status_not_provided(self) -> None:
        """acting_player_status を渡さない場合、silent pass を避けるため拒否。"""
        svc = SpotInteractionService()
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_NEED_AT_LEAST,
            need_type="HUNGER",
            need_threshold=60,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            # acting_player_status を渡さない
        )
        assert ok is False

    def test_invalid_need_type_string_rejected(self) -> None:
        """need_type が NeedType に存在しない名前なら拒否。"""
        svc = SpotInteractionService()
        status = _player_status(hunger=99)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_NEED_AT_LEAST,
            need_type="NOT_A_REAL_NEED",
            need_threshold=60,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is False

    def test_missing_need_type_or_threshold_rejected(self) -> None:
        """need_type または need_threshold が欠けていれば拒否。"""
        svc = SpotInteractionService()
        status = _player_status(hunger=70)
        # need_type 欠落
        cond1 = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_NEED_AT_LEAST,
            need_threshold=60,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond1), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is False
        # need_threshold 欠落
        cond2 = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_NEED_AT_LEAST,
            need_type="HUNGER",
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond2), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is False


class TestPlayerHpRatioBelow:
    """PLAYER_HP_RATIO_BELOW: HP 充足率が閾値未満で成立。"""

    def test_passes_when_hp_low(self) -> None:
        """HP 30/100 (=0.3), hp_ratio=0.5 → 0.3 < 0.5 で成立。"""
        svc = SpotInteractionService()
        status = _player_status(hp_value=30, hp_max=100)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_HP_RATIO_BELOW,
            hp_ratio=0.5,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is True

    def test_fails_when_hp_high(self) -> None:
        """HP 80/100 (=0.8), hp_ratio=0.5 → 拒否。"""
        svc = SpotInteractionService()
        status = _player_status(hp_value=80, hp_max=100)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_HP_RATIO_BELOW,
            hp_ratio=0.5,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is False

    def test_fails_at_exact_ratio_below(self) -> None:
        """境界条件: 充足率 == hp_ratio は BELOW では拒否 (strict <)。"""
        svc = SpotInteractionService()
        status = _player_status(hp_value=50, hp_max=100)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_HP_RATIO_BELOW,
            hp_ratio=0.5,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is False

    def test_fails_when_status_missing(self) -> None:
        """acting_player_status を渡さなければ拒否。"""
        svc = SpotInteractionService()
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_HP_RATIO_BELOW,
            hp_ratio=0.5,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
        )
        assert ok is False


class TestPlayerHpRatioAtLeast:
    """PLAYER_HP_RATIO_AT_LEAST: HP 充足率が閾値以上で成立。"""

    def test_passes_when_hp_high(self) -> None:
        """HP 80/100, hp_ratio=0.5 → 0.8 >= 0.5 で成立。"""
        svc = SpotInteractionService()
        status = _player_status(hp_value=80, hp_max=100)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_HP_RATIO_AT_LEAST,
            hp_ratio=0.5,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is True

    def test_passes_at_exact_ratio_at_least(self) -> None:
        """境界条件: 充足率 == hp_ratio は AT_LEAST では成立 (>=)。"""
        svc = SpotInteractionService()
        status = _player_status(hp_value=50, hp_max=100)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_HP_RATIO_AT_LEAST,
            hp_ratio=0.5,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is True

    def test_fails_when_hp_low(self) -> None:
        """HP 20/100, hp_ratio=0.5 → 拒否。"""
        svc = SpotInteractionService()
        status = _player_status(hp_value=20, hp_max=100)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_HP_RATIO_AT_LEAST,
            hp_ratio=0.5,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is False


class TestZeroMaxHpEdge:
    """max_hp == 0 (理論上ありうる退化ケース) は HP 系 precondition を必ず拒否する。"""

    def test_below_rejects_when_max_hp_zero(self) -> None:
        """max_hp=0 の player では PLAYER_HP_RATIO_BELOW が常に拒否される。"""
        svc = SpotInteractionService()
        status = _player_status(hp_value=0, hp_max=0)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_HP_RATIO_BELOW,
            hp_ratio=0.5,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is False

    def test_at_least_rejects_when_max_hp_zero(self) -> None:
        """max_hp=0 では PLAYER_HP_RATIO_AT_LEAST も拒否される (silent True 防止)。"""
        svc = SpotInteractionService()
        status = _player_status(hp_value=0, hp_max=0)
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PLAYER_HP_RATIO_AT_LEAST,
            hp_ratio=0.0,
        )
        ok, _ = svc.can_interact(
            _interaction_with(cond), _switch_object(),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
            acting_player_status=status,
        )
        assert ok is False


class TestScenarioLoaderValidation:
    """ScenarioLoader が need_type / hp_ratio を load 時に検証する。"""

    def test_invalid_need_type_rejected_at_load(self) -> None:
        """未知の need_type 文字列は ScenarioLoadError で拒否 (silent runtime 失敗を回避)。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoadError, ScenarioLoader,
        )

        with pytest.raises(ScenarioLoadError, match="need_type"):
            ScenarioLoader().load_from_dict(_minimal_scenario_with_precondition({
                "condition_type": "PLAYER_NEED_AT_LEAST",
                "need_type": "NOT_A_REAL_NEED",
                "need_threshold": 50,
            }))

    def test_hp_ratio_out_of_range_rejected_at_load(self) -> None:
        """hp_ratio が 0.0..1.0 の範囲外なら ScenarioLoadError で拒否。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoadError, ScenarioLoader,
        )

        for bad in (-0.1, 1.5, 2.0):
            with pytest.raises(ScenarioLoadError, match="hp_ratio"):
                ScenarioLoader().load_from_dict(_minimal_scenario_with_precondition({
                    "condition_type": "PLAYER_HP_RATIO_BELOW",
                    "hp_ratio": bad,
                }))

    def test_hp_ratio_non_numeric_rejected(self) -> None:
        """hp_ratio が数値でなければ拒否。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import (
            ScenarioLoadError, ScenarioLoader,
        )

        with pytest.raises(ScenarioLoadError, match="hp_ratio"):
            ScenarioLoader().load_from_dict(_minimal_scenario_with_precondition({
                "condition_type": "PLAYER_HP_RATIO_BELOW",
                "hp_ratio": "half",
            }))


def _minimal_scenario_with_precondition(precondition_raw: dict) -> dict:
    """1 player + 1 spot + 1 object + 1 interaction で指定 precondition を持つ最小シナリオ。"""
    return {
        "scenario_format_version": "1.0",
        "metadata": {
            "id": "x", "title": "x", "description": "x",
            "theme": "x", "difficulty": "easy", "estimated_ticks": 1,
            "author": "x", "tags": [],
        },
        "item_specs": [],
        "environment": {
            "weather": {"enabled": False, "initial": {"weather_type": "CLEAR", "intensity": 0.0},
                        "update_interval_ticks": 100, "announce_changes": False},
        },
        "spots": [{
            "id": "s", "name": "S", "description": "d", "category": "OTHER",
            "atmosphere": {"lighting": "DIM", "temperature": "NORMAL"},
            "interior": {"objects": [{
                "id": "o", "name": "O", "description": "d", "object_type": "OTHER",
                "state": {},
                "interactions": [{
                    "action_name": "x", "display_label": "X",
                    "preconditions": [precondition_raw],
                    "effects": [],
                }],
            }]},
        }],
        "connections": [],
        "players": [{"id": "p", "name": "P", "spawn_spot": "s", "initial_items": []}],
        "game_end_conditions": {"win": [], "lose": []},
    }


class TestScenarioLoaderParsesPlayerFields:
    """scenario_loader が need_type / need_threshold / hp_ratio を読み取れる。"""

    def test_loader_propagates_player_need_fields(self) -> None:
        """JSON の need_type/need_threshold が InteractionCondition に反映される。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader

        scenario = {
            "scenario_format_version": "1.0",
            "metadata": {
                "id": "x", "title": "x", "description": "x",
                "theme": "x", "difficulty": "easy", "estimated_ticks": 1,
                "author": "x", "tags": [],
            },
            "item_specs": [],
            "environment": {
                "weather": {"enabled": False, "initial": {"weather_type": "CLEAR", "intensity": 0.0},
                            "update_interval_ticks": 100, "announce_changes": False},
            },
            "spots": [{
                "id": "s", "name": "S", "description": "d", "category": "OTHER",
                "atmosphere": {"lighting": "DIM", "temperature": "NORMAL"},
                "interior": {"objects": [{
                    "id": "o", "name": "O", "description": "d", "object_type": "OTHER",
                    "state": {},
                    "interactions": [{
                        "action_name": "x", "display_label": "X",
                        "preconditions": [{
                            "condition_type": "PLAYER_NEED_AT_LEAST",
                            "need_type": "HUNGER",
                            "need_threshold": 60,
                        }, {
                            "condition_type": "PLAYER_HP_RATIO_BELOW",
                            "hp_ratio": 0.5,
                        }],
                        "effects": [],
                    }],
                }]},
            }],
            "connections": [],
            "players": [{"id": "p", "name": "P", "spawn_spot": "s", "initial_items": []}],
            "game_end_conditions": {"win": [], "lose": []},
        }
        loaded = ScenarioLoader().load_from_dict(scenario)
        spot_id = list(loaded.interiors.keys())[0]
        obj = loaded.interiors[spot_id].objects[0]
        idef = obj.interactions[0]
        assert len(idef.preconditions) == 2

        c1 = idef.preconditions[0]
        assert c1.condition_type == InteractionConditionTypeEnum.PLAYER_NEED_AT_LEAST
        assert c1.need_type == "HUNGER"
        assert c1.need_threshold == 60

        c2 = idef.preconditions[1]
        assert c2.condition_type == InteractionConditionTypeEnum.PLAYER_HP_RATIO_BELOW
        assert c2.hp_ratio == 0.5

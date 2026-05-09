"""Phase 4-D-2 PR 1: PlayerStatusAggregate.state フィールドのテスト。

`state: Dict[str, Any]` を PlayerStatusAggregate に追加することで、
status effect / 変装 / 持続フラグ等、型固定フィールド (HP/needs/gold)
が拾わない任意の状態を保持できるようにする。

SpotObject.state / ItemInstance.state と同じ flat dict セマンティクス
(部分マージ、JSON プリミティブ限定)。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStateValidationException,
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


def _player_status(state: dict | None = None) -> PlayerStatusAggregate:
    """state テスト用の最小 PlayerStatusAggregate。"""
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


class TestPlayerStateBasics:
    """PlayerStatusAggregate.state の基本挙動。"""

    def test_default_state_is_empty_dict(self) -> None:
        """state を渡さない場合、空 dict として初期化される。"""
        status = _player_status()
        assert status.state == {}

    def test_state_initial_value_can_be_set(self) -> None:
        """初期 state を constructor で渡せる。"""
        status = _player_status(state={"alignment": "good", "reputation": 5})
        assert status.state == {"alignment": "good", "reputation": 5}

    def test_state_property_returns_defensive_copy(self) -> None:
        """state プロパティは内部 dict の防御的コピーを返す (外部破壊不可)。"""
        status = _player_status(state={"poisoned": True})
        snapshot = status.state
        snapshot["poisoned"] = False
        snapshot["foo"] = "bar"
        # 内部は変わらない
        assert status.state == {"poisoned": True}

    def test_replace_state_swaps_entire_dict(self) -> None:
        """replace_state は state 全体を置き換える。"""
        status = _player_status(state={"a": 1, "b": 2})
        status.replace_state({"c": 3})
        assert status.state == {"c": 3}

    def test_merge_state_overwrites_keys_and_adds_new(self) -> None:
        """merge_state は同名キー上書き、新規キー追加。"""
        status = _player_status(state={"alignment": "good", "reputation": 5})
        status.merge_state({"alignment": "evil", "disguise": "noble"})
        assert status.state == {"alignment": "evil", "reputation": 5, "disguise": "noble"}


class TestPlayerStateValueValidation:
    """state 値型は JSON プリミティブに制限される (永続化境界)。"""

    def test_non_primitive_value_in_constructor_rejected(self) -> None:
        """constructor 経由で datetime 等を入れると PlayerStateValidationException。"""
        from datetime import datetime

        with pytest.raises(PlayerStateValidationException, match="not JSON-serializable"):
            _player_status(state={"created_at": datetime(2026, 1, 1)})

    def test_non_primitive_value_in_replace_state_rejected(self) -> None:
        """replace_state でも検証されてエラー。"""
        status = _player_status()
        with pytest.raises(PlayerStateValidationException):
            status.replace_state({"obj": object()})

    def test_non_primitive_value_in_merge_state_rejected(self) -> None:
        """merge_state でも検証されてエラー。state は変化しない (atomicity)。"""
        status = _player_status(state={"alignment": "good"})
        with pytest.raises(PlayerStateValidationException):
            status.merge_state({"bad": [1, 2, 3]})  # list は非対応
        # 失敗時に state は元のまま
        assert status.state == {"alignment": "good"}

    def test_non_str_key_rejected(self) -> None:
        """state のキーは str のみ。int キー等は拒否。"""
        status = _player_status()
        with pytest.raises(PlayerStateValidationException, match="key must be str"):
            status.merge_state({1: "a"})

    def test_all_primitive_types_accepted(self) -> None:
        """str / int / float / bool / None は全て通る。"""
        status = _player_status()
        status.merge_state({
            "s": "x", "i": 42, "f": 1.5, "b": True, "n": None,
        })
        assert status.state == {"s": "x", "i": 42, "f": 1.5, "b": True, "n": None}


class TestPlayerStateCoexistsWithOtherFields:
    """state は HP / needs / gold 等の既存フィールドと独立して併存できる。"""

    def test_state_does_not_affect_other_fields(self) -> None:
        """state を変更しても hp / mp / gold は影響を受けない。"""
        status = _player_status(state={"alignment": "good"})
        before_hp = status.hp.value
        before_gold = status.gold.value
        status.merge_state({"alignment": "evil"})
        assert status.hp.value == before_hp
        assert status.gold.value == before_gold

    def test_existing_methods_unchanged(self) -> None:
        """既存の satisfy_need 等は state を持っていても通常通り動く。"""
        from ai_rpg_world.domain.player.value_object.agent_need import NeedType

        status = _player_status(state={"alignment": "good"})
        status.increase_need(NeedType.HUNGER, 30)
        assert status.needs.get(NeedType.HUNGER).value == 30
        # state は変わらない
        assert status.state == {"alignment": "good"}

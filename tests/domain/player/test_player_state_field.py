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
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.exception.player_exceptions import (
    PlayerStateValidationException,
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


def _player_status(state: dict | None = None, *, hp: int = 100, mp: int = 50, gold: int = 0) -> PlayerStatusAggregate:
    """state テスト用の最小 PlayerStatusAggregate。"""
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(1),
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(gold),
        hp=Hp(value=hp, max_hp=100),
        mp=Mp(value=mp, max_mp=50),
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

    @pytest.mark.parametrize(
        "initial_state",
        [None, {"alignment": "good", "reputation": 5}],
        ids=["empty", "nonempty"],
    )
    def test_non_primitive_value_in_replace_state_rejected(self, initial_state) -> None:
        """置換で基本型以外を拒否すると、空・非空の元の状態は変わらない。"""
        status = _player_status(state=initial_state)
        before = dict(status.state)
        with pytest.raises(PlayerStateValidationException):
            status.replace_state({"obj": object()})
        assert status.state == before

    @pytest.mark.parametrize(
        "updates",
        [
            {"bad": [1, 2, 3]},
            {"alignment": "evil", "disguise": "noble", "bad": [1, 2, 3]},
        ],
        ids=["invalid-only", "valid-values-before-invalid"],
    )
    def test_non_primitive_value_in_merge_state_rejected(self, updates) -> None:
        """部分更新に不正な値があれば、他の有効な値も反映されない。"""
        status = _player_status(state={"alignment": "good"})
        before = dict(status.state)
        with pytest.raises(PlayerStateValidationException):
            status.merge_state(updates)  # list は非対応
        # 失敗時に state は元のまま
        assert status.state == {"alignment": "good"}
        assert status.state == before

    @pytest.mark.parametrize(
        ("initial_state", "updates"),
        [
            (None, {1: "a"}),
            ({"alignment": "good"}, {"alignment": "evil", "extra": 7, 1: "a"}),
        ],
        ids=["invalid-only", "valid-keys-before-invalid"],
    )
    def test_non_str_key_rejected(self, initial_state, updates) -> None:
        """整数キーの部分更新を拒否すると、先行する有効キーも反映されない。"""
        status = _player_status(state=initial_state)
        before = dict(status.state)
        with pytest.raises(PlayerStateValidationException, match="key must be str"):
            status.merge_state(updates)
        assert status.state == before

    def test_all_primitive_types_accepted(self) -> None:
        """str / int / float / bool / None は値も型も変えずに保持される。"""
        status = _player_status()
        status.merge_state(
            {
                "s": "x",
                "i": 42,
                "f": 1.5,
                "b": True,
                "n": None,
            }
        )
        assert status.state == {"s": "x", "i": 42, "f": 1.5, "b": True, "n": None}
        assert type(status.state["s"]) is str
        assert type(status.state["i"]) is int
        assert type(status.state["f"]) is float
        assert type(status.state["b"]) is bool
        assert status.state["n"] is None


class TestPlayerStateCoexistsWithOtherFields:
    """state は HP / needs / gold 等の既存フィールドと独立して併存できる。"""

    @pytest.mark.parametrize(
        ("hp", "mp", "gold"),
        [(100, 50, 0), (63, 17, 41)],
        ids=["default-resources", "nondefault-resources"],
    )
    def test_state_does_not_affect_other_fields(self, hp, mp, gold) -> None:
        """状態の更新でHP・MPの値と上限・所持金は変わらない。"""
        status = _player_status(state={"alignment": "good"}, hp=hp, mp=mp, gold=gold)
        before_hp = status.hp.value
        before_gold = status.gold.value
        status.merge_state({"alignment": "evil"})
        assert status.hp.value == before_hp
        assert status.gold.value == before_gold
        assert (status.hp.value, status.hp.max_hp) == (hp, 100)
        assert (status.mp.value, status.mp.max_mp) == (mp, 50)
        assert status.gold.value == gold

    def test_existing_methods_unchanged(self) -> None:
        """状態を持つ集約で空腹を増やしても、その状態の内容は変わらない。"""
        from ai_rpg_world.domain.player.value_object.agent_need import NeedType

        status = _player_status(state={"alignment": "good"})
        status.increase_need(NeedType.HUNGER, 30)
        assert status.needs.get(NeedType.HUNGER).value == 30
        # state は変わらない
        assert status.state == {"alignment": "good"}

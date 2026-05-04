"""AgentNeed / AgentNeeds のユニットテスト。

欲求値の増減、閾値判定、コレクション操作、describe テキストを検証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.value_object.agent_need import AgentNeed, NeedType
from ai_rpg_world.domain.player.value_object.agent_needs import AgentNeeds


class TestAgentNeed:
    """単一欲求のテスト"""

    def test_create_clamps_value(self) -> None:
        """createで値が範囲内にクランプされること"""
        need = AgentNeed.create(NeedType.HUNGER, 150, 100)
        assert need.value == 100
        need2 = AgentNeed.create(NeedType.HUNGER, -10, 100)
        assert need2.value == 0

    def test_increase(self) -> None:
        """increaseで値が増加すること"""
        need = AgentNeed.create(NeedType.HUNGER, 30, 100)
        increased = need.increase(20)
        assert increased.value == 50

    def test_increase_clamps_at_max(self) -> None:
        """increaseで最大値を超えないこと"""
        need = AgentNeed.create(NeedType.HUNGER, 90, 100)
        increased = need.increase(20)
        assert increased.value == 100

    def test_satisfy(self) -> None:
        """satisfyで値が減少すること"""
        need = AgentNeed.create(NeedType.HUNGER, 80, 100)
        satisfied = need.satisfy(30)
        assert satisfied.value == 50

    def test_satisfy_clamps_at_zero(self) -> None:
        """satisfyで0未満にならないこと"""
        need = AgentNeed.create(NeedType.HUNGER, 10, 100)
        satisfied = need.satisfy(50)
        assert satisfied.value == 0

    def test_is_critical(self) -> None:
        """80%以上でis_criticalがTrueになること"""
        need = AgentNeed.create(NeedType.HUNGER, 80, 100)
        assert need.is_critical is True
        need2 = AgentNeed.create(NeedType.HUNGER, 79, 100)
        assert need2.is_critical is False

    def test_is_satisfied(self) -> None:
        """20%以下でis_satisfiedがTrueになること"""
        need = AgentNeed.create(NeedType.HUNGER, 20, 100)
        assert need.is_satisfied is True
        need2 = AgentNeed.create(NeedType.HUNGER, 21, 100)
        assert need2.is_satisfied is False

    def test_describe_levels(self) -> None:
        """describeが欲求レベルに応じたテキストを返すこと"""
        need0 = AgentNeed.create(NeedType.HUNGER, 10, 100)
        assert "問題なし" in need0.describe()
        need60 = AgentNeed.create(NeedType.HUNGER, 60, 100)
        assert "高い" in need60.describe()
        need90 = AgentNeed.create(NeedType.HUNGER, 90, 100)
        assert "危険" in need90.describe()

    def test_frozen(self) -> None:
        """AgentNeedがfrozenであること"""
        need = AgentNeed.create(NeedType.HUNGER, 50, 100)
        with pytest.raises(AttributeError):
            need.value = 60  # type: ignore[misc]

    def test_invalid_max_value(self) -> None:
        """max_value <= 0 でValueErrorが発生すること"""
        with pytest.raises(ValueError):
            AgentNeed(NeedType.HUNGER, 0, 0)

    def test_fatigue_describe(self) -> None:
        """疲労のdescribeテキストが正しいこと"""
        need = AgentNeed.create(NeedType.FATIGUE, 70, 100)
        assert "疲労" in need.describe()


class TestAgentNeeds:
    """欲求コレクションのテスト"""

    def test_default_creates_hunger_and_fatigue(self) -> None:
        """defaultで空腹と疲労が0で初期化されること"""
        needs = AgentNeeds.default()
        assert len(needs) == 2
        hunger = needs.get(NeedType.HUNGER)
        assert hunger is not None
        assert hunger.value == 0
        fatigue = needs.get(NeedType.FATIGUE)
        assert fatigue is not None
        assert fatigue.value == 0

    def test_with_updated(self) -> None:
        """with_updatedで特定の欲求を更新できること"""
        needs = AgentNeeds.default()
        hunger = needs.get(NeedType.HUNGER)
        assert hunger is not None
        updated = needs.with_updated(hunger.increase(30))
        new_hunger = updated.get(NeedType.HUNGER)
        assert new_hunger is not None
        assert new_hunger.value == 30
        # 元のコレクションは変わらない
        assert needs.get(NeedType.HUNGER).value == 0  # type: ignore

    def test_increase_all(self) -> None:
        """increase_allで全欲求を一括増加できること"""
        needs = AgentNeeds.default()
        updated = needs.increase_all({NeedType.HUNGER: 5, NeedType.FATIGUE: 3})
        assert updated.get(NeedType.HUNGER).value == 5  # type: ignore
        assert updated.get(NeedType.FATIGUE).value == 3  # type: ignore

    def test_describe_all(self) -> None:
        """describe_allで全欲求のテキストが返ること"""
        needs = AgentNeeds.default()
        descriptions = needs.describe_all()
        assert len(descriptions) == 2
        assert any("空腹" in d for d in descriptions)
        assert any("疲労" in d for d in descriptions)

    def test_empty(self) -> None:
        """emptyで空のコレクションが返ること"""
        needs = AgentNeeds.empty()
        assert len(needs) == 0
        assert needs.get(NeedType.HUNGER) is None

    def test_with_updated_inserts_unregistered_type(self) -> None:
        """with_updatedで未登録のNeedTypeは末尾に追加されること"""
        needs = AgentNeeds.empty()
        hunger = AgentNeed.create(NeedType.HUNGER, 50, 100)
        updated = needs.with_updated(hunger)
        assert len(updated) == 1
        assert updated.get(NeedType.HUNGER) is not None
        assert updated.get(NeedType.HUNGER).value == 50  # type: ignore

    def test_has_critical(self) -> None:
        """has_criticalが危険レベルの欲求がある場合にTrueになること"""
        needs = AgentNeeds.default()
        assert needs.has_critical is False
        critical_hunger = AgentNeed.create(NeedType.HUNGER, 85, 100)
        updated = needs.with_updated(critical_hunger)
        assert updated.has_critical is True

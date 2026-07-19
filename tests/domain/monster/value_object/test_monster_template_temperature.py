"""MonsterTemplate の温度 comfort range API テスト (Phase 4-O B)。

検証対象:
- バリデーション (型 / 範囲 / min <= max)
- `temperature_discomfort()` の判定 (kind=None / "too_cold" / "too_hot")
- damage=0 では常に None (= 効果無効化)
- TemperatureEnum.severity の順序
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterTemplateValidationException,
)
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import (
    MonsterTemplateId,
)
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum


def _base_template(**overrides) -> MonsterTemplate:
    defaults = dict(
        template_id=MonsterTemplateId.create(1),
        name="Wolf",
        base_stats=BaseStats(20, 0, 4, 0, 1, 0.0, 0.0),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(100, True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.NEUTRAL,
        description="A wolf.",
    )
    defaults.update(overrides)
    return MonsterTemplate(**defaults)


class TestTemperatureSeverity:
    """TemperatureEnum.severity が 0 (寒) - 4 (暑) の順序。"""

    def test_severity(self) -> None:
        """severity は寒い順に整数。"""
        assert TemperatureEnum.FREEZING.severity == 0
        assert TemperatureEnum.COLD.severity == 1
        assert TemperatureEnum.NORMAL.severity == 2
        assert TemperatureEnum.WARM.severity == 3
        assert TemperatureEnum.HOT.severity == 4


class TestDefaults:
    """default では comfort 全範囲 + damage=0 で従来挙動互換。"""

    def test_default_min_is_FREEZING(self) -> None:
        t = _base_template()
        assert t.min_comfortable_temperature == TemperatureEnum.FREEZING
        assert t.max_comfortable_temperature == TemperatureEnum.HOT
        assert t.temperature_discomfort_damage_per_tick == 0

    def test_returns_none_default(self) -> None:
        """default ではどの温度でも None を返す。"""
        t = _base_template()
        for temp in TemperatureEnum:
            assert t.temperature_discomfort(temp) is None


class TestComfortRangeValidation:
    """min <= max の不変条件。"""

    def test_min_max_ok(self) -> None:
        """min が max より 寒なら OK。"""
        _base_template(
            min_comfortable_temperature=TemperatureEnum.COLD,
            max_comfortable_temperature=TemperatureEnum.WARM,
            temperature_discomfort_damage_per_tick=2,
        )

    def test_min_max_same_ok(self) -> None:
        """寒さに弱く暑さにも弱い (NORMAL のみ快適) は許容。"""
        _base_template(
            min_comfortable_temperature=TemperatureEnum.NORMAL,
            max_comfortable_temperature=TemperatureEnum.NORMAL,
            temperature_discomfort_damage_per_tick=1,
        )

    def test_min_max_raises_exception(self) -> None:
        """min が max より 暑なら 例外。"""
        with pytest.raises(
            MonsterTemplateValidationException, match="min_comfortable_temperature",
        ):
            _base_template(
                min_comfortable_temperature=TemperatureEnum.HOT,
                max_comfortable_temperature=TemperatureEnum.COLD,
            )

    def test_min_temperature_enum_raises_exception(self) -> None:
        """min が TemperatureEnum でないと例外。"""
        with pytest.raises(
            MonsterTemplateValidationException, match="min_comfortable_temperature",
        ):
            _base_template(min_comfortable_temperature="cold")

    def test_damage_raises_exception(self) -> None:
        """damage が負なら例外。"""
        with pytest.raises(
            MonsterTemplateValidationException,
            match="temperature_discomfort_damage_per_tick",
        ):
            _base_template(temperature_discomfort_damage_per_tick=-1)

    def test_damage_bool_raises_exception(self) -> None:
        """damage が bool なら 例外。"""
        with pytest.raises(
            MonsterTemplateValidationException,
            match="temperature_discomfort_damage_per_tick",
        ):
            _base_template(temperature_discomfort_damage_per_tick=True)


class TestTemperatureDiscomfortJudgment:
    """`temperature_discomfort()` の kind 判定。"""

    def test_too_cold(self) -> None:
        """COLD-WARM が快適、FREEZING は too_cold。"""
        t = _base_template(
            min_comfortable_temperature=TemperatureEnum.COLD,
            max_comfortable_temperature=TemperatureEnum.WARM,
            temperature_discomfort_damage_per_tick=1,
        )
        assert t.temperature_discomfort(TemperatureEnum.FREEZING) == "too_cold"

    def test_too_hot(self) -> None:
        """暑すぎると toohot。"""
        t = _base_template(
            min_comfortable_temperature=TemperatureEnum.COLD,
            max_comfortable_temperature=TemperatureEnum.WARM,
            temperature_discomfort_damage_per_tick=1,
        )
        assert t.temperature_discomfort(TemperatureEnum.HOT) == "too_hot"

    def test_boundary(self) -> None:
        """min/max 境界 (severity 等しい) は不快ではない。"""
        t = _base_template(
            min_comfortable_temperature=TemperatureEnum.COLD,
            max_comfortable_temperature=TemperatureEnum.WARM,
            temperature_discomfort_damage_per_tick=1,
        )
        assert t.temperature_discomfort(TemperatureEnum.COLD) is None
        assert t.temperature_discomfort(TemperatureEnum.WARM) is None
        assert t.temperature_discomfort(TemperatureEnum.NORMAL) is None

    def test_damage_zero_none(self) -> None:
        """damage=0 は効果無効化として明示的に None 返却。"""
        t = _base_template(
            min_comfortable_temperature=TemperatureEnum.NORMAL,
            max_comfortable_temperature=TemperatureEnum.NORMAL,
            temperature_discomfort_damage_per_tick=0,
        )
        assert t.temperature_discomfort(TemperatureEnum.FREEZING) is None
        assert t.temperature_discomfort(TemperatureEnum.HOT) is None

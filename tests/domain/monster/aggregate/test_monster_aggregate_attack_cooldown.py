"""MonsterAggregate に追加した last_attack_tick / can_attack_now / record_attack の挙動。

検証対象:
- 初期値で can_attack_now=True (last_attack_tick=None)
- record_attack 後は last_attack_tick が更新され cooldown 中は False
- cooldown 経過後に True に戻る
- DEAD 状態では can_attack_now=False、record_attack は例外
- MonsterTemplate.attack_cooldown_ticks のバリデーション
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import (
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterAlreadyDeadException,
    MonsterTemplateValidationException,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import (
    MonsterTemplateId,
)
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import (
    SkillLoadoutAggregate,
)
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


def _base_stats() -> BaseStats:
    return BaseStats(
        max_hp=10,
        max_mp=0,
        attack=5,
        defense=0,
        speed=1,
        critical_rate=0.0,
        evasion_rate=0.0,
    )


def _template(*, attack_cooldown_ticks: int = 3) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="灰色のオオカミ",
        base_stats=_base_stats(),
        reward_info=RewardInfo(exp=1, gold=1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="A grey wolf.",
        attack_cooldown_ticks=attack_cooldown_ticks,
    )


def _aggregate(template: MonsterTemplate | None = None) -> MonsterAggregate:
    return MonsterAggregate(
        monster_id=MonsterId.create(101),
        template=template or _template(),
        world_object_id=WorldObjectId.create(9001),
        skill_loadout=SkillLoadoutAggregate.create(
            SkillLoadoutId(1),
            owner_id=101,
            normal_capacity=4,
            awakened_capacity=2,
        ),
        status=MonsterStatusEnum.ALIVE,
        spawned_at_tick=WorldTick(0),
    )


class TestInitialState:
    """生成直後の状態。"""

    def test_last_attack_tick_initial_value_none(self) -> None:
        """last_attack_tick は初期 None。"""
        agg = _aggregate()
        assert agg.last_attack_tick is None

    def test_can_attack_now_true(self) -> None:
        """last_attack_tick=None なら can_attack_now は True。"""
        agg = _aggregate()
        assert agg.can_attack_now(WorldTick(5)) is True


class TestCooldown:
    """record_attack 後の cooldown 経過判定。"""

    @pytest.mark.parametrize(
        ("cooldown_ticks", "checks"),
        [
            pytest.param(
                3,
                ((10, False), (11, False), (12, False), (13, True)),
                id="three-tick-cooldown",
            ),
            pytest.param(1, ((10, False),), id="same-tick-with-minimum-cooldown"),
            pytest.param(5, ((14, False), (15, True)), id="five-tick-boundary"),
        ],
    )
    def test_attack_availability_after_recording(
        self,
        cooldown_ticks: int,
        checks: tuple[tuple[int, bool], ...],
    ) -> None:
        """tick10の攻撃後は指定間隔に達するまで拒否し、境界ちょうどで許可する。"""
        agg = _aggregate(_template(attack_cooldown_ticks=cooldown_ticks))
        agg.record_attack(WorldTick(10))

        for tick, expected in checks:
            assert agg.can_attack_now(WorldTick(tick)) is expected

    def test_last_attack_tick_value_updated(self) -> None:
        """tick10に続くtick20の攻撃で記録を更新し、待ち時間2を再び適用する。"""
        agg = _aggregate(_template(attack_cooldown_ticks=2))
        agg.record_attack(WorldTick(10))
        agg.record_attack(WorldTick(20))
        assert agg.last_attack_tick == WorldTick(20)
        assert agg.can_attack_now(WorldTick(20)) is False
        assert agg.can_attack_now(WorldTick(21)) is False
        assert agg.can_attack_now(WorldTick(22)) is True


class TestDeadMonster:
    """DEAD 状態の挙動。"""

    def test_dead_can_attack_now_false(self) -> None:
        """致命ダメージで死亡した個体は、時間が経過しても攻撃できない。"""
        agg = _aggregate()
        agg.take_environmental_damage(damage=999, current_tick=WorldTick(5))
        assert agg.hp.value == 0
        assert agg.status == MonsterStatusEnum.DEAD

        assert agg.can_attack_now(WorldTick(100)) is False

    def test_dead_record_attack_raises_exception(self) -> None:
        """HPが残る飢餓死後の攻撃記録は拒否され、既存の記録とイベントを保つ。"""
        agg = _aggregate()
        agg.starve(WorldTick(5))
        assert agg.hp.value == 10
        assert agg.status == MonsterStatusEnum.DEAD
        events_before = agg.get_events()
        assert events_before

        with pytest.raises(MonsterAlreadyDeadException):
            agg.record_attack(WorldTick(100))

        assert agg.last_attack_tick is None
        assert agg.get_events() == events_before


class TestTemplateValidation:
    """attack_cooldown_ticks / has_dark_vision のバリデーション。"""

    @pytest.mark.parametrize("cooldown_ticks", [0, -1])
    def test_nonpositive_attack_cooldown_ticks_raise_exception(
        self,
        cooldown_ticks: int,
    ) -> None:
        """攻撃間隔が0または負数なら、テンプレートの検証例外で拒否する。"""
        with pytest.raises(MonsterTemplateValidationException):
            _template(attack_cooldown_ticks=cooldown_ticks)

    def test_has_dark_vision_default_false(self) -> None:
        """デフォルト has_dark_vision は False。"""
        t = _template()
        assert t.has_dark_vision is False

    def test_attack_cooldown_ticks_defaults_to_one(self) -> None:
        """デフォルト attack_cooldown_ticks は 1（毎 tick 攻撃可）。"""
        t = MonsterTemplate(
            template_id=MonsterTemplateId.create(1),
            name="x",
            base_stats=_base_stats(),
            reward_info=RewardInfo(exp=1, gold=1),
            respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="x",
        )
        assert t.attack_cooldown_ticks == 1

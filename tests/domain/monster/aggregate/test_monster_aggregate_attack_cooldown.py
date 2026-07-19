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

    def test_record_attack_after_false(self) -> None:
        """同じ tick では cooldown 未満で can_attack_now=False。"""
        agg = _aggregate(_template(attack_cooldown_ticks=3))
        agg.record_attack(WorldTick(10))
        assert agg.can_attack_now(WorldTick(10)) is False
        assert agg.can_attack_now(WorldTick(11)) is False
        assert agg.can_attack_now(WorldTick(12)) is False

    def test_record_attack_same_tick_can_attack_now_false(self) -> None:
        """同じ tick で 2 回目を呼ぶと False（elapsed=0 < cooldown）。"""
        agg = _aggregate(_template(attack_cooldown_ticks=1))
        agg.record_attack(WorldTick(10))
        # cooldown=1 でも record と同じ tick なら elapsed=0 で不可
        assert agg.can_attack_now(WorldTick(10)) is False

    def test_boundary_value_elapsed_cooldown_equals_true(self) -> None:
        """`elapsed == attack_cooldown_ticks` で can_attack_now=True（>= 比較）。"""
        agg = _aggregate(_template(attack_cooldown_ticks=5))
        agg.record_attack(WorldTick(10))
        # 境界の少し下は False
        assert agg.can_attack_now(WorldTick(14)) is False
        # 境界ちょうどで True
        assert agg.can_attack_now(WorldTick(15)) is True

    def test_record_attack_after_cooldown_true(self) -> None:
        """`current_tick - last_attack_tick >= attack_cooldown_ticks` で True。"""
        agg = _aggregate(_template(attack_cooldown_ticks=3))
        agg.record_attack(WorldTick(10))
        assert agg.can_attack_now(WorldTick(13)) is True

    def test_last_attack_tick_value_updated(self) -> None:
        """連続 record_attack で last_attack_tick が上書きされる。"""
        agg = _aggregate(_template(attack_cooldown_ticks=2))
        agg.record_attack(WorldTick(10))
        agg.record_attack(WorldTick(20))
        assert agg.last_attack_tick == WorldTick(20)


class TestDeadMonster:
    """DEAD 状態の挙動。"""

    def test_dead_can_attack_now_false(self) -> None:
        """status=DEAD は cooldown 関係なく False。"""
        agg = _aggregate()
        agg._lifecycle_state = agg._lifecycle_state.apply_damage(999)  # 致命
        # 致命後の状態は apply_damage 経由で扱うべきだが、ここでは status を
        # 直接書き換えて DEAD を再現する（テストの purpose は can_attack_now
        # の戻り値検証のみ）。
        from ai_rpg_world.domain.monster.value_object.monster_lifecycle_state import (
            MonsterLifecycleState,
        )

        agg._lifecycle_state = MonsterLifecycleState(
            hp=agg._lifecycle_state.hp,
            mp=agg._lifecycle_state.mp,
            status=MonsterStatusEnum.DEAD,
            last_death_tick=WorldTick(5),
            spawned_at_tick=WorldTick(0),
            hunger=0.0,
            starvation_timer=0,
        )
        assert agg.can_attack_now(WorldTick(100)) is False

    def test_dead_record_attack_raises_exception(self) -> None:
        """DEAD 状態で record_attack を呼ぶと MonsterAlreadyDeadException。"""
        from ai_rpg_world.domain.monster.value_object.monster_lifecycle_state import (
            MonsterLifecycleState,
        )

        agg = _aggregate()
        agg._lifecycle_state = MonsterLifecycleState(
            hp=agg._lifecycle_state.hp,
            mp=agg._lifecycle_state.mp,
            status=MonsterStatusEnum.DEAD,
            last_death_tick=WorldTick(5),
            spawned_at_tick=WorldTick(0),
            hunger=0.0,
            starvation_timer=0,
        )
        with pytest.raises(MonsterAlreadyDeadException):
            agg.record_attack(WorldTick(100))


class TestTemplateValidation:
    """attack_cooldown_ticks / has_dark_vision のバリデーション。"""

    def test_zero_or_less_attack_cooldown_ticks_raise_exception(self) -> None:
        """0 以下は ValidationException。"""
        with pytest.raises(MonsterTemplateValidationException):
            _template(attack_cooldown_ticks=0)

    def test_negative_attack_cooldown_ticks_raise_exception(self) -> None:
        """負値は ValidationException。"""
        with pytest.raises(MonsterTemplateValidationException):
            _template(attack_cooldown_ticks=-1)

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

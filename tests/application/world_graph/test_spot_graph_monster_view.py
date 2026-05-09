"""`spot_graph_monster_view.build_monster_view_provider` の単体テスト。

検証対象:
- HP バケット化（healthy / wounded / dying / dead）
- behavior_state の日本語ラベル変換
- 死亡個体の特別表記
- aggregate が None なら view も None
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world_graph.spot_graph_monster_view import (
    HEALTH_DEAD,
    HEALTH_DYING,
    HEALTH_HEALTHY,
    HEALTH_WOUNDED,
    build_monster_view_provider,
)
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId


class _BehaviorStub:
    def __init__(self, value: str) -> None:
        self.value = value


class _HpStub:
    def __init__(self, value: int, max_hp: int) -> None:
        self.value = value
        self.max_hp = max_hp


class _TemplateStub:
    def __init__(self, name: str) -> None:
        self.name = name


def _make_aggregate(
    *,
    name: str = "灰色のオオカミ",
    hp: int = 100,
    max_hp: int = 100,
    behavior_value: str = "IDLE",
    status: MonsterStatusEnum = MonsterStatusEnum.ALIVE,
):
    """テスト用の最小限な MonsterAggregate モック。"""
    agg = MagicMock()
    agg.template = _TemplateStub(name)
    agg.hp = _HpStub(hp, max_hp)
    agg.behavior_state = _BehaviorStub(behavior_value)
    agg.status = status
    return agg


class TestHealthBucketing:
    """HP の比率を 3 段階バケットに丸める挙動。"""

    def test_満タンは_healthy(self) -> None:
        """HP が満タンなら healthy バケット。"""
        lookup = MagicMock()
        lookup.find_by_id.return_value = _make_aggregate(hp=100, max_hp=100)
        provider = build_monster_view_provider(lookup)

        view = provider(MonsterId.create(101))

        assert view is not None
        assert view.health_bucket == HEALTH_HEALTHY

    def test_半分以下は_wounded(self) -> None:
        """HP 50% は wounded（30%以上70%未満）。"""
        lookup = MagicMock()
        lookup.find_by_id.return_value = _make_aggregate(hp=50, max_hp=100)
        provider = build_monster_view_provider(lookup)

        assert provider(MonsterId.create(101)).health_bucket == HEALTH_WOUNDED

    def test_30パーセント未満は_dying(self) -> None:
        """HP 20% は dying（瀕死）。"""
        lookup = MagicMock()
        lookup.find_by_id.return_value = _make_aggregate(hp=20, max_hp=100)
        provider = build_monster_view_provider(lookup)

        assert provider(MonsterId.create(101)).health_bucket == HEALTH_DYING

    def test_境界値_70パーセント以上は_healthy(self) -> None:
        """しきい値 0.70 ちょうどは healthy 側（healthy ≧ 0.70）。"""
        lookup = MagicMock()
        lookup.find_by_id.return_value = _make_aggregate(hp=70, max_hp=100)
        provider = build_monster_view_provider(lookup)

        assert provider(MonsterId.create(101)).health_bucket == HEALTH_HEALTHY

    def test_境界値_69パーセントは_wounded(self) -> None:
        """境界の少し下（HP 69%）は wounded。"""
        lookup = MagicMock()
        lookup.find_by_id.return_value = _make_aggregate(hp=69, max_hp=100)
        provider = build_monster_view_provider(lookup)

        assert provider(MonsterId.create(101)).health_bucket == HEALTH_WOUNDED

    def test_max_hp_ゼロは_healthy_扱い(self) -> None:
        """max_hp=0 のテンプレ（HP を持たない概念モンスター）は healthy 表示。"""
        lookup = MagicMock()
        lookup.find_by_id.return_value = _make_aggregate(hp=0, max_hp=0)
        provider = build_monster_view_provider(lookup)

        assert provider(MonsterId.create(101)).health_bucket == HEALTH_HEALTHY


class TestBehaviorLabel:
    """behavior_state の日本語ラベル変換。"""

    def test_idle_は落ち着いている(self) -> None:
        """IDLE → 落ち着いている。"""
        lookup = MagicMock()
        lookup.find_by_id.return_value = _make_aggregate(behavior_value="IDLE")
        view = build_monster_view_provider(lookup)(MonsterId.create(101))

        assert view.behavior_label == "落ち着いている"

    def test_chase_はこちらを追っている(self) -> None:
        """CHASE → こちらを追っている。"""
        lookup = MagicMock()
        lookup.find_by_id.return_value = _make_aggregate(behavior_value="CHASE")
        view = build_monster_view_provider(lookup)(MonsterId.create(101))

        assert view.behavior_label == "こちらを追っている"

    def test_未知の_state_はそのまま(self) -> None:
        """マップに無い state は元の文字列を返す（落ちない）。"""
        lookup = MagicMock()
        lookup.find_by_id.return_value = _make_aggregate(behavior_value="MYSTERY")
        view = build_monster_view_provider(lookup)(MonsterId.create(101))

        assert view.behavior_label == "MYSTERY"


class TestDeadMonster:
    """死亡個体は別表記（is_dead=True, behavior は固定文言）。"""

    def test_dead_status_は_is_dead_true(self) -> None:
        """status=DEAD のときは is_dead=True、health_bucket=dead。"""
        lookup = MagicMock()
        lookup.find_by_id.return_value = _make_aggregate(
            status=MonsterStatusEnum.DEAD,
            hp=0,
            max_hp=100,
            behavior_value="IDLE",
        )
        view = build_monster_view_provider(lookup)(MonsterId.create(101))

        assert view.is_dead is True
        assert view.health_bucket == HEALTH_DEAD
        assert view.behavior_label == "動かない"


class TestNotFound:
    """aggregate が見つからない場合は None。"""

    def test_aggregate_none_は_view_none(self) -> None:
        """find_by_id が None を返した場合は provider も None を返す。"""
        lookup = MagicMock()
        lookup.find_by_id.return_value = None

        view = build_monster_view_provider(lookup)(MonsterId.create(999))

        assert view is None


class TestNameFallback:
    """テンプレ名が空のときのフォールバック。"""

    def test_空名は何かのモンスター(self) -> None:
        """template.name が空文字なら "何かのモンスター" になる。"""
        lookup = MagicMock()
        lookup.find_by_id.return_value = _make_aggregate(name="   ")
        view = build_monster_view_provider(lookup)(MonsterId.create(101))

        assert view.display_name == "何かのモンスター"

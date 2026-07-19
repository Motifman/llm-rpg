"""MonsterVisibilityService の単体テスト。

検証対象: 環境光量 と `MonsterTemplate.has_dark_vision` の OR 判定。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.domain.monster.service.monster_visibility_service import (
    MonsterVisibilityService,
)
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum


def _template(*, has_dark_vision: bool):
    """has_dark_vision だけ可変のテンプレ mock を返す。"""
    t = MagicMock()
    t.has_dark_vision = has_dark_vision
    return t


class TestCanSeeTarget:
    """環境光量 × dark_vision の組み合わせ判定。"""

    def test_dark_vision(self) -> None:
        """BRIGHT では dark_vision の有無によらず可視。"""
        svc = MonsterVisibilityService()
        assert svc.can_see_target(_template(has_dark_vision=False), LightingEnum.BRIGHT) is True

    def test_documented_behavior(self) -> None:
        """DIM は最小実装では可視扱い（命中率低下等は将来拡張）。"""
        svc = MonsterVisibilityService()
        assert svc.can_see_target(_template(has_dark_vision=False), LightingEnum.DIM) is True

    def test_darkness_dark_vision(self) -> None:
        """DARK + dark_vision なし → 不可視。"""
        svc = MonsterVisibilityService()
        assert svc.can_see_target(_template(has_dark_vision=False), LightingEnum.DARK) is False

    def test_pitch_darkness_dark_vision(self) -> None:
        """PITCH_BLACK も同じく不可視。"""
        svc = MonsterVisibilityService()
        assert svc.can_see_target(_template(has_dark_vision=False), LightingEnum.PITCH_BLACK) is False

    def test_dark_vision_darkness(self) -> None:
        """has_dark_vision=True なら DARK でも True。"""
        svc = MonsterVisibilityService()
        assert svc.can_see_target(_template(has_dark_vision=True), LightingEnum.DARK) is True

    def test_dark_vision_pitch_darkness(self) -> None:
        """has_dark_vision=True なら PITCH_BLACK でも True。"""
        svc = MonsterVisibilityService()
        assert svc.can_see_target(_template(has_dark_vision=True), LightingEnum.PITCH_BLACK) is True

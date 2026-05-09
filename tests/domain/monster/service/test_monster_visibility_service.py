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

    def test_明るい_かつ_dark_vision無しは見える(self) -> None:
        """BRIGHT では dark_vision の有無によらず可視。"""
        svc = MonsterVisibilityService()
        assert svc.can_see_target(_template(has_dark_vision=False), LightingEnum.BRIGHT) is True

    def test_薄暗いも見える(self) -> None:
        """DIM は最小実装では可視扱い（命中率低下等は将来拡張）。"""
        svc = MonsterVisibilityService()
        assert svc.can_see_target(_template(has_dark_vision=False), LightingEnum.DIM) is True

    def test_暗闇_かつ_dark_vision無しは見えない(self) -> None:
        """DARK + dark_vision なし → 不可視。"""
        svc = MonsterVisibilityService()
        assert svc.can_see_target(_template(has_dark_vision=False), LightingEnum.DARK) is False

    def test_漆黒_かつ_dark_vision無しは見えない(self) -> None:
        """PITCH_BLACK も同じく不可視。"""
        svc = MonsterVisibilityService()
        assert svc.can_see_target(_template(has_dark_vision=False), LightingEnum.PITCH_BLACK) is False

    def test_dark_vision有りは暗闇でも見える(self) -> None:
        """has_dark_vision=True なら DARK でも True。"""
        svc = MonsterVisibilityService()
        assert svc.can_see_target(_template(has_dark_vision=True), LightingEnum.DARK) is True

    def test_dark_vision有りは漆黒でも見える(self) -> None:
        """has_dark_vision=True なら PITCH_BLACK でも True。"""
        svc = MonsterVisibilityService()
        assert svc.can_see_target(_template(has_dark_vision=True), LightingEnum.PITCH_BLACK) is True

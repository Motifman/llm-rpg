"""ObservationFormatterContext のテスト。"""

import pytest
from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)


def _make_name_resolver() -> ObservationNameResolver:
    """テスト用の ObservationNameResolver を生成。"""
    return ObservationNameResolver()


class TestObservationFormatterContextCreation:
    """ObservationFormatterContext 生成のテスト"""

    def test_creates_with_name_resolver_and_item_repository(self):
        """name_resolver と item_repository を指定して生成できる。"""
        name_resolver = _make_name_resolver()
        item_repository = MagicMock()
        ctx = ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=item_repository,
        )
        assert ctx.name_resolver is name_resolver
        assert ctx.item_repository is item_repository

    def test_creates_with_name_resolver_and_none_item_repository(self):
        """item_repository に None を指定して生成できる。"""
        name_resolver = _make_name_resolver()
        ctx = ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=None,
        )
        assert ctx.name_resolver is name_resolver
        assert ctx.item_repository is None

    def test_name_resolver_attribute_returns_passed_value(self):
        """name_resolver 属性で渡した値を取得できる。"""
        name_resolver = _make_name_resolver()
        ctx = ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=None,
        )
        result = ctx.name_resolver
        assert result is name_resolver

    def test_item_repository_attribute_returns_passed_value(self):
        """item_repository 属性で渡した値を取得できる。"""
        name_resolver = _make_name_resolver()
        item_repository = MagicMock()
        ctx = ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=item_repository,
        )
        result = ctx.item_repository
        assert result is item_repository


class TestObservationFormatterContextImmutability:
    """ObservationFormatterContext の読み取り専用（frozen）のテスト"""

    def test_raises_when_assigning_to_name_resolver(self):
        """name_resolver に代入すると FrozenInstanceError。"""
        ctx = ObservationFormatterContext(
            name_resolver=_make_name_resolver(),
            item_repository=None,
        )
        with pytest.raises(FrozenInstanceError):
            ctx.name_resolver = MagicMock()

    def test_raises_when_assigning_to_item_repository(self):
        """item_repository に代入すると FrozenInstanceError。"""
        ctx = ObservationFormatterContext(
            name_resolver=_make_name_resolver(),
            item_repository=None,
        )
        with pytest.raises(FrozenInstanceError):
            ctx.item_repository = MagicMock()

    def test_raises_when_assigning_new_attribute(self):
        """存在しない属性に代入すると FrozenInstanceError。"""
        ctx = ObservationFormatterContext(
            name_resolver=_make_name_resolver(),
            item_repository=None,
        )
        with pytest.raises(FrozenInstanceError):
            ctx.new_attr = "value"  # type: ignore[attr-defined]


class TestObservationFormatterContextEquality:
    """ObservationFormatterContext の同値性のテスト"""

    def test_equal_when_same_name_resolver_and_item_repository(self):
        """同じ name_resolver と item_repository なら同値。"""
        name_resolver = _make_name_resolver()
        item_repository = MagicMock()
        ctx1 = ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=item_repository,
        )
        ctx2 = ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=item_repository,
        )
        assert ctx1 == ctx2

    def test_equal_when_both_item_repository_none(self):
        """両方 item_repository が None なら同値。"""
        name_resolver = _make_name_resolver()
        ctx1 = ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=None,
        )
        ctx2 = ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=None,
        )
        assert ctx1 == ctx2

    def test_not_equal_when_different_item_repository(self):
        """item_repository が異なると同値でない。"""
        name_resolver = _make_name_resolver()
        ctx1 = ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=MagicMock(),
        )
        ctx2 = ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=MagicMock(),
        )
        assert ctx1 != ctx2

    def test_not_equal_when_different_name_resolver(self):
        """name_resolver が異なると同値でない。"""
        ctx1 = ObservationFormatterContext(
            name_resolver=_make_name_resolver(),
            item_repository=None,
        )
        ctx2 = ObservationFormatterContext(
            name_resolver=_make_name_resolver(),
            item_repository=None,
        )
        assert ctx1 != ctx2


class TestObservationFormatterContextIntegration:
    """ObservationFormatterContext の統合テスト"""

    def test_context_name_resolver_returns_fallback_when_no_repos(self):
        """リポジトリ未設定の name_resolver でもフォールバックが返る。"""
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId

        name_resolver = _make_name_resolver()
        ctx = ObservationFormatterContext(
            name_resolver=name_resolver,
            item_repository=None,
        )
        # フォールバックラベルが返ることを確認
        assert ctx.name_resolver.player_name(PlayerId(999)) == "不明なプレイヤー"
        assert ctx.name_resolver.spot_name(SpotId(1)) == "不明なスポット"

    def test_observation_formatter_creates_valid_context(self):
        """ObservationFormatter が有効な context を生成する。"""
        from ai_rpg_world.application.observation.services.observation_formatter import (
            ObservationFormatter,
        )

        formatter = ObservationFormatter()
        ctx = formatter._context
        assert isinstance(ctx, ObservationFormatterContext)
        assert ctx.name_resolver is formatter._name_resolver
        assert ctx.item_repository is None

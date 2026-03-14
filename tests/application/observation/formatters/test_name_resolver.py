"""ObservationNameResolver の単体テスト（例外・フォールバック）。"""

import pytest

from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
    FALLBACK_ITEM_LABEL,
    FALLBACK_NPC_LABEL,
    FALLBACK_SNS_USER_LABEL,
)
from ai_rpg_world.domain.item.exception.item_exception import ItemInstanceIdValidationException
from ai_rpg_world.domain.sns.exception import UserIdValidationException
from ai_rpg_world.domain.world.exception.map_exception import WorldObjectIdValidationException


class TestObservationNameResolverFallbackWhenNoRepos:
    """リポジトリ未設定時のフォールバックテスト"""

    @pytest.fixture
    def resolver(self) -> ObservationNameResolver:
        """全リポジトリなしの resolver。"""
        return ObservationNameResolver()

    def test_item_spec_name_returns_fallback_when_no_repo(self, resolver: ObservationNameResolver):
        """item_spec_repository なしではフォールバックを返す。"""
        assert resolver.item_spec_name(1) == FALLBACK_ITEM_LABEL

    def test_npc_name_returns_fallback_when_no_repo(self, resolver: ObservationNameResolver):
        """monster_repository なしではフォールバックを返す。"""
        assert resolver.npc_name(1) == FALLBACK_NPC_LABEL

    def test_sns_user_display_name_returns_fallback_when_no_repo(
        self, resolver: ObservationNameResolver
    ):
        """sns_user_repository なしではフォールバックを返す。"""
        assert resolver.sns_user_display_name(1) == FALLBACK_SNS_USER_LABEL


class TestObservationNameResolverExceptionFallback:
    """不正値時にフォールバックを返すテスト（具体的な例外を捕捉）"""

    @pytest.fixture
    def resolver(self) -> ObservationNameResolver:
        """item_spec_repository あり（中身は空でも可）の resolver。"""
        return ObservationNameResolver(item_spec_repository=object())

    def test_item_spec_name_invalid_value_returns_fallback(
        self, resolver: ObservationNameResolver
    ):
        """ItemSpecId が不正（0以下）のときフォールバックを返す。"""
        result = resolver.item_spec_name(0)
        assert result == FALLBACK_ITEM_LABEL

    def test_item_spec_name_negative_value_returns_fallback(
        self, resolver: ObservationNameResolver
    ):
        """ItemSpecId が負のときフォールバックを返す。"""
        result = resolver.item_spec_name(-1)
        assert result == FALLBACK_ITEM_LABEL


class TestObservationNameResolverNpcExceptionFallback:
    """npc_name の例外フォールバックテスト"""

    @pytest.fixture
    def resolver(self) -> ObservationNameResolver:
        """monster_repository ありの resolver。"""
        return ObservationNameResolver(monster_repository=object())

    def test_npc_name_invalid_value_returns_fallback(self, resolver: ObservationNameResolver):
        """WorldObjectId が不正（0以下）のときフォールバックを返す。"""
        result = resolver.npc_name(0)
        assert result == FALLBACK_NPC_LABEL

    def test_npc_name_negative_value_returns_fallback(self, resolver: ObservationNameResolver):
        """WorldObjectId が負のときフォールバックを返す。"""
        result = resolver.npc_name(-1)
        assert result == FALLBACK_NPC_LABEL


class TestObservationNameResolverSnsUserExceptionFallback:
    """sns_user_display_name の例外フォールバックテスト"""

    @pytest.fixture
    def resolver(self) -> ObservationNameResolver:
        """sns_user_repository ありの resolver。"""
        return ObservationNameResolver(sns_user_repository=object())

    def test_sns_user_display_name_invalid_value_returns_fallback(
        self, resolver: ObservationNameResolver
    ):
        """UserId が不正（0以下）のときフォールバックを返す。"""
        result = resolver.sns_user_display_name(0)
        assert result == FALLBACK_SNS_USER_LABEL

    def test_sns_user_display_name_negative_value_returns_fallback(
        self, resolver: ObservationNameResolver
    ):
        """UserId が負のときフォールバックを返す。"""
        result = resolver.sns_user_display_name(-1)
        assert result == FALLBACK_SNS_USER_LABEL

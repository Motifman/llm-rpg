"""ObservationNameResolver の単体テスト（正常・例外・フォールバックを網羅）。"""

import pytest
from unittest.mock import Mock
from types import SimpleNamespace

from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
    FALLBACK_GUILD_LABEL,
    FALLBACK_ITEM_LABEL,
    FALLBACK_MONSTER_LABEL,
    FALLBACK_NPC_LABEL,
    FALLBACK_PLAYER_LABEL,
    FALLBACK_SHOP_LABEL,
    FALLBACK_SKILL_LABEL,
    FALLBACK_SNS_USER_LABEL,
    FALLBACK_SPOT_LABEL,
)
from ai_rpg_world.domain.item.exception.item_exception import ItemInstanceIdValidationException
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.sns.exception import UserIdValidationException
from ai_rpg_world.domain.world.exception.map_exception import WorldObjectIdValidationException
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


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

    def test_spot_name_returns_fallback_when_no_repo(self, resolver: ObservationNameResolver):
        """spot_repository なしではフォールバックを返す。"""
        assert resolver.spot_name(SpotId(1)) == FALLBACK_SPOT_LABEL

    def test_player_name_returns_fallback_when_no_repo(self, resolver: ObservationNameResolver):
        """player_profile_repository なしではフォールバックを返す。"""
        assert resolver.player_name(PlayerId(1)) == FALLBACK_PLAYER_LABEL


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


class TestObservationNameResolverNormalCase:
    """リポジトリが有効なデータを返す正常系テスト"""

    def test_spot_name_returns_spot_name_when_repo_has_spot(self):
        """spot_repository がスポットを返す場合、その名前を返す。"""
        spot = SimpleNamespace(name="ダンジョン入口")
        spot_repo = Mock(find_by_id=Mock(return_value=spot))
        resolver = ObservationNameResolver(spot_repository=spot_repo)
        assert resolver.spot_name(SpotId(1)) == "ダンジョン入口"

    def test_spot_name_returns_fallback_when_repo_returns_none(self):
        """spot_repository が None を返す場合はフォールバック。"""
        spot_repo = Mock(find_by_id=Mock(return_value=None))
        resolver = ObservationNameResolver(spot_repository=spot_repo)
        assert resolver.spot_name(SpotId(1)) == FALLBACK_SPOT_LABEL

    def test_player_name_returns_profile_name_when_repo_has_profile(self):
        """player_profile_repository がプロフィールを返す場合、その名前を返す。"""
        profile = SimpleNamespace(name=SimpleNamespace(value="勇者"))
        profile_repo = Mock(find_by_id=Mock(return_value=profile))
        resolver = ObservationNameResolver(player_profile_repository=profile_repo)
        assert resolver.player_name(PlayerId(1)) == "勇者"

    def test_player_name_returns_fallback_when_profile_has_no_name(self):
        """プロフィールに name 属性がない場合はフォールバック。"""
        profile = SimpleNamespace()
        profile_repo = Mock(find_by_id=Mock(return_value=profile))
        resolver = ObservationNameResolver(player_profile_repository=profile_repo)
        assert resolver.player_name(PlayerId(1)) == FALLBACK_PLAYER_LABEL

    def test_item_spec_name_returns_spec_name_when_repo_has_spec(self):
        """item_spec_repository がスペックを返す場合、その名前を返す。"""
        spec = SimpleNamespace(name="鋼の剣")
        spec_repo = Mock(find_by_id=Mock(return_value=spec))
        resolver = ObservationNameResolver(item_spec_repository=spec_repo)
        assert resolver.item_spec_name(1) == "鋼の剣"

    def test_item_instance_name_returns_spec_name_when_repo_has_item(self):
        """item_repository がアイテムを返す場合、そのスペック名を返す。"""
        item = SimpleNamespace(item_spec=SimpleNamespace(name="魔法の杖"))
        item_repo = Mock(find_by_id=Mock(return_value=item))
        resolver = ObservationNameResolver(item_repository=item_repo)
        assert resolver.item_instance_name(1) == "魔法の杖"

    def test_shop_name_returns_shop_name_when_repo_has_shop(self):
        """shop_repository がショップを返す場合、その名前を返す。"""
        shop = SimpleNamespace(name="武器屋")
        shop_repo = Mock(find_by_id=Mock(return_value=shop))
        resolver = ObservationNameResolver(shop_repository=shop_repo)
        assert resolver.shop_name(1) == "武器屋"

    def test_guild_name_returns_guild_name_when_repo_has_guild(self):
        """guild_repository がギルドを返す場合、その名前を返す。"""
        guild = SimpleNamespace(name="冒険者ギルド")
        guild_repo = Mock(find_by_id=Mock(return_value=guild))
        resolver = ObservationNameResolver(guild_repository=guild_repo)
        assert resolver.guild_name(1) == "冒険者ギルド"

    def test_skill_name_returns_spec_name_when_repo_has_spec(self):
        """skill_spec_repository がスペックを返す場合、その名前を返す。"""
        spec = SimpleNamespace(name="ファイアボール")
        spec_repo = Mock(find_by_id=Mock(return_value=spec))
        resolver = ObservationNameResolver(skill_spec_repository=spec_repo)
        assert resolver.skill_name(1) == "ファイアボール"

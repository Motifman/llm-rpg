import pytest
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope
from ai_rpg_world.domain.quest.exception.quest_exception import QuestScopeValidationException
from ai_rpg_world.domain.quest.enum.quest_enum import QuestScopeType
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestQuestScope:
    """QuestScope値オブジェクトのテスト"""

    def test_public_scope(self):
        """公開スコープが正しく作成されること"""
        scope = QuestScope.public_scope()
        assert scope.scope_type == QuestScopeType.PUBLIC
        assert scope.target_player_id is None
        assert scope.guild_id is None
        assert scope.is_public() is True
        assert scope.is_direct() is False
        assert scope.is_guild() is False

    def test_direct_scope(self):
        """直接スコープが正しく作成されること"""
        target = PlayerId(1)
        scope = QuestScope.direct_scope(target)
        assert scope.scope_type == QuestScopeType.DIRECT
        assert scope.target_player_id == target
        assert scope.guild_id is None
        assert scope.is_direct() is True
        assert scope.is_public() is False

    def test_guild_scope(self):
        """ギルドスコープが正しく作成されること"""
        scope = QuestScope.guild_scope(10)
        assert scope.scope_type == QuestScopeType.GUILD_MEMBERS
        assert scope.guild_id == 10
        assert scope.target_player_id is None
        assert scope.is_guild() is True

    def test_direct_scope_without_target_raises(self):
        """DIRECTでtarget_player_idなしは例外"""
        with pytest.raises(QuestScopeValidationException):
            QuestScope(scope_type=QuestScopeType.DIRECT, target_player_id=None)

    def test_guild_scope_without_guild_id_raises(self):
        """GUILD_MEMBERSでguild_idなしは例外"""
        with pytest.raises(QuestScopeValidationException):
            QuestScope(scope_type=QuestScopeType.GUILD_MEMBERS, guild_id=None)

    def test_public_scope_with_extra_raises(self):
        """PUBLICでtarget_player_idやguild_idがあると例外"""
        with pytest.raises(QuestScopeValidationException):
            QuestScope(
                scope_type=QuestScopeType.PUBLIC,
                target_player_id=PlayerId(1),
            )
        with pytest.raises(QuestScopeValidationException):
            QuestScope(scope_type=QuestScopeType.PUBLIC, guild_id=1)

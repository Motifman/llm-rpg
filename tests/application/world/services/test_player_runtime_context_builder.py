"""PlayerRuntimeContextBuilder のテスト。正常・例外を網羅する。"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world.services.player_runtime_context_builder import (
    PlayerRuntimeContextBuilder,
)
from ai_rpg_world.application.world.services.player_supplemental_context_builder import (
    PlayerSupplementalContextBuilder,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


class TestPlayerRuntimeContextBuilderDelegation:
    """PlayerSupplementalContextBuilder への委譲が正しく行われることを検証する。"""

    def test_build_inventory_items_delegates_to_supplemental_builder(self):
        """build_inventory_items が PlayerSupplementalContextBuilder に委譲すること"""
        supplemental = MagicMock(spec=PlayerSupplementalContextBuilder)
        supplemental.build_inventory_items.return_value = []
        builder = PlayerRuntimeContextBuilder(supplemental_context_builder=supplemental)

        result = builder.build_inventory_items(PlayerId(1))

        supplemental.build_inventory_items.assert_called_once_with(PlayerId(1))
        assert result == []

    def test_build_attention_level_options_returns_three_options(self):
        """build_attention_level_options が3つの注意レベルオプションを返すこと"""
        builder = PlayerRuntimeContextBuilder()
        result = builder.build_attention_level_options()

        assert len(result) == 3
        values = [opt.value for opt in result]
        assert AttentionLevel.FULL.value in values
        assert AttentionLevel.FILTER_SOCIAL.value in values
        assert AttentionLevel.IGNORE.value in values

    def test_build_active_quest_ids_returns_empty_when_no_quest_repo(self):
        """quest_repository が None の場合、build_active_quest_ids は空リストを返すこと"""
        builder = PlayerRuntimeContextBuilder()
        result = builder.build_active_quest_ids(player_id=1)
        assert result == []

    def test_build_guild_ids_returns_empty_when_no_guild_repo(self):
        """guild_repository が None の場合、build_guild_ids は空リストを返すこと"""
        builder = PlayerRuntimeContextBuilder()
        result = builder.build_guild_ids(player_id=1)
        assert result == []

    def test_build_usable_skills_returns_empty_when_no_skill_repo(self):
        """skill_loadout_repository が None の場合、build_usable_skills は空リストを返すこと"""
        builder = PlayerRuntimeContextBuilder()
        result = builder.build_usable_skills(player_id=1)
        assert result == []

    def test_build_awakened_action_returns_none_when_no_skill_repo(self):
        """skill_loadout_repository が None の場合、build_awakened_action は None を返すこと"""
        builder = PlayerRuntimeContextBuilder()
        result = builder.build_awakened_action(player_id=1)
        assert result is None

    def test_can_destroy_placeable_delegates_correctly(self):
        """can_destroy_placeable が物理マップとプレイヤーIDで委譲先を呼ぶこと"""
        supplemental = MagicMock(spec=PlayerSupplementalContextBuilder)
        supplemental.can_destroy_placeable.return_value = False
        builder = PlayerRuntimeContextBuilder(supplemental_context_builder=supplemental)

        physical_map = MagicMock()
        result = builder.can_destroy_placeable(physical_map, player_id=1)

        supplemental.can_destroy_placeable.assert_called_once_with(physical_map, 1)
        assert result is False

    def test_constructor_creates_supplemental_builder_when_not_provided(self):
        """supplemental_context_builder を渡さない場合、内部で PlayerSupplementalContextBuilder を構築すること"""
        builder = PlayerRuntimeContextBuilder(guild_repository=MagicMock())
        guild = MagicMock()
        guild.guild_id.value = 1
        guild.name = "Test Guild"
        guild.location_area_id.value = 10
        guild.description = "Desc"
        guild.members = {}
        builder._supplemental_context_builder._guild_repository.find_guilds_by_player_id = MagicMock(
            return_value=[]
        )
        result = builder.build_guild_ids(player_id=1)
        assert result == []

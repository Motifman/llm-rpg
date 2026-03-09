"""PlayerSupplementalContextBuilder のテスト。"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world.services.player_supplemental_context_builder import (
    PlayerSupplementalContextBuilder,
)
from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.guild.value_object.guild_membership import GuildMembership
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.shop.aggregate.shop_aggregate import ShopAggregate
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from datetime import datetime


def _make_guild(
    guild_id: int,
    spot_id: int,
    location_area_id: int,
    name: str,
    description: str,
    player_id: int,
) -> GuildAggregate:
    """テスト用ギルドを作成（create_guild 相当の手動構築）"""
    membership = GuildMembership(
        player_id=PlayerId(player_id),
        role=GuildRole.LEADER,
        joined_at=datetime.now(),
        contribution_points=0,
    )
    return GuildAggregate(
        guild_id=GuildId(guild_id),
        spot_id=SpotId(spot_id),
        location_area_id=LocationAreaId(location_area_id),
        name=name,
        description=description,
        members={PlayerId(player_id): membership},
    )


def _make_shop(shop_id: int, spot_id: int, location_area_id: int, name: str, description: str) -> ShopAggregate:
    """テスト用ショップを作成"""
    return ShopAggregate(
        shop_id=ShopId(shop_id),
        spot_id=SpotId(spot_id),
        location_area_id=LocationAreaId(location_area_id),
        owner_ids={PlayerId(1)},
        name=name,
        description=description,
        listings={},
    )


class TestPlayerSupplementalContextBuilderGuildDescription:
    """build_guild_memberships の description 設定テスト"""

    def test_build_guild_memberships_sets_description_when_player_in_same_area(self):
        """プレイヤーがギルドの LocationArea 内にいる場合、description が設定される"""
        guild_repo = MagicMock()
        guild = _make_guild(1, 1, 10, "冒険者ギルド", "一緒に冒険しましょう", player_id=1)
        guild_repo.find_guilds_by_player_id.return_value = [guild]

        builder = PlayerSupplementalContextBuilder(guild_repository=guild_repo)
        result = builder.build_guild_memberships(player_id=1, player_area_id=10)

        assert len(result) == 1
        assert result[0].guild_name == "冒険者ギルド"
        assert result[0].description == "一緒に冒険しましょう"

    def test_build_guild_memberships_omit_description_when_player_in_different_area(self):
        """プレイヤーがギルドの LocationArea 外にいる場合、description は None"""
        guild_repo = MagicMock()
        guild = _make_guild(1, 1, 10, "冒険者ギルド", "一緒に冒険しましょう", player_id=1)
        guild_repo.find_guilds_by_player_id.return_value = [guild]

        builder = PlayerSupplementalContextBuilder(guild_repository=guild_repo)
        result = builder.build_guild_memberships(player_id=1, player_area_id=99)

        assert len(result) == 1
        assert result[0].guild_name == "冒険者ギルド"
        assert result[0].description is None

    def test_build_guild_memberships_omit_description_when_player_area_id_is_none(self):
        """player_area_id が None の場合、description は None"""
        guild_repo = MagicMock()
        guild = _make_guild(1, 1, 10, "冒険者ギルド", "一緒に冒険しましょう", player_id=1)
        guild_repo.find_guilds_by_player_id.return_value = [guild]

        builder = PlayerSupplementalContextBuilder(guild_repository=guild_repo)
        result = builder.build_guild_memberships(player_id=1, player_area_id=None)

        assert len(result) == 1
        assert result[0].description is None

    def test_build_guild_memberships_mixed_areas_only_matching_gets_description(self):
        """複数ギルド所属時、現在地と一致するギルドのみ description が設定される"""
        guild_repo = MagicMock()
        g1 = _make_guild(1, 1, 10, "町のギルド", "町の説明", player_id=1)
        g2 = _make_guild(2, 2, 20, "港のギルド", "港の説明", player_id=1)
        guild_repo.find_guilds_by_player_id.return_value = [g1, g2]

        builder = PlayerSupplementalContextBuilder(guild_repository=guild_repo)
        result = builder.build_guild_memberships(player_id=1, player_area_id=20)

        assert len(result) == 2
        town = next(m for m in result if m.guild_name == "町のギルド")
        port = next(m for m in result if m.guild_name == "港のギルド")
        assert town.description is None
        assert port.description == "港の説明"

    def test_build_guild_memberships_no_repo_returns_empty(self):
        """guild_repository が None の場合、空リストを返す"""
        builder = PlayerSupplementalContextBuilder(guild_repository=None)
        result = builder.build_guild_memberships(player_id=1, player_area_id=10)
        assert result == []


class TestPlayerSupplementalContextBuilderShopDescription:
    """build_nearby_shops の description 設定テスト"""

    def test_build_nearby_shops_sets_description(self):
        """nearby_shops にショップの description が設定される"""
        shop_repo = MagicMock()
        shop = _make_shop(1, 1, 10, "ポーション屋", "様々な薬を扱う店です")
        shop_repo.find_by_spot_and_location.return_value = shop

        builder = PlayerSupplementalContextBuilder(shop_repository=shop_repo)
        result = builder.build_nearby_shops(spot_id=1, location_area_id=10)

        assert len(result) == 1
        assert result[0].shop_name == "ポーション屋"
        assert result[0].description == "様々な薬を扱う店です"

    def test_build_nearby_shops_empty_description_becomes_none(self):
        """ショップの description が空文字の場合、None になる"""
        shop_repo = MagicMock()
        shop = _make_shop(1, 1, 10, "名無し店", "")
        shop_repo.find_by_spot_and_location.return_value = shop

        builder = PlayerSupplementalContextBuilder(shop_repository=shop_repo)
        result = builder.build_nearby_shops(spot_id=1, location_area_id=10)

        assert len(result) == 1
        assert result[0].description is None

    def test_build_nearby_shops_no_shop_returns_empty(self):
        """ショップが存在しない場合、空リストを返す"""
        shop_repo = MagicMock()
        shop_repo.find_by_spot_and_location.return_value = None

        builder = PlayerSupplementalContextBuilder(shop_repository=shop_repo)
        result = builder.build_nearby_shops(spot_id=1, location_area_id=10)

        assert result == []

"""PlayerSupplementalContextBuilder のテスト。"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.trade.exceptions import PersonalTradeQueryApplicationException
from ai_rpg_world.application.world.contracts.dtos import (
    GuildMemberSummaryDto,
    VisibleObjectDto,
)
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
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ChestComponent
from ai_rpg_world.domain.world.exception.map_exception import (
    NotAnActorException,
    ObjectNotFoundException,
    WorldObjectIdValidationException,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from datetime import datetime


def _make_guild(
    guild_id: int,
    spot_id: int,
    location_area_id: int,
    name: str,
    description: str,
    player_id: int,
    members_dict: dict | None = None,
) -> GuildAggregate:
    """テスト用ギルドを作成（create_guild 相当の手動構築）"""
    members_dict = members_dict or {}
    if not members_dict:
        membership = GuildMembership(
            player_id=PlayerId(player_id),
            role=GuildRole.LEADER,
            joined_at=datetime.now(),
            contribution_points=0,
        )
        members_dict = {PlayerId(player_id): membership}
    return GuildAggregate(
        guild_id=GuildId(guild_id),
        spot_id=SpotId(spot_id),
        location_area_id=LocationAreaId(location_area_id),
        name=name,
        description=description,
        members=members_dict,
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
        result = builder.build_guild_memberships(player_id=1, player_area_ids=[10])

        assert len(result) == 1
        assert result[0].guild_name == "冒険者ギルド"
        assert result[0].description == "一緒に冒険しましょう"

    def test_build_guild_memberships_omit_description_when_player_in_different_area(self):
        """プレイヤーがギルドの LocationArea 外にいる場合、description は None"""
        guild_repo = MagicMock()
        guild = _make_guild(1, 1, 10, "冒険者ギルド", "一緒に冒険しましょう", player_id=1)
        guild_repo.find_guilds_by_player_id.return_value = [guild]

        builder = PlayerSupplementalContextBuilder(guild_repository=guild_repo)
        result = builder.build_guild_memberships(player_id=1, player_area_ids=[99])

        assert len(result) == 1
        assert result[0].guild_name == "冒険者ギルド"
        assert result[0].description is None

    def test_build_guild_memberships_omit_description_when_player_area_id_is_none(self):
        """player_area_id が None の場合、description は None"""
        guild_repo = MagicMock()
        guild = _make_guild(1, 1, 10, "冒険者ギルド", "一緒に冒険しましょう", player_id=1)
        guild_repo.find_guilds_by_player_id.return_value = [guild]

        builder = PlayerSupplementalContextBuilder(guild_repository=guild_repo)
        result = builder.build_guild_memberships(player_id=1, player_area_ids=None)

        assert len(result) == 1
        assert result[0].description is None

    def test_build_guild_memberships_mixed_areas_only_matching_gets_description(self):
        """複数ギルド所属時、現在地と一致するギルドのみ description が設定される"""
        guild_repo = MagicMock()
        g1 = _make_guild(1, 1, 10, "町のギルド", "町の説明", player_id=1)
        g2 = _make_guild(2, 2, 20, "港のギルド", "港の説明", player_id=1)
        guild_repo.find_guilds_by_player_id.return_value = [g1, g2]

        builder = PlayerSupplementalContextBuilder(guild_repository=guild_repo)
        result = builder.build_guild_memberships(player_id=1, player_area_ids=[20])

        assert len(result) == 2
        town = next(m for m in result if m.guild_name == "町のギルド")
        port = next(m for m in result if m.guild_name == "港のギルド")
        assert town.description is None
        assert port.description == "港の説明"

    def test_build_guild_memberships_no_repo_returns_empty(self):
        """guild_repository が None の場合、空リストを返す"""
        builder = PlayerSupplementalContextBuilder(guild_repository=None)
        result = builder.build_guild_memberships(player_id=1, player_area_ids=[10])
        assert result == []


class TestPlayerSupplementalContextBuilderShopDescription:
    """build_nearby_shops の description 設定テスト"""

    def test_build_nearby_shops_sets_description(self):
        """nearby_shops にショップの description が設定される"""
        shop_repo = MagicMock()
        shop = _make_shop(1, 1, 10, "ポーション屋", "様々な薬を扱う店です")
        shop_repo.find_by_spot_and_location.return_value = shop

        builder = PlayerSupplementalContextBuilder(shop_repository=shop_repo)
        result = builder.build_nearby_shops(spot_id=1, location_area_ids=[10])

        assert len(result) == 1
        assert result[0].shop_name == "ポーション屋"
        assert result[0].description == "様々な薬を扱う店です"

    def test_build_nearby_shops_empty_description_becomes_none(self):
        """ショップの description が空文字の場合、None になる"""
        shop_repo = MagicMock()
        shop = _make_shop(1, 1, 10, "名無し店", "")
        shop_repo.find_by_spot_and_location.return_value = shop

        builder = PlayerSupplementalContextBuilder(shop_repository=shop_repo)
        result = builder.build_nearby_shops(spot_id=1, location_area_ids=[10])

        assert len(result) == 1
        assert result[0].description is None

    def test_build_nearby_shops_no_shop_returns_empty(self):
        """ショップが存在しない場合、空リストを返す"""
        shop_repo = MagicMock()
        shop_repo.find_by_spot_and_location.return_value = None

        builder = PlayerSupplementalContextBuilder(shop_repository=shop_repo)
        result = builder.build_nearby_shops(spot_id=1, location_area_ids=[10])

        assert result == []

    def test_build_nearby_shops_multiple_areas_returns_multiple_shops(self):
        """location_area_ids に複数指定したとき、各エリアのショップがマージされ重複なく返る"""
        shop_repo = MagicMock()
        shop1 = _make_shop(1, 1, 10, "ポーション屋", "薬の店")
        shop2 = _make_shop(2, 1, 20, "武具屋", "武具の店")
        shop_repo.find_by_spot_and_location.side_effect = lambda spot, loc: (
            shop1 if loc.value == 10 else (shop2 if loc.value == 20 else None)
        )

        builder = PlayerSupplementalContextBuilder(shop_repository=shop_repo)
        result = builder.build_nearby_shops(spot_id=1, location_area_ids=[10, 20])

        assert len(result) == 2
        names = [s.shop_name for s in result]
        assert "ポーション屋" in names
        assert "武具屋" in names


class TestPlayerSupplementalContextBuilderGuildMembers:
    """Phase 2: GuildMembershipSummaryDto.members のテスト"""

    def test_build_guild_memberships_sets_members_for_leader(self):
        """リーダーの場合、members が設定される"""
        members_dict = {
            PlayerId(1): GuildMembership(
                player_id=PlayerId(1),
                role=GuildRole.LEADER,
                joined_at=datetime.now(),
                contribution_points=0,
            ),
            PlayerId(2): GuildMembership(
                player_id=PlayerId(2),
                role=GuildRole.MEMBER,
                joined_at=datetime.now(),
                contribution_points=0,
            ),
        }
        guild = _make_guild(1, 1, 10, "テストギルド", "説明", player_id=1, members_dict=members_dict)
        guild_repo = MagicMock()
        guild_repo.find_guilds_by_player_id.return_value = [guild]

        from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
            PlayerProfileAggregate,
        )
        from ai_rpg_world.domain.player.value_object.player_name import PlayerName
        from ai_rpg_world.domain.player.enum.player_enum import Role
        from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
            InMemoryDataStore,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
            InMemoryPlayerProfileRepository,
        )

        data_store = InMemoryDataStore()
        profile_repo = InMemoryPlayerProfileRepository(data_store)
        profile_repo.save(
            PlayerProfileAggregate.create(
                player_id=PlayerId(1),
                name=PlayerName("Alice"),
                role=Role.CITIZEN,
            )
        )
        profile_repo.save(
            PlayerProfileAggregate.create(
                player_id=PlayerId(2),
                name=PlayerName("Bob"),
                role=Role.CITIZEN,
            )
        )

        builder = PlayerSupplementalContextBuilder(
            guild_repository=guild_repo,
            player_profile_repository=profile_repo,
        )
        result = builder.build_guild_memberships(player_id=1, player_area_ids=[10])

        assert len(result) == 1
        assert result[0].members is not None
        assert len(result[0].members) == 2
        member_ids = {m.player_id for m in result[0].members}
        assert member_ids == {1, 2}
        names = {m.player_name for m in result[0].members}
        assert "Alice" in names
        assert "Bob" in names

    def test_build_guild_memberships_sets_members_for_officer(self):
        """オフィサーの場合、members が設定される"""
        members_dict = {
            PlayerId(1): GuildMembership(
                player_id=PlayerId(1),
                role=GuildRole.OFFICER,
                joined_at=datetime.now(),
                contribution_points=0,
            ),
        }
        guild = _make_guild(1, 1, 10, "テストギルド", "説明", player_id=1, members_dict=members_dict)
        guild_repo = MagicMock()
        guild_repo.find_guilds_by_player_id.return_value = [guild]

        builder = PlayerSupplementalContextBuilder(
            guild_repository=guild_repo,
            player_profile_repository=None,
        )
        result = builder.build_guild_memberships(player_id=1, player_area_ids=[10])

        assert len(result) == 1
        assert result[0].members is not None
        assert len(result[0].members) == 1
        assert result[0].members[0].player_name == "プレイヤー1"

    def test_build_guild_memberships_members_none_for_member_role(self):
        """メンバーのみの役職の場合、members は None"""
        members_dict = {
            PlayerId(1): GuildMembership(
                player_id=PlayerId(1),
                role=GuildRole.LEADER,
                joined_at=datetime.now(),
                contribution_points=0,
            ),
            PlayerId(2): GuildMembership(
                player_id=PlayerId(2),
                role=GuildRole.MEMBER,
                joined_at=datetime.now(),
                contribution_points=0,
            ),
        }
        guild = _make_guild(1, 1, 10, "テストギルド", "説明", player_id=1, members_dict=members_dict)
        guild_repo = MagicMock()
        guild_repo.find_guilds_by_player_id.return_value = [guild]

        builder = PlayerSupplementalContextBuilder(guild_repository=guild_repo)
        result = builder.build_guild_memberships(player_id=2, player_area_ids=[10])

        assert len(result) == 1
        assert result[0].members is None


class TestPlayerSupplementalContextBuilderLocationOverlap:
    """Phase 1: ロケーション重なり対応のテスト"""

    def test_build_guild_memberships_multiple_player_areas_matching_second_gets_description(self):
        """player_area_ids に複数指定し、2番目がギルドの area と一致する場合 description が設定される"""
        guild_repo = MagicMock()
        guild = _make_guild(1, 1, 20, "港のギルド", "港の説明", player_id=1)
        guild_repo.find_guilds_by_player_id.return_value = [guild]

        builder = PlayerSupplementalContextBuilder(guild_repository=guild_repo)
        result = builder.build_guild_memberships(player_id=1, player_area_ids=[10, 20])

        assert len(result) == 1
        assert result[0].description == "港の説明"


def _visible_chest(object_id: int, display_name: str = "宝箱") -> VisibleObjectDto:
    """チェスト用の VisibleObjectDto を作成"""
    return VisibleObjectDto(
        object_id=object_id,
        object_type="chest",
        x=0,
        y=0,
        z=0,
        distance=1,
        display_name=display_name,
        object_kind="chest",
        can_take_from_chest=True,
    )


class TestPlayerSupplementalContextBuilderBuildChestItems:
    """build_chest_items の例外処理テスト"""

    def test_build_chest_items_skips_chest_on_object_not_found_continues_with_others(self):
        """ObjectNotFoundException のチェストはスキップし、他は処理継続する"""
        from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
        from ai_rpg_world.domain.world.value_object.coordinate import Coordinate

        item_repo = MagicMock()
        mock_item = MagicMock()
        mock_item.item_instance_id = ItemInstanceId(100)
        mock_item.item_spec.name = "ポーション"
        mock_item.quantity = 1
        item_repo.find_by_id.return_value = mock_item

        physical_map = MagicMock()
        chest_component = ChestComponent(item_ids=[ItemInstanceId(100)])
        chest_obj = WorldObject(
            object_id=WorldObjectId.create(2),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.CHEST,
            component=chest_component,
        )

        def get_object_side_effect(woid):
            if woid.value == 1:
                raise ObjectNotFoundException("not found")
            if woid.value == 2:
                return chest_obj
            raise ObjectNotFoundException(f"unknown: {woid}")

        physical_map.get_object.side_effect = get_object_side_effect

        visible = [
            _visible_chest(1, "消えた宝箱"),
            _visible_chest(2, "有効な宝箱"),
        ]
        builder = PlayerSupplementalContextBuilder(item_repository=item_repo)
        result = builder.build_chest_items(physical_map, visible)

        assert len(result) == 1
        assert result[0].chest_world_object_id == 2
        assert result[0].display_name == "ポーション"


class TestPlayerSupplementalContextBuilderBuildAvailableTrades:
    """build_available_trades の例外処理テスト"""

    def test_build_available_trades_returns_empty_on_personal_trade_query_exception(self):
        """PersonalTradeQueryApplicationException 時は空リストを返す"""
        trade_service = MagicMock()
        trade_service.get_personal_trades.side_effect = PersonalTradeQueryApplicationException(
            "query failed"
        )

        builder = PlayerSupplementalContextBuilder(
            personal_trade_query_service=trade_service
        )
        result = builder.build_available_trades(player_id=1)

        assert result == []

    def test_build_available_trades_propagates_unexpected_exception(self):
        """想定外の例外は伝播する"""
        trade_service = MagicMock()
        trade_service.get_personal_trades.side_effect = ValueError("unexpected")

        builder = PlayerSupplementalContextBuilder(
            personal_trade_query_service=trade_service
        )
        with pytest.raises(ValueError, match="unexpected"):
            builder.build_available_trades(player_id=1)


class TestPlayerSupplementalContextBuilderCanDestroyPlaceable:
    """can_destroy_placeable の例外処理テスト"""

    def test_can_destroy_placeable_returns_false_on_object_not_found(self):
        """ObjectNotFoundException 時は False を返す"""
        physical_map = MagicMock()
        physical_map.get_actor.side_effect = ObjectNotFoundException("not found")

        builder = PlayerSupplementalContextBuilder()
        result = builder.can_destroy_placeable(physical_map, player_id=1)

        assert result is False

    def test_can_destroy_placeable_returns_false_on_not_an_actor(self):
        """NotAnActorException 時は False を返す"""
        physical_map = MagicMock()
        physical_map.get_actor.side_effect = NotAnActorException("not actor")

        builder = PlayerSupplementalContextBuilder()
        result = builder.can_destroy_placeable(physical_map, player_id=1)

        assert result is False

    def test_can_destroy_placeable_returns_false_on_world_object_id_validation(self):
        """WorldObjectIdValidationException 時は False を返す"""
        physical_map = MagicMock()
        physical_map.get_actor.side_effect = WorldObjectIdValidationException("invalid")

        builder = PlayerSupplementalContextBuilder()
        result = builder.can_destroy_placeable(physical_map, player_id=1)

        assert result is False

    def test_can_destroy_placeable_propagates_unexpected_exception(self):
        """想定外の例外は伝播する"""
        physical_map = MagicMock()
        physical_map.get_actor.side_effect = RuntimeError("unexpected")

        builder = PlayerSupplementalContextBuilder()
        with pytest.raises(RuntimeError, match="unexpected"):
            builder.can_destroy_placeable(physical_map, player_id=1)

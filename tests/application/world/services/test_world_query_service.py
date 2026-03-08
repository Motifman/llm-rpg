"""WorldQueryService のテスト。正常・例外を網羅する。"""

import pytest
from typing import List, Dict
from unittest.mock import patch
from unittest.mock import MagicMock

from ai_rpg_world.application.conversation.contracts.dtos import (
    ConversationNodeDto,
    ConversationSessionDto,
)
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.application.world.contracts.queries import (
    GetPlayerLocationQuery,
    GetSpotContextForPlayerQuery,
    GetVisibleContextQuery,
    GetAvailableMovesQuery,
    GetPlayerCurrentStateQuery,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
)
from ai_rpg_world.application.world.exceptions.base_exception import WorldSystemErrorException
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.enum.player_enum import Role, AttentionLevel
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.entity.world_object_component import ChestComponent
from ai_rpg_world.domain.world.entity.world_object_component import InteractableComponent
from ai_rpg_world.domain.world.enum.world_enum import InteractionTypeEnum
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import InMemoryPlayerProfileRepository
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import InMemoryPhysicalMapRepository
from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import InMemorySpotRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)
from ai_rpg_world.application.world.services.gateway_based_connected_spots_provider import (
    GatewayBasedConnectedSpotsProvider,
)


class TestWorldQueryService:
    @pytest.fixture
    def setup_service(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()

        status_repo = InMemoryPlayerStatusRepository(data_store)
        profile_repo = InMemoryPlayerProfileRepository(data_store)
        phys_repo = InMemoryPhysicalMapRepository(data_store)
        spot_repo = InMemorySpotRepository(data_store)
        spot_repo.save(Spot(SpotId(1), "Default Spot", ""))
        connected_spots_provider = GatewayBasedConnectedSpotsProvider(phys_repo)

        service = WorldQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected_spots_provider,
        )
        return service, status_repo, profile_repo, phys_repo, spot_repo

    def _create_sample_status(self, player_id: int, spot_id: int = 1, x: int = 0, y: int = 0):
        exp_table = ExpTable(100, 1.5)
        return PlayerStatusAggregate(
            player_id=PlayerId(player_id),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold(1000),
            hp=Hp.create(100, 100),
            mp=Mp.create(50, 50),
            stamina=Stamina.create(100, 100),
            current_spot_id=SpotId(spot_id),
            current_coordinate=Coordinate(x, y, 0),
        )

    def _create_sample_profile(self, player_id: int, name: str = "TestPlayer"):
        return PlayerProfileAggregate.create(
            player_id=PlayerId(player_id),
            name=PlayerName(name),
            role=Role.CITIZEN,
        )

    def _create_sample_map(self, spot_id: int, width: int = 10, height: int = 10, objects: List = None):
        tiles = {}
        for x in range(width):
            for y in range(height):
                coord = Coordinate(x, y, 0)
                tiles[coord] = Tile(coord, TerrainType.grass())
        return PhysicalMapAggregate(
            spot_id=SpotId(spot_id),
            tiles=tiles,
            objects=objects or [],
        )

    def _create_player_object(self, player_id: int, x: int = 0, y: int = 0):
        return WorldObject(
            object_id=WorldObjectId.create(player_id),
            coordinate=Coordinate(x, y, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(player_id)),
        )

    # --- 正常ケース ---

    def test_get_player_location_returns_dto_when_placed(self, setup_service):
        """配置済みプレイヤーの位置が DTO で返ること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Alice"))
        status_repo.save(self._create_sample_status(player_id, spot_id, 3, 4))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id, 3, 4)]))

        result = service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert result is not None
        assert result.player_id == player_id
        assert result.player_name == "Alice"
        assert result.current_spot_id == spot_id
        assert result.x == 3
        assert result.y == 4
        assert result.z == 0

    def test_get_player_location_returns_none_when_not_placed(self, setup_service):
        """未配置の場合は None を返すこと"""
        service, status_repo, profile_repo, _, spot_repo = setup_service
        player_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id)
        status._current_spot_id = None
        status._current_coordinate = None
        status_repo.save(status)

        result = service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert result is None

    def test_get_player_location_returns_none_when_player_not_in_repo(self, setup_service):
        """プレイヤーがリポジトリに存在しない場合は None を返すこと"""
        service, _, _, _, _ = setup_service

        result = service.get_player_location(GetPlayerLocationQuery(player_id=99999))

        assert result is None

    def test_get_player_location_includes_spot_name_and_description(self, setup_service):
        """スポット名・説明が DTO に含まれること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        spot_repo.save(Spot(SpotId(spot_id), "Town Square", "A central area"))

        result = service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert result is not None
        assert result.current_spot_name == "Town Square"
        assert result.current_spot_description == "A central area"

    # --- 例外ケース ---

    def test_get_player_location_raises_player_not_found_when_profile_missing(self, setup_service):
        """プロフィールが存在しない場合に PlayerNotFoundException が発生すること"""
        service, status_repo, _, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with pytest.raises(PlayerNotFoundException) as exc_info:
            service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert exc_info.value.context.get("player_id") == player_id

    def test_get_player_location_raises_map_not_found_when_spot_missing(self, setup_service):
        """スポットが存在しない場合に MapNotFoundException が発生すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 999
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with pytest.raises(MapNotFoundException) as exc_info:
            service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert exc_info.value.context.get("spot_id") == spot_id

    def test_get_player_location_raises_world_system_error_on_unexpected_exception(self, setup_service):
        """想定外の例外時に WorldSystemErrorException が発生すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with patch.object(spot_repo, "find_by_id", side_effect=RuntimeError("unexpected")):
            with pytest.raises(WorldSystemErrorException) as exc_info:
                service.get_player_location(GetPlayerLocationQuery(player_id=player_id))
            assert exc_info.value.original_exception is not None
            assert isinstance(exc_info.value.original_exception, RuntimeError)

    # --- get_spot_context_for_player 正常ケース ---

    def test_get_spot_context_returns_spot_info_when_placed(self, setup_service):
        """配置済みプレイヤーの現在スポット情報＋接続先が SpotInfoDto で返ること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Alice"))
        status_repo.save(self._create_sample_status(player_id, spot_id, 2, 3))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id, 2, 3)]))
        spot_repo.save(Spot(SpotId(1), "Town", "A starting town"))

        result = service.get_spot_context_for_player(GetSpotContextForPlayerQuery(player_id=player_id))

        assert result is not None
        assert result.spot_id == spot_id
        assert result.name == "Town"
        assert result.description == "A starting town"
        assert result.current_player_count >= 1
        assert player_id in result.current_player_ids
        assert isinstance(result.connected_spot_ids, set)
        assert isinstance(result.connected_spot_names, set)

    def test_get_spot_context_returns_none_when_not_placed(self, setup_service):
        """未配置の場合は None を返すこと"""
        service, status_repo, profile_repo, _, spot_repo = setup_service
        player_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id)
        status._current_spot_id = None
        status._current_coordinate = None
        status_repo.save(status)

        result = service.get_spot_context_for_player(GetSpotContextForPlayerQuery(player_id=player_id))

        assert result is None

    def test_get_player_current_state_includes_extended_runtime_lists(self, setup_service):
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Alice"))
        status_repo.save(self._create_sample_status(player_id, 1, 0, 0))

        player_obj = self._create_player_object(player_id, 0, 0)
        npc_obj = WorldObject(
            object_id=WorldObjectId.create(200),
            coordinate=Coordinate(0, 1, 0),
            object_type=ObjectTypeEnum.NPC,
            component=InteractableComponent(
                interaction_type=InteractionTypeEnum.TALK,
                data={"dialogue_tree_id": 1},
            ),
        )
        chest_obj = WorldObject(
            object_id=WorldObjectId.create(210),
            coordinate=Coordinate(1, 0, 0),
            object_type=ObjectTypeEnum.CHEST,
            component=ChestComponent(is_open=True),
        )
        chest_obj.component.add_item(ItemInstanceId.create(500))
        phys_repo.save(self._create_sample_map(1, objects=[player_obj, npc_obj, chest_obj]))

        inventory_repo = MagicMock()
        inventory = MagicMock()
        inventory.max_slots = 1
        inventory.get_item_instance_id_by_slot.return_value = MagicMock(value=400)
        inventory_repo.find_by_id.return_value = inventory

        item_repo = MagicMock()
        inventory_item = MagicMock()
        inventory_item.item_instance_id.value = 400
        inventory_item.item_spec.name = "木箱"
        inventory_item.item_spec.is_placeable_item.return_value = True
        inventory_item.quantity = 1
        chest_item = MagicMock()
        chest_item.item_instance_id.value = 500
        chest_item.item_spec.name = "ポーション"
        chest_item.quantity = 2
        item_repo.find_by_id.side_effect = [inventory_item, chest_item]

        conversation_service = MagicMock()
        conversation_service.get_current_node.return_value = ConversationSessionDto(
            player_id=1,
            npc_id_value=200,
            dialogue_tree_id_value=1,
            current_node=ConversationNodeDto(
                node_id_value=1,
                text="やあ",
                choices=(("はい", 2),),
                is_terminal=False,
                has_next=False,
            ),
        )

        skill_loadout_repo = MagicMock()
        loadout = MagicMock()
        loadout.loadout_id.value = 10
        skill = MagicMock()
        skill.skill_id.value = 1001
        skill.name = "火球"
        skill.mp_cost = 5
        skill.stamina_cost = 0
        skill.hp_cost = 0
        loadout.get_current_deck.return_value = MagicMock(slots=(skill,))
        loadout.can_use_skill.return_value = True
        skill_loadout_repo.find_by_owner_id.return_value = loadout

        time_provider = MagicMock()
        time_provider.get_current_tick.return_value = MagicMock(value=100)

        extended_service = WorldQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=service._connected_spots_provider,
            player_inventory_repository=inventory_repo,
            item_repository=item_repo,
            conversation_command_service=conversation_service,
            skill_loadout_repository=skill_loadout_repo,
            game_time_provider=time_provider,
        )

        result = extended_service.get_player_current_state(
            GetPlayerCurrentStateQuery(player_id=player_id)
        )

        assert result is not None
        assert len(result.inventory_items) == 1
        assert result.inventory_items[0].display_name == "木箱"
        assert len(result.chest_items) == 1
        assert result.chest_items[0].display_name == "ポーション"
        assert result.active_conversation is not None
        assert result.active_conversation.choices[0].display_text == "はい"
        assert len(result.usable_skills) == 1
        assert result.usable_skills[0].display_name == "火球"
        assert result.attention_level_options

    def test_get_spot_context_includes_connected_spots_when_gateway_exists(self, setup_service):
        """ゲートウェイで接続されたスポットが connected_spot_ids / names に含まれること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        from ai_rpg_world.domain.world.entity.gateway import Gateway
        from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
        from ai_rpg_world.domain.world.value_object.area import RectArea

        spot_repo.save(Spot(SpotId(1), "SpotA", "First"))
        spot_repo.save(Spot(SpotId(2), "SpotB", "Second"))
        gateway = Gateway(
            GatewayId(1),
            "GateToB",
            RectArea(min_x=5, max_x=6, min_y=5, max_y=6, min_z=0, max_z=0),
            SpotId(2),
            Coordinate(0, 0, 0),
        )
        tiles = {}
        for x in range(10):
            for y in range(10):
                coord = Coordinate(x, y, 0)
                tiles[coord] = Tile(coord, TerrainType.grass())
        map1 = PhysicalMapAggregate(
            spot_id=SpotId(1),
            tiles=tiles,
            objects=[self._create_player_object(1, 0, 0)],
            gateways=[gateway],
        )
        phys_repo.save(map1)
        phys_repo.save(self._create_sample_map(2))
        profile_repo.save(self._create_sample_profile(1))
        status_repo.save(self._create_sample_status(1, 1, 0, 0))

        result = service.get_spot_context_for_player(GetSpotContextForPlayerQuery(player_id=1))

        assert result is not None
        assert 2 in result.connected_spot_ids
        assert "SpotB" in result.connected_spot_names

    def test_get_spot_context_raises_player_not_found_when_profile_missing(self, setup_service):
        """プロフィールが存在しない場合に PlayerNotFoundException が発生すること"""
        service, status_repo, _, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with pytest.raises(PlayerNotFoundException):
            service.get_spot_context_for_player(GetSpotContextForPlayerQuery(player_id=player_id))

    def test_get_spot_context_raises_map_not_found_when_spot_missing(self, setup_service):
        """スポットが存在しない場合に MapNotFoundException が発生すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 999
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with pytest.raises(MapNotFoundException):
            service.get_spot_context_for_player(GetSpotContextForPlayerQuery(player_id=player_id))

    def test_get_spot_context_raises_world_system_error_on_unexpected_exception(self, setup_service):
        """想定外の例外時に WorldSystemErrorException が発生すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with patch.object(spot_repo, "find_by_id", side_effect=RuntimeError("unexpected")):
            with pytest.raises(WorldSystemErrorException) as exc_info:
                service.get_spot_context_for_player(GetSpotContextForPlayerQuery(player_id=player_id))
            assert exc_info.value.original_exception is not None

    # --- get_visible_context 正常・例外 ---

    def test_get_visible_context_returns_dto_when_placed(self, setup_service):
        """配置済みプレイヤーの視界内オブジェクトが VisibleContextDto で返ること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Bob"))
        status_repo.save(self._create_sample_status(player_id, spot_id, 5, 5))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id, 5, 5)]))

        result = service.get_visible_context(GetVisibleContextQuery(player_id=player_id, distance=3))

        assert result is not None
        assert result.player_id == player_id
        assert result.player_name == "Bob"
        assert result.spot_id == spot_id
        assert result.center_x == 5
        assert result.center_y == 5
        assert result.view_distance == 3
        assert isinstance(result.visible_objects, list)
        assert len(result.visible_objects) >= 1
        obj = result.visible_objects[0]
        assert obj.object_type == "PLAYER"
        assert obj.distance >= 0
        assert obj.display_name == "Bob"
        assert obj.object_kind == "player"
        assert obj.direction_from_player == "ここ"
        assert obj.player_id_value == 1
        assert obj.is_self is True

    def test_get_visible_context_returns_none_when_not_placed(self, setup_service):
        """未配置の場合は None を返すこと"""
        service, status_repo, profile_repo, _, spot_repo = setup_service
        player_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id)
        status._current_spot_id = None
        status._current_coordinate = None
        status_repo.save(status)

        result = service.get_visible_context(GetVisibleContextQuery(player_id=player_id))

        assert result is None

    def test_get_visible_context_raises_player_not_found_when_profile_missing(self, setup_service):
        """プロフィールが存在しない場合に PlayerNotFoundException が発生すること"""
        service, status_repo, _, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with pytest.raises(PlayerNotFoundException):
            service.get_visible_context(GetVisibleContextQuery(player_id=player_id))

    def test_get_visible_context_raises_map_not_found_when_spot_missing(self, setup_service):
        """スポットが存在しない場合に MapNotFoundException が発生すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 999
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with pytest.raises(MapNotFoundException):
            service.get_visible_context(GetVisibleContextQuery(player_id=player_id))

    def test_get_visible_context_distance_zero_returns_center_only(self, setup_service):
        """distance=0 のとき視界内は自身のみ（または空）となること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 1, 1))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id, 1, 1)]))

        result = service.get_visible_context(GetVisibleContextQuery(player_id=player_id, distance=0))

        assert result is not None
        assert result.view_distance == 0
        assert len(result.visible_objects) >= 1

    def test_get_visible_context_excludes_object_behind_opaque_wall(self, setup_service):
        """遮蔽物の向こうにいる対象は visible_objects に含まれないこと"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))

        tiles = {
            Coordinate(0, 0, 0): Tile(Coordinate(0, 0, 0), TerrainType.grass()),
            Coordinate(1, 0, 0): Tile(Coordinate(1, 0, 0), TerrainType.wall()),
            Coordinate(2, 0, 0): Tile(Coordinate(2, 0, 0), TerrainType.grass()),
        }
        hidden_player = self._create_player_object(2, 2, 0)
        phys_repo.save(
            PhysicalMapAggregate(
                spot_id=SpotId(spot_id),
                tiles=tiles,
                objects=[self._create_player_object(player_id, 0, 0), hidden_player],
            )
        )

        result = service.get_visible_context(GetVisibleContextQuery(player_id=player_id, distance=3))

        assert result is not None
        assert {obj.player_id_value for obj in result.visible_objects if obj.player_id_value is not None} == {1}

    def test_get_visible_context_raises_world_system_error_on_unexpected_exception(self, setup_service):
        """想定外の例外時に WorldSystemErrorException が発生すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with patch.object(phys_repo, "find_by_spot_id", side_effect=RuntimeError("unexpected")):
            with pytest.raises(WorldSystemErrorException) as exc_info:
                service.get_visible_context(GetVisibleContextQuery(player_id=player_id))
            assert exc_info.value.original_exception is not None

    # --- get_available_moves 正常・例外 ---

    def test_get_available_moves_returns_dto_when_placed(self, setup_service):
        """配置済みプレイヤーの利用可能な移動先が PlayerMovementOptionsDto で返ること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Charlie"))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        result = service.get_available_moves(GetAvailableMovesQuery(player_id=player_id))

        assert result is not None
        assert result.player_id == player_id
        assert result.player_name == "Charlie"
        assert result.current_spot_id == spot_id
        assert isinstance(result.available_moves, list)
        assert result.total_available_moves == len(result.available_moves)

    def test_get_available_moves_returns_none_when_not_placed(self, setup_service):
        """未配置の場合は None を返すこと"""
        service, status_repo, profile_repo, _, spot_repo = setup_service
        player_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id)
        status._current_spot_id = None
        status._current_coordinate = None
        status_repo.save(status)

        result = service.get_available_moves(GetAvailableMovesQuery(player_id=player_id))

        assert result is None

    def test_get_available_moves_includes_connected_spot_when_gateway_exists(self, setup_service):
        """ゲートウェイで接続されたスポットが available_moves に含まれること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        from ai_rpg_world.domain.world.entity.gateway import Gateway
        from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
        from ai_rpg_world.domain.world.value_object.area import RectArea

        spot_repo.save(Spot(SpotId(1), "Here", ""))
        spot_repo.save(Spot(SpotId(2), "There", ""))
        gateway = Gateway(
            GatewayId(1),
            "GateToThere",
            RectArea(min_x=5, max_x=6, min_y=5, max_y=6, min_z=0, max_z=0),
            SpotId(2),
            Coordinate(0, 0, 0),
        )
        tiles = {}
        for x in range(10):
            for y in range(10):
                coord = Coordinate(x, y, 0)
                tiles[coord] = Tile(coord, TerrainType.grass())
        map1 = PhysicalMapAggregate(
            spot_id=SpotId(1),
            tiles=tiles,
            objects=[self._create_player_object(1, 0, 0)],
            gateways=[gateway],
        )
        phys_repo.save(map1)
        phys_repo.save(self._create_sample_map(2))
        profile_repo.save(self._create_sample_profile(1))
        status_repo.save(self._create_sample_status(1, 1, 0, 0))

        result = service.get_available_moves(GetAvailableMovesQuery(player_id=1))

        assert result is not None
        assert result.total_available_moves >= 1
        spot_ids = [m.spot_id for m in result.available_moves]
        assert 2 in spot_ids
        move_to_2 = next(m for m in result.available_moves if m.spot_id == 2)
        assert move_to_2.spot_name == "There"
        assert move_to_2.conditions_met is True

    def test_get_available_moves_raises_player_not_found_when_profile_missing(self, setup_service):
        """プロフィールが存在しない場合に PlayerNotFoundException が発生すること"""
        service, status_repo, _, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with pytest.raises(PlayerNotFoundException):
            service.get_available_moves(GetAvailableMovesQuery(player_id=player_id))

    def test_get_available_moves_raises_map_not_found_when_spot_missing(self, setup_service):
        """スポットが存在しない場合に MapNotFoundException が発生すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 999
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with pytest.raises(MapNotFoundException):
            service.get_available_moves(GetAvailableMovesQuery(player_id=player_id))

    def test_get_available_moves_raises_world_system_error_on_unexpected_exception(self, setup_service):
        """想定外の例外時に WorldSystemErrorException が発生すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with patch.object(spot_repo, "find_by_id", side_effect=RuntimeError("unexpected")):
            with pytest.raises(WorldSystemErrorException) as exc_info:
                service.get_available_moves(GetAvailableMovesQuery(player_id=player_id))
            assert exc_info.value.original_exception is not None

    # --- get_player_current_state 正常ケース ---

    def test_get_player_current_state_returns_dto_when_placed(self, setup_service):
        """配置済みプレイヤーの現在状態が PlayerCurrentStateDto で返ること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Alice"))
        status_repo.save(self._create_sample_status(player_id, spot_id, 3, 4))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id, 3, 4)]))
        spot_repo.save(Spot(SpotId(1), "Town", "A town"))

        result = service.get_player_current_state(GetPlayerCurrentStateQuery(player_id=player_id))

        assert result is not None
        assert isinstance(result, PlayerCurrentStateDto)
        assert result.player_id == player_id
        assert result.player_name == "Alice"
        assert result.current_spot_id == spot_id
        assert result.current_spot_name == "Town"
        assert result.x == 3
        assert result.y == 4
        assert result.weather_type is not None
        assert result.weather_intensity >= 0
        assert result.current_player_count >= 1
        assert result.attention_level is AttentionLevel.FULL
        assert isinstance(result.visible_objects, list)
        if result.visible_objects:
            visible = result.visible_objects[0]
            assert visible.display_name is not None
            assert visible.object_kind is not None
            assert visible.direction_from_player is not None
        assert result.available_moves is not None
        assert result.total_available_moves is not None

    def test_get_player_current_state_delegates_assembly_to_builder(self, setup_service):
        """現在状態の組み立ては builder に委譲すること"""
        _service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Alice"))
        status_repo.save(self._create_sample_status(player_id, spot_id, 3, 4))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id, 3, 4)]))
        builder = MagicMock()
        expected = PlayerCurrentStateDto(
            player_id=1,
            player_name="Alice",
            current_spot_id=1,
            current_spot_name="Town",
            current_spot_description="A town",
            x=3,
            y=4,
            z=0,
            area_id=None,
            area_name=None,
            current_player_count=1,
            current_player_ids={1},
            connected_spot_ids=set(),
            connected_spot_names=set(),
            weather_type="clear",
            weather_intensity=0.0,
            current_terrain_type="grass",
            visible_objects=[],
            view_distance=5,
            available_moves=[],
            total_available_moves=0,
            attention_level=AttentionLevel.FULL,
        )
        builder.build_player_current_state.return_value = expected
        service = WorldQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=GatewayBasedConnectedSpotsProvider(phys_repo),
            player_current_state_builder=builder,
        )

        result = service.get_player_current_state(GetPlayerCurrentStateQuery(player_id=player_id))

        assert result is expected
        builder.build_player_current_state.assert_called_once()

    def test_get_player_current_state_returns_none_when_not_placed(self, setup_service):
        """未配置の場合は None を返すこと"""
        service, status_repo, profile_repo, _, spot_repo = setup_service
        player_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id)
        status._current_spot_id = None
        status._current_coordinate = None
        status_repo.save(status)

        result = service.get_player_current_state(GetPlayerCurrentStateQuery(player_id=player_id))

        assert result is None

    def test_get_player_current_state_returns_none_when_player_not_in_repo(self, setup_service):
        """プレイヤーがリポジトリに存在しない場合は None を返すこと"""
        service, _, _, _, _ = setup_service

        result = service.get_player_current_state(GetPlayerCurrentStateQuery(player_id=99999))

        assert result is None

    def test_get_player_current_state_includes_attention_level_from_status(self, setup_service):
        """PlayerStatus の attention_level が DTO に含まれること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status.set_attention_level(AttentionLevel.IGNORE)
        status_repo.save(status)
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        result = service.get_player_current_state(GetPlayerCurrentStateQuery(player_id=player_id))

        assert result is not None
        assert result.attention_level == AttentionLevel.IGNORE

    def test_get_player_current_state_include_available_moves_false_omits_moves(self, setup_service):
        """include_available_moves=False のとき available_moves が None であること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        result = service.get_player_current_state(
            GetPlayerCurrentStateQuery(player_id=player_id, include_available_moves=False)
        )

        assert result is not None
        assert result.available_moves is None
        assert result.total_available_moves is None

    def test_get_player_current_state_marks_far_targets_as_not_immediately_executable(self, setup_service):
        """視認できても隣接していない対象には available_interactions が付かないこと"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        far_npc = WorldObject(
            object_id=WorldObjectId(200),
            coordinate=Coordinate(2, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=InteractableComponent(InteractionTypeEnum.TALK),
        )
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                objects=[self._create_player_object(player_id, 0, 0), far_npc],
            )
        )

        result = service.get_player_current_state(GetPlayerCurrentStateQuery(player_id=player_id))

        assert result is not None
        npc = next(obj for obj in result.visible_objects if obj.object_id == 200)
        assert npc.available_interactions == []

    def test_get_player_current_state_uses_actor_busy_state_and_path_state(self):
        """is_busy / busy_until_tick / has_active_path がアクター状態と経路状態から導出されること"""
        data_store = InMemoryDataStore()
        data_store.clear_all()
        status_repo = InMemoryPlayerStatusRepository(data_store)
        profile_repo = InMemoryPlayerProfileRepository(data_store)
        phys_repo = InMemoryPhysicalMapRepository(data_store)
        spot_repo = InMemorySpotRepository(data_store)
        spot_repo.save(Spot(SpotId(1), "Town", ""))
        game_time_provider = InMemoryGameTimeProvider(initial_tick=10)
        service = WorldQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=GatewayBasedConnectedSpotsProvider(phys_repo),
            game_time_provider=game_time_provider,
        )
        profile_repo.save(self._create_sample_profile(1))
        status = self._create_sample_status(1, 1, 0, 0)
        status.set_destination(
            Coordinate(2, 0, 0),
            [Coordinate(0, 0, 0), Coordinate(1, 0, 0), Coordinate(2, 0, 0)],
        )
        status_repo.save(status)
        actor = self._create_player_object(1, 0, 0)
        actor.set_busy(game_time_provider.get_current_tick().add_duration(5))
        phys_repo.save(self._create_sample_map(1, objects=[actor]))

        result = service.get_player_current_state(GetPlayerCurrentStateQuery(player_id=1))

        assert result is not None
        assert result.is_busy is True
        assert result.busy_until_tick == 15
        assert result.has_active_path is True

    def test_get_player_current_state_raises_player_not_found_when_profile_missing(self, setup_service):
        """プロフィールが存在しない場合に PlayerNotFoundException が発生すること"""
        service, status_repo, _, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with pytest.raises(PlayerNotFoundException):
            service.get_player_current_state(GetPlayerCurrentStateQuery(player_id=player_id))

    def test_get_player_current_state_raises_map_not_found_when_spot_missing(self, setup_service):
        """スポットが存在しない場合に MapNotFoundException が発生すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 999
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with pytest.raises(MapNotFoundException):
            service.get_player_current_state(GetPlayerCurrentStateQuery(player_id=player_id))

    def test_get_player_current_state_raises_world_system_error_on_unexpected_exception(self, setup_service):
        """想定外の例外時に WorldSystemErrorException が発生すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with patch.object(spot_repo, "find_by_id", side_effect=RuntimeError("unexpected")):
            with pytest.raises(WorldSystemErrorException) as exc_info:
                service.get_player_current_state(GetPlayerCurrentStateQuery(player_id=player_id))
            assert exc_info.value.original_exception is not None


class TestGetPlayerLocationQueryValidation:
    """GetPlayerLocationQuery のバリデーション"""

    def test_query_raises_value_error_for_invalid_player_id_zero(self):
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetPlayerLocationQuery(player_id=0)

    def test_query_raises_value_error_for_negative_player_id(self):
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetPlayerLocationQuery(player_id=-1)

    def test_query_accepts_positive_player_id(self):
        q = GetPlayerLocationQuery(player_id=1)
        assert q.player_id == 1


class TestGetSpotContextForPlayerQueryValidation:
    """GetSpotContextForPlayerQuery のバリデーション"""

    def test_query_raises_value_error_for_invalid_player_id_zero(self):
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetSpotContextForPlayerQuery(player_id=0)

    def test_query_accepts_positive_player_id(self):
        q = GetSpotContextForPlayerQuery(player_id=1)
        assert q.player_id == 1


class TestGetVisibleContextQueryValidation:
    """GetVisibleContextQuery のバリデーション"""

    def test_query_raises_value_error_for_invalid_player_id_zero(self):
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetVisibleContextQuery(player_id=0)

    def test_query_raises_value_error_for_negative_distance(self):
        with pytest.raises(ValueError, match="distance must be 0 or greater"):
            GetVisibleContextQuery(player_id=1, distance=-1)

    def test_query_accepts_positive_player_id_and_default_distance(self):
        q = GetVisibleContextQuery(player_id=1)
        assert q.player_id == 1
        assert q.distance == 5

    def test_query_accepts_custom_distance(self):
        q = GetVisibleContextQuery(player_id=1, distance=10)
        assert q.distance == 10


class TestGetAvailableMovesQueryValidation:
    """GetAvailableMovesQuery のバリデーション"""

    def test_query_raises_value_error_for_invalid_player_id_zero(self):
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetAvailableMovesQuery(player_id=0)

    def test_query_accepts_positive_player_id(self):
        q = GetAvailableMovesQuery(player_id=1)
        assert q.player_id == 1


class TestGetPlayerCurrentStateQueryValidation:
    """GetPlayerCurrentStateQuery のバリデーション"""

    def test_query_raises_value_error_for_invalid_player_id_zero(self):
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetPlayerCurrentStateQuery(player_id=0)

    def test_query_raises_value_error_for_negative_view_distance(self):
        with pytest.raises(ValueError, match="view_distance must be 0 or greater"):
            GetPlayerCurrentStateQuery(player_id=1, view_distance=-1)

    def test_query_accepts_positive_player_id_and_defaults(self):
        q = GetPlayerCurrentStateQuery(player_id=1)
        assert q.player_id == 1
        assert q.include_available_moves is True
        assert q.view_distance == 5

    def test_query_accepts_custom_include_available_moves_and_view_distance(self):
        q = GetPlayerCurrentStateQuery(player_id=1, include_available_moves=False, view_distance=10)
        assert q.include_available_moves is False
        assert q.view_distance == 10

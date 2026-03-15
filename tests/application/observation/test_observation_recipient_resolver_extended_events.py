"""追加観測イベントの配信先解決テスト（正常系・内部イベント・例外系）"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
)
from ai_rpg_world.domain.combat.event.combat_events import (
    HitBoxCreatedEvent,
    HitBoxHitRecordedEvent,
)
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.conversation.event.conversation_event import ConversationStartedEvent
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.event.guild_event import (
    GuildCreatedEvent,
    GuildDisbandedEvent,
    GuildRoleChangedEvent,
)
from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.monster.event.monster_events import (
    MonsterDamagedEvent,
    MonsterDecidedToMoveEvent,
    MonsterMpRecoveredEvent,
    TargetSpottedEvent,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
    PursuitFailureReason,
)
from ai_rpg_world.domain.pursuit.event.pursuit_events import (
    PursuitCancelledEvent,
    PursuitFailedEvent,
    PursuitStartedEvent,
    PursuitUpdatedEvent,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
    PursuitLastKnownState,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
)
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.quest.aggregate.quest_aggregate import QuestAggregate
from ai_rpg_world.domain.quest.enum.quest_enum import QuestObjectiveType
from ai_rpg_world.domain.quest.event.quest_event import (
    QuestCancelledEvent,
    QuestIssuedEvent,
    QuestPendingApprovalEvent,
)
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.quest.value_object.quest_objective import QuestObjective
from ai_rpg_world.domain.quest.value_object.quest_reward import QuestReward
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope
from ai_rpg_world.domain.shop.aggregate.shop_aggregate import ShopAggregate
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopItemListedEvent,
    ShopItemPurchasedEvent,
    ShopItemUnlistedEvent,
)
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillProposalType
from ai_rpg_world.domain.skill.event.skill_events import (
    SkillCooldownStartedEvent,
    SkillDeckLeveledUpEvent,
    SkillProposalGeneratedEvent,
    SkillUsedEvent,
)
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_guild_repository import (
    InMemoryGuildRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_quest_repository import (
    InMemoryQuestRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_shop_repository import (
    InMemoryShopRepository,
)


def _create_player_object(player_id: int, x: int = 0, y: int = 0) -> WorldObject:
    return WorldObject(
        object_id=WorldObjectId.create(player_id),
        coordinate=Coordinate(x, y, 0),
        object_type=ObjectTypeEnum.PLAYER,
        component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(player_id)),
    )


def _make_minimal_map(spot_id: int, objects: list[WorldObject]) -> PhysicalMapAggregate:
    tiles = {Coordinate(0, 0, 0): Tile(Coordinate(0, 0, 0), TerrainType.grass())}
    for obj in objects:
        tiles.setdefault(obj.coordinate, Tile(obj.coordinate, TerrainType.grass()))
    return PhysicalMapAggregate(
        spot_id=SpotId(spot_id),
        tiles=tiles,
        objects=objects,
    )


def _make_status(
    player_id: int,
    spot_id: int,
    coord: Coordinate = None,
) -> PlayerStatusAggregate:
    if coord is None:
        coord = Coordinate(0, 0, 0)
    exp_table = ExpTable(100, 1.5)
    nav = PlayerNavigationState.from_parts(
        current_spot_id=SpotId(spot_id),
        current_coordinate=coord,
    )
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
        navigation_state=nav,
    )


def _make_objective() -> QuestObjective:
    return QuestObjective(
        objective_type=QuestObjectiveType.REACH_SPOT,
        target_id=1,
        required_count=1,
    )


def _make_pursuit_last_known(target_id: int, spot_id: int = 1) -> PursuitLastKnownState:
    return PursuitLastKnownState(
        target_id=WorldObjectId.create(target_id),
        spot_id=SpotId(spot_id),
        coordinate=Coordinate(1, 0, 0),
    )


def _make_pursuit_target_snapshot(
    target_id: int, spot_id: int = 1
) -> PursuitTargetSnapshot:
    return PursuitTargetSnapshot(
        target_id=WorldObjectId.create(target_id),
        spot_id=SpotId(spot_id),
        coordinate=Coordinate(1, 0, 0),
    )


class TestObservationRecipientResolverExtendedEvents:
    def test_conversation_started_delivers_to_speaker_only(self):
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
        )
        event = ConversationStartedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="Conversation",
            npc_id_value=10,
            dialogue_tree_id_value=1,
            entry_node_id_value=1,
        )
        assert [p.value for p in resolver.resolve(event)] == [1]

    def test_player_spoke_whisper_delivers_to_target_only(self):
        """囁きは宛先プレイヤーのみ配信先になる"""
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
        )
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            content="内緒だよ",
            channel=SpeechChannel.WHISPER,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=PlayerId(2),
        )
        assert [p.value for p in resolver.resolve(event)] == [2]

    def test_player_spoke_say_delivers_to_players_within_range(self):
        """発言（SAY）は同一スポットで範囲内のプレイヤーに配信される"""
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        # 話し手(1)が (0,0)、他に (1,0)(2,0)(10,0) にプレイヤー。SAY_RANGE=5 なら (10,0) は届かない
        status_repo.save(_make_status(1, 1, Coordinate(0, 0, 0)))
        status_repo.save(_make_status(2, 1, Coordinate(1, 0, 0)))
        status_repo.save(_make_status(3, 1, Coordinate(2, 0, 0)))
        status_repo.save(_make_status(4, 1, Coordinate(10, 0, 0)))
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=MagicMock(),
        )
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            content="こんにちは",
            channel=SpeechChannel.SAY,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=None,
        )
        # 1,2,3 は距離 0,1,2 で範囲5以内。4 は距離10で範囲外
        result_ids = {p.value for p in resolver.resolve(event)}
        assert result_ids == {1, 2, 3}

    def test_player_spoke_shout_delivers_to_wider_range(self):
        """シャウトは同一スポットでより広い範囲に配信される"""
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        status_repo.save(_make_status(1, 1, Coordinate(0, 0, 0)))
        status_repo.save(_make_status(2, 1, Coordinate(10, 0, 0)))  # 距離10、SAYでは届かないがSHOUT(15)では届く
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=MagicMock(),
        )
        event = PlayerSpokeEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            content="助けて！",
            channel=SpeechChannel.SHOUT,
            spot_id=SpotId(1),
            speaker_coordinate=Coordinate(0, 0, 0),
            target_player_id=None,
        )
        assert {p.value for p in resolver.resolve(event)} == {1, 2}

    def test_quest_issued_public_delivers_to_all_known_players(self):
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        status_repo.save(_make_status(1, 1))
        status_repo.save(_make_status(2, 2))
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=physical_map_repo,
        )
        event = QuestIssuedEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            issuer_player_id=None,
            scope=QuestScope.public_scope(),
            reward=QuestReward.of(),
        )
        assert {p.value for p in resolver.resolve(event)} == {1, 2}

    def test_quest_issued_guild_scope_resolves_members_with_real_guild_repository(self):
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        guild_repo = InMemoryGuildRepository(data_store=data_store)
        guild = GuildAggregate.create_guild(
            guild_id=GuildId(10),
            spot_id=SpotId(1),
            location_area_id=LocationAreaId(1),
            name="暁",
            description="guild",
            creator_player_id=PlayerId(1),
        )
        guild.add_member(PlayerId(1), PlayerId(2))
        guild_repo.save(guild)
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=physical_map_repo,
            guild_repository=guild_repo,
        )
        event = QuestIssuedEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            issuer_player_id=PlayerId(1),
            scope=QuestScope.guild_scope(10),
            reward=QuestReward.of(),
        )
        assert {p.value for p in resolver.resolve(event)} == {1, 2}

    def test_quest_pending_approval_uses_real_guild_repository_with_int_guild_id(self):
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        guild_repo = InMemoryGuildRepository(data_store=data_store)
        guild = GuildAggregate.create_guild(
            guild_id=GuildId(7),
            spot_id=SpotId(1),
            location_area_id=LocationAreaId(1),
            name="黄昏",
            description="guild",
            creator_player_id=PlayerId(1),
        )
        guild.add_member(PlayerId(1), PlayerId(3))
        guild_repo.save(guild)
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=physical_map_repo,
            guild_repository=guild_repo,
        )
        event = QuestPendingApprovalEvent.create(
            aggregate_id=QuestId(3),
            aggregate_type="QuestAggregate",
            guild_id=7,
            issuer_player_id=PlayerId(9),
            scope=QuestScope.guild_scope(7),
            reward=QuestReward.of(),
        )
        assert {p.value for p in resolver.resolve(event)} == {1, 3}

    def test_quest_cancelled_reads_related_players_from_quest_repository(self):
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        quest_repo = InMemoryQuestRepository(data_store=data_store)
        quest = QuestAggregate.issue_quest(
            quest_id=QuestId(5),
            objectives=[_make_objective()],
            reward=QuestReward.of(gold=10),
            scope=QuestScope.direct_scope(PlayerId(3)),
            issuer_player_id=PlayerId(2),
        )
        quest.accept_by(PlayerId(3))
        quest_repo.save(quest)
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=physical_map_repo,
            quest_repository=quest_repo,
        )
        event = QuestCancelledEvent.create(
            aggregate_id=QuestId(5),
            aggregate_type="QuestAggregate",
        )
        assert {p.value for p in resolver.resolve(event)} == {2, 3}

    def test_shop_item_listed_delivers_players_at_shop_spot_with_real_shop_repository(self):
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        shop_repo = InMemoryShopRepository(data_store=data_store)
        status_repo.save(_make_status(1, 5))
        status_repo.save(_make_status(2, 5))
        shop_repo.save(
            ShopAggregate.create(
                shop_id=ShopId(1),
                spot_id=SpotId(5),
                location_area_id=LocationAreaId(1),
                owner_id=PlayerId(9),
                name="道具屋",
            )
        )
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=physical_map_repo,
            shop_repository=shop_repo,
        )
        event = ShopItemListedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(1),
            item_instance_id=ItemInstanceId(10),
            price_per_unit=ShopListingPrice(1),
            listed_by=PlayerId(9),
        )
        assert {p.value for p in resolver.resolve(event)} == {1, 2}

    def test_shop_item_unlisted_without_shop_repository_falls_back_to_operator(self):
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
        )
        event = ShopItemUnlistedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(1),
            unlisted_by=PlayerId(4),
        )
        assert [p.value for p in resolver.resolve(event)] == [4]

    def test_shop_item_purchased_delivers_buyer_and_seller(self):
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
        )
        event = ShopItemPurchasedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(1),
            item_instance_id=ItemInstanceId(11),
            buyer_id=PlayerId(2),
            quantity=3,
            total_gold=60,
            seller_id=PlayerId(7),
        )
        assert {p.value for p in resolver.resolve(event)} == {2, 7}

    def test_guild_created_delivers_creator_and_players_at_spot(self):
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        status_repo.save(_make_status(1, 9))
        status_repo.save(_make_status(2, 9))
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=physical_map_repo,
        )
        event = GuildCreatedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            name="紅蓮",
            description="guild",
            spot_id=SpotId(9),
            location_area_id=LocationAreaId(1),
            creator_player_id=PlayerId(1),
            creator_role=GuildRole.LEADER,
        )
        assert {p.value for p in resolver.resolve(event)} == {1, 2}

    def test_guild_disbanded_delivers_all_members_when_repository_available(self):
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        guild_repo = InMemoryGuildRepository(data_store=data_store)
        guild = GuildAggregate.create_guild(
            guild_id=GuildId(1),
            spot_id=SpotId(1),
            location_area_id=LocationAreaId(1),
            name="蒼穹",
            description="guild",
            creator_player_id=PlayerId(1),
        )
        guild.add_member(PlayerId(1), PlayerId(2))
        guild_repo.save(guild)
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=physical_map_repo,
            guild_repository=guild_repo,
        )
        event = GuildDisbandedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            disbanded_by=PlayerId(1),
        )
        assert {p.value for p in resolver.resolve(event)} == {1, 2}

    def test_guild_role_changed_without_repository_falls_back_to_actor_pair(self):
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
        )
        event = GuildRoleChangedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            player_id=PlayerId(2),
            old_role=GuildRole.MEMBER,
            new_role=GuildRole.OFFICER,
            changed_by=PlayerId(1),
        )
        assert {p.value for p in resolver.resolve(event)} == {1, 2}

    def test_monster_damaged_delivers_players_at_spot_and_attacker(self):
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        physical_map_repo.save(_make_minimal_map(2, [_create_player_object(1)]))
        status_repo.save(_make_status(1, 2))
        status_repo.save(_make_status(3, 2))
        monster_repo = MagicMock()
        monster = MagicMock()
        monster.spot_id = SpotId(2)
        monster_repo.find_by_id.return_value = monster
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=physical_map_repo,
            monster_repository=monster_repo,
        )
        event = MonsterDamagedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            damage=5,
            current_hp=95,
            attacker_id=WorldObjectId.create(1),
        )
        assert {p.value for p in resolver.resolve(event)} == {1, 3}

    @pytest.mark.parametrize(
        "event_factory",
        [
            lambda: MonsterDecidedToMoveEvent.create(
                aggregate_id=MonsterId(1),
                aggregate_type="MonsterAggregate",
                actor_id=WorldObjectId(1),
                coordinate={"x": 0, "y": 0, "z": 0},
                spot_id=SpotId(1),
                current_tick=1,
            ),
            lambda: MonsterMpRecoveredEvent.create(
                aggregate_id=MonsterId(1),
                aggregate_type="MonsterAggregate",
                amount=5,
                current_mp=20,
            ),
            lambda: TargetSpottedEvent.create(
                aggregate_id=WorldObjectId(1),
                aggregate_type="MonsterBehavior",
                actor_id=WorldObjectId(1),
                target_id=WorldObjectId(2),
                coordinate=Coordinate(0, 0, 0),
            ),
        ],
    )
    def test_internal_monster_events_return_empty(self, event_factory):
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
            monster_repository=MagicMock(),
        )
        assert resolver.resolve(event_factory()) == []

    def test_hit_box_hit_recorded_delivers_owner_and_target_players(self):
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store=data_store)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        physical_map_repo.save(
            _make_minimal_map(1, [_create_player_object(1, x=0), _create_player_object(2, x=1)])
        )
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=physical_map_repo,
        )
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId.create(1),
            target_id=WorldObjectId.create(2),
            hit_coordinate=Coordinate(0, 0, 0),
        )
        assert {p.value for p in resolver.resolve(event)} == {1, 2}

    def test_hit_box_created_is_internal_and_returns_empty(self):
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
        )
        event = HitBoxCreatedEvent.create(
            aggregate_id=HitBoxId(1),
            aggregate_type="HitBoxAggregate",
            spot_id=SpotId(1),
            owner_id=WorldObjectId.create(1),
            initial_coordinate=Coordinate(0, 0, 0),
            duration=3,
            power_multiplier=1.0,
            shape_cell_count=1,
            effect_count=0,
            activation_tick=1,
        )
        assert resolver.resolve(event) == []

    def test_skill_used_delivers_to_owner_when_loadout_repo_available(self):
        loadout_repo = MagicMock()
        loadout = MagicMock()
        loadout.owner_id = 7
        loadout_repo.find_by_id.return_value = loadout
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
            skill_loadout_repository=loadout_repo,
        )
        event = SkillUsedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            skill_id=SkillId(1),
            deck_tier=DeckTier.NORMAL,
            cast_lock_until_tick=10,
            cooldown_until_tick=20,
        )
        assert [p.value for p in resolver.resolve(event)] == [7]

    def test_skill_deck_leveled_up_delivers_to_progress_owner(self):
        progress_repo = MagicMock()
        progress = MagicMock()
        progress.owner_id = 11
        progress_repo.find_by_id.return_value = progress
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
            skill_deck_progress_repository=progress_repo,
        )
        event = SkillDeckLeveledUpEvent.create(
            aggregate_id=SkillDeckProgressId(1),
            aggregate_type="SkillDeckProgressAggregate",
            old_level=1,
            new_level=2,
        )
        assert [p.value for p in resolver.resolve(event)] == [11]

    @pytest.mark.parametrize(
        "event",
        [
            SkillCooldownStartedEvent.create(
                aggregate_id=SkillLoadoutId(1),
                aggregate_type="SkillLoadoutAggregate",
                skill_id=SkillId(1),
                cooldown_until_tick=99,
            ),
            SkillProposalGeneratedEvent.create(
                aggregate_id=SkillDeckProgressId(1),
                aggregate_type="SkillDeckProgressAggregate",
                proposal_id=1,
                proposal_type=SkillProposalType.ADD,
                offered_skill_id=SkillId(3),
            ),
        ],
    )
    def test_internal_skill_events_return_empty(self, event):
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
            skill_loadout_repository=MagicMock(),
            skill_deck_progress_repository=MagicMock(),
        )
        assert resolver.resolve(event) == []

    def test_pursuit_started_delivers_actor_only_when_target_is_not_player(self):
        data_store = InMemoryDataStore()
        physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        physical_map_repo.save(
            _make_minimal_map(
                1,
                [
                    _create_player_object(1),
                    WorldObject(
                        object_id=WorldObjectId.create(999),
                        coordinate=Coordinate(1, 0, 0),
                        object_type=ObjectTypeEnum.NPC,
                        component=ActorComponent(direction=DirectionEnum.SOUTH),
                    ),
                ],
            )
        )
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=physical_map_repo,
        )
        event = PursuitStartedEvent.create(
            aggregate_id=WorldObjectId.create(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId.create(1),
            target_id=WorldObjectId.create(999),
            target_snapshot=_make_pursuit_target_snapshot(999),
            last_known=_make_pursuit_last_known(999),
        )
        assert [p.value for p in resolver.resolve(event)] == [1]

    @pytest.mark.parametrize(
        "event",
        [
            PursuitStartedEvent.create(
                aggregate_id=WorldObjectId.create(1),
                aggregate_type="PlayerStatusAggregate",
                actor_id=WorldObjectId.create(1),
                target_id=WorldObjectId.create(2),
                target_snapshot=_make_pursuit_target_snapshot(2),
                last_known=_make_pursuit_last_known(2),
            ),
            PursuitUpdatedEvent.create(
                aggregate_id=WorldObjectId.create(1),
                aggregate_type="PlayerStatusAggregate",
                actor_id=WorldObjectId.create(1),
                target_id=WorldObjectId.create(2),
                last_known=_make_pursuit_last_known(2),
                target_snapshot=_make_pursuit_target_snapshot(2),
            ),
            PursuitFailedEvent.create(
                aggregate_id=WorldObjectId.create(1),
                aggregate_type="PlayerStatusAggregate",
                actor_id=WorldObjectId.create(1),
                target_id=WorldObjectId.create(2),
                failure_reason=PursuitFailureReason.TARGET_MISSING,
                last_known=_make_pursuit_last_known(2),
                target_snapshot=_make_pursuit_target_snapshot(2),
            ),
            PursuitCancelledEvent.create(
                aggregate_id=WorldObjectId.create(1),
                aggregate_type="PlayerStatusAggregate",
                actor_id=WorldObjectId.create(1),
                target_id=WorldObjectId.create(2),
                last_known=_make_pursuit_last_known(2),
                target_snapshot=_make_pursuit_target_snapshot(2),
            ),
        ],
    )
    def test_pursuit_lifecycle_events_deliver_actor_and_target_players(self, event):
        data_store = InMemoryDataStore()
        physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        physical_map_repo.save(
            _make_minimal_map(1, [_create_player_object(1), _create_player_object(2, 1, 0)])
        )
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=physical_map_repo,
        )
        assert {p.value for p in resolver.resolve(event)} == {1, 2}

    def test_pursuit_updated_deduplicates_when_actor_and_target_are_same_player(self):
        data_store = InMemoryDataStore()
        physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        physical_map_repo.save(_make_minimal_map(1, [_create_player_object(1)]))
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=physical_map_repo,
        )
        event = PursuitUpdatedEvent.create(
            aggregate_id=WorldObjectId.create(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId.create(1),
            target_id=WorldObjectId.create(1),
            last_known=_make_pursuit_last_known(1),
            target_snapshot=_make_pursuit_target_snapshot(1),
        )
        assert [p.value for p in resolver.resolve(event)] == [1]

    @pytest.mark.parametrize(
        "event",
        [
            PursuitUpdatedEvent.create(
                aggregate_id=WorldObjectId.create(1),
                aggregate_type="PlayerStatusAggregate",
                actor_id=WorldObjectId.create(1),
                target_id=WorldObjectId.create(999),
                last_known=_make_pursuit_last_known(999),
                target_snapshot=_make_pursuit_target_snapshot(999),
            ),
            PursuitFailedEvent.create(
                aggregate_id=WorldObjectId.create(1),
                aggregate_type="PlayerStatusAggregate",
                actor_id=WorldObjectId.create(1),
                target_id=WorldObjectId.create(999),
                failure_reason=PursuitFailureReason.TARGET_MISSING,
                last_known=_make_pursuit_last_known(999),
                target_snapshot=_make_pursuit_target_snapshot(999),
            ),
            PursuitCancelledEvent.create(
                aggregate_id=WorldObjectId.create(1),
                aggregate_type="PlayerStatusAggregate",
                actor_id=WorldObjectId.create(1),
                target_id=WorldObjectId.create(999),
                last_known=_make_pursuit_last_known(999),
                target_snapshot=_make_pursuit_target_snapshot(999),
            ),
        ],
    )
    def test_pursuit_events_keep_visibility_actor_only_when_target_is_not_player(self, event):
        data_store = InMemoryDataStore()
        physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        physical_map_repo.save(
            _make_minimal_map(
                1,
                [
                    _create_player_object(1),
                    WorldObject(
                        object_id=WorldObjectId.create(999),
                        coordinate=Coordinate(1, 0, 0),
                        object_type=ObjectTypeEnum.NPC,
                        component=ActorComponent(direction=DirectionEnum.SOUTH),
                    ),
                ],
            )
        )
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=physical_map_repo,
        )
        assert [p.value for p in resolver.resolve(event)] == [1]

    def test_public_quest_resolution_propagates_status_repository_error(self):
        status_repo = MagicMock()
        status_repo.find_all.side_effect = RuntimeError("find_all failed")
        resolver = create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=MagicMock(),
        )
        event = QuestIssuedEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            issuer_player_id=None,
            scope=QuestScope.public_scope(),
            reward=QuestReward.of(),
        )
        with pytest.raises(RuntimeError, match="find_all failed"):
            resolver.resolve(event)

    def test_pending_approval_propagates_guild_repository_error(self):
        guild_repo = MagicMock()
        guild_repo.find_by_id.side_effect = RuntimeError("guild lookup failed")
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
            guild_repository=guild_repo,
        )
        event = QuestPendingApprovalEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            guild_id=5,
            issuer_player_id=PlayerId(1),
            scope=QuestScope.guild_scope(5),
            reward=QuestReward.of(),
        )
        with pytest.raises(RuntimeError, match="guild lookup failed"):
            resolver.resolve(event)

    def test_shop_resolution_propagates_shop_repository_error(self):
        shop_repo = MagicMock()
        shop_repo.find_by_id.side_effect = RuntimeError("shop lookup failed")
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
            shop_repository=shop_repo,
        )
        event = ShopItemListedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(1),
            item_instance_id=ItemInstanceId(10),
            price_per_unit=ShopListingPrice(1),
            listed_by=PlayerId(1),
        )
        with pytest.raises(RuntimeError, match="shop lookup failed"):
            resolver.resolve(event)

    def test_monster_resolution_propagates_monster_repository_error(self):
        monster_repo = MagicMock()
        monster_repo.find_by_id.side_effect = RuntimeError("monster lookup failed")
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
            monster_repository=monster_repo,
        )
        event = MonsterDamagedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            damage=5,
            current_hp=95,
            attacker_id=None,
        )
        with pytest.raises(RuntimeError, match="monster lookup failed"):
            resolver.resolve(event)

    def test_skill_resolution_propagates_loadout_repository_error(self):
        loadout_repo = MagicMock()
        loadout_repo.find_by_id.side_effect = RuntimeError("loadout lookup failed")
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(),
            physical_map_repository=MagicMock(),
            skill_loadout_repository=loadout_repo,
        )
        event = SkillUsedEvent.create(
            aggregate_id=SkillLoadoutId(1),
            aggregate_type="SkillLoadoutAggregate",
            skill_id=SkillId(1),
            deck_tier=DeckTier.NORMAL,
            cast_lock_until_tick=10,
            cooldown_until_tick=20,
        )
        with pytest.raises(RuntimeError, match="loadout lookup failed"):
            resolver.resolve(event)

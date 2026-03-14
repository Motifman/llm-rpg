"""GuildRecipientStrategy のテスト（正常系・境界・例外）"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.player_audience_query_service import (
    PlayerAudienceQueryService,
)
from ai_rpg_world.application.observation.services.recipient_strategies.guild_recipient_strategy import (
    GuildRecipientStrategy,
)
from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole
from ai_rpg_world.domain.guild.event.guild_event import (
    GuildBankDepositedEvent,
    GuildBankWithdrawnEvent,
    GuildCreatedEvent,
    GuildDisbandedEvent,
    GuildMemberJoinedEvent,
    GuildMemberLeftEvent,
    GuildRoleChangedEvent,
)
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.guild.value_object.guild_membership import GuildMembership
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_guild_repository import (
    InMemoryGuildRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)


def _make_audience_query(status_repo: PlayerStatusRepository) -> PlayerAudienceQueryService:
    """テスト用 PlayerAudienceQueryService"""
    return PlayerAudienceQueryService(player_status_repository=status_repo)


class TestGuildRecipientStrategyNormal:
    """GuildRecipientStrategy 正常系テスト"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def audience_query(self, status_repo):
        return _make_audience_query(status_repo)

    def test_guild_created_returns_creator_and_players_at_spot(self, audience_query):
        """GuildCreatedEvent: 作成者と同一スポットのプレイヤーが配信先"""
        audience_query = MagicMock()
        audience_query.players_at_spot.return_value = [PlayerId(2), PlayerId(3)]
        strategy = GuildRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
        )
        event = GuildCreatedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            name="テストギルド",
            description="説明",
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(1),
            creator_player_id=PlayerId(1),
            creator_role=GuildRole.LEADER,
        )
        result = strategy.resolve(event)
        assert len(result) == 3
        assert result[0].value == 1
        assert {p.value for p in result} == {1, 2, 3}

    def test_guild_member_joined_returns_membership_player_when_no_repo(self, audience_query):
        """GuildMemberJoinedEvent: リポジトリなしのとき参加者のみ"""
        membership = GuildMembership(
            player_id=PlayerId(5),
            role=GuildRole.MEMBER,
            joined_at=datetime.now(),
            contribution_points=0,
        )
        strategy = GuildRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            guild_repository=None,
        )
        event = GuildMemberJoinedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            membership=membership,
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 5

    def test_guild_member_joined_returns_all_members_when_repo_has_guild(self, audience_query):
        """GuildMemberJoinedEvent: リポジトリにギルドがあるとき全メンバー"""
        guild_repo = InMemoryGuildRepository(data_store=InMemoryDataStore())
        guild = GuildAggregate.create_guild(
            guild_id=GuildId(10),
            spot_id=SpotId(1),
            location_area_id=LocationAreaId(1),
            name="ギルド",
            description="",
            creator_player_id=PlayerId(1),
        )
        guild.add_member(PlayerId(1), PlayerId(2))
        guild_repo.save(guild)
        membership = GuildMembership(
            player_id=PlayerId(3),
            role=GuildRole.MEMBER,
            joined_at=datetime.now(),
            contribution_points=0,
        )
        strategy = GuildRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            guild_repository=guild_repo,
        )
        event = GuildMemberJoinedEvent.create(
            aggregate_id=GuildId(10),
            aggregate_type="GuildAggregate",
            membership=membership,
        )
        result = strategy.resolve(event)
        assert len(result) == 2
        assert {p.value for p in result} == {1, 2}

    def test_guild_bank_deposited_returns_deposited_by_when_no_repo(self, audience_query):
        """GuildBankDepositedEvent: リポジトリなしのとき入金者のみ"""
        strategy = GuildRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            guild_repository=None,
        )
        event = GuildBankDepositedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildBankAggregate",
            amount=100,
            deposited_by=PlayerId(4),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 4

    def test_guild_disbanded_returns_all_members_when_repo_has_guild(self, audience_query):
        """GuildDisbandedEvent: リポジトリにギルドがあるとき全メンバー"""
        guild_repo = InMemoryGuildRepository(data_store=InMemoryDataStore())
        guild = GuildAggregate.create_guild(
            guild_id=GuildId(20),
            spot_id=SpotId(1),
            location_area_id=LocationAreaId(1),
            name="ギルド",
            description="",
            creator_player_id=PlayerId(1),
        )
        guild.add_member(PlayerId(1), PlayerId(2))
        guild_repo.save(guild)
        strategy = GuildRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            guild_repository=guild_repo,
        )
        event = GuildDisbandedEvent.create(
            aggregate_id=GuildId(20),
            aggregate_type="GuildAggregate",
            disbanded_by=PlayerId(1),
        )
        result = strategy.resolve(event)
        assert len(result) == 2
        assert {p.value for p in result} == {1, 2}


class TestGuildRecipientStrategyExceptions:
    """GuildRecipientStrategy 例外・境界テスト"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def audience_query(self, status_repo):
        return _make_audience_query(status_repo)

    def test_all_member_ids_returns_empty_when_repository_none(self, audience_query):
        """_all_member_ids: リポジトリが None のとき空リスト"""
        strategy = GuildRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            guild_repository=None,
        )
        result = strategy._all_member_ids(GuildId(1))
        assert result == []

    def test_all_member_ids_returns_empty_when_guild_not_found(self, audience_query):
        """_all_member_ids: ギルドが見つからないとき空リスト"""
        guild_repo = MagicMock()
        guild_repo.find_by_id.return_value = None
        strategy = GuildRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            guild_repository=guild_repo,
        )
        result = strategy._all_member_ids(GuildId(999))
        assert result == []

    def test_resolve_propagates_repository_exception(self, audience_query):
        """resolve: リポジトリが例外を投げた場合、その例外が伝播する"""
        guild_repo = MagicMock()
        guild_repo.find_by_id.side_effect = RuntimeError("Guild find failed")
        audience_query = MagicMock()
        audience_query.players_at_spot.return_value = []
        strategy = GuildRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            guild_repository=guild_repo,
        )
        membership = GuildMembership(
            player_id=PlayerId(1),
            role=GuildRole.LEADER,
            joined_at=datetime.now(),
            contribution_points=0,
        )
        event = GuildMemberJoinedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            membership=membership,
        )
        with pytest.raises(RuntimeError, match="Guild find failed"):
            strategy.resolve(event)


class TestGuildRecipientStrategySupports:
    """GuildRecipientStrategy supports テスト"""

    @pytest.fixture
    def strategy(self):
        return GuildRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=MagicMock(),
        )

    def test_supports_guild_created_event(self, strategy):
        """GuildCreatedEvent を supports"""
        event = GuildCreatedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            name="テスト",
            description="",
            spot_id=SpotId(1),
            location_area_id=LocationAreaId(1),
            creator_player_id=PlayerId(1),
            creator_role=GuildRole.LEADER,
        )
        assert strategy.supports(event) is True

    def test_supports_returns_false_for_unknown_event(self, strategy):
        """未知のイベントでは False"""
        class UnknownEvent:
            pass
        assert strategy.supports(UnknownEvent()) is False

"""QuestRecipientStrategy のテスト（正常系・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.application.observation.services.player_audience_query_service import (
    PlayerAudienceQueryService,
)
from ai_rpg_world.application.observation.services.recipient_strategies.quest_recipient_strategy import (
    QuestRecipientStrategy,
)
from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.guild.value_object.guild_membership import GuildMembership
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.quest.event.quest_event import (
    QuestAcceptedEvent,
    QuestApprovedEvent,
    QuestCancelledEvent,
    QuestCompletedEvent,
    QuestIssuedEvent,
    QuestPendingApprovalEvent,
)
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.quest.value_object.quest_reward import QuestReward
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_guild_repository import (
    InMemoryGuildRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_quest_repository import (
    InMemoryQuestRepository,
)
from ai_rpg_world.domain.quest.aggregate.quest_aggregate import QuestAggregate
from ai_rpg_world.domain.quest.enum.quest_enum import QuestObjectiveType, QuestStatus
from ai_rpg_world.domain.quest.value_object.quest_objective import QuestObjective


def _make_audience_query(status_repo: PlayerStatusRepository) -> PlayerAudienceQueryService:
    """テスト用 PlayerAudienceQueryService"""
    return PlayerAudienceQueryService(player_status_repository=status_repo)


class TestQuestRecipientStrategyNormal:
    """QuestRecipientStrategy 正常系テスト"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def audience_query(self, status_repo):
        return _make_audience_query(status_repo)

    @pytest.fixture
    def strategy(self, audience_query):
        return QuestRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
        )

    def test_quest_accepted_returns_acceptor(self, strategy):
        """QuestAcceptedEvent: acceptor_player_id が配信先"""
        event = QuestAcceptedEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            acceptor_player_id=PlayerId(5),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 5

    def test_quest_completed_returns_acceptor(self, strategy):
        """QuestCompletedEvent: acceptor_player_id が配信先"""
        event = QuestCompletedEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            acceptor_player_id=PlayerId(3),
            reward=QuestReward.of(),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 3

    def test_quest_issued_public_returns_all_known_players(self, strategy, status_repo):
        """QuestIssuedEvent (公開): all_known_players が配信先"""
        from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
            PlayerStatusAggregate,
        )
        from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
        from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
        from ai_rpg_world.domain.player.value_object.growth import Growth
        from ai_rpg_world.domain.player.value_object.gold import Gold
        from ai_rpg_world.domain.player.value_object.hp import Hp
        from ai_rpg_world.domain.player.value_object.mp import Mp
        from ai_rpg_world.domain.player.value_object.stamina import Stamina
        from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
        from ai_rpg_world.domain.world.value_object.coordinate import Coordinate

        exp_table = ExpTable(100, 1.5)
        status_repo.save(
            PlayerStatusAggregate(
                player_id=PlayerId(1),
                base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
                stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
                exp_table=exp_table,
                growth=Growth(1, 0, exp_table),
                gold=Gold(1000),
                hp=Hp.create(100, 100),
                mp=Mp.create(50, 50),
                stamina=Stamina.create(100, 100),
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(0, 0, 0),
            )
        )
        status_repo.save(
            PlayerStatusAggregate(
                player_id=PlayerId(2),
                base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
                stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
                exp_table=exp_table,
                growth=Growth(1, 0, exp_table),
                gold=Gold(1000),
                hp=Hp.create(100, 100),
                mp=Mp.create(50, 50),
                stamina=Stamina.create(100, 100),
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(0, 0, 0),
            )
        )
        event = QuestIssuedEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            issuer_player_id=None,
            scope=QuestScope.public_scope(),
            reward=QuestReward.of(),
        )
        result = strategy.resolve(event)
        assert len(result) == 2
        assert {p.value for p in result} == {1, 2}

    def test_quest_issued_direct_returns_target_player(self, strategy):
        """QuestIssuedEvent (直接): target_player_id が配信先"""
        event = QuestIssuedEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            issuer_player_id=None,
            scope=QuestScope.direct_scope(PlayerId(7)),
            reward=QuestReward.of(),
        )
        result = strategy.resolve(event)
        assert len(result) == 1
        assert result[0].value == 7

    def test_quest_issued_guild_returns_guild_members(self, audience_query, data_store):
        """QuestIssuedEvent (ギルド): ギルドメンバーが配信先"""
        guild_repo = InMemoryGuildRepository(data_store=data_store)
        guild = GuildAggregate.create_guild(
            guild_id=GuildId(5),
            spot_id=SpotId(1),
            location_area_id=LocationAreaId(1),
            name="テストギルド",
            description="desc",
            creator_player_id=PlayerId(1),
        )
        guild.add_member(PlayerId(1), PlayerId(2))
        guild_repo.save(guild)
        strategy = QuestRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            guild_repository=guild_repo,
        )
        event = QuestIssuedEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            issuer_player_id=None,
            scope=QuestScope.guild_scope(5),
            reward=QuestReward.of(),
        )
        result = strategy.resolve(event)
        assert len(result) == 2
        assert {p.value for p in result} == {1, 2}


class TestQuestRecipientStrategyExceptions:
    """QuestRecipientStrategy 例外・境界テスト"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def audience_query(self, status_repo):
        return _make_audience_query(status_repo)

    def test_resolve_by_scope_returns_empty_when_scope_none(self, audience_query):
        """_resolve_by_scope(None): 空リストを返す（防御的）"""
        strategy = QuestRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
        )
        result = strategy._resolve_by_scope(None)
        assert result == []

    def test_guild_member_ids_returns_empty_when_guild_id_zero(self, audience_query):
        """guild_id=0 のとき GuildId 検証で失敗し空リストを返す"""
        guild_repo = MagicMock()
        strategy = QuestRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            guild_repository=guild_repo,
        )
        event = QuestPendingApprovalEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            guild_id=0,
            issuer_player_id=PlayerId(1),
            scope=QuestScope.guild_scope(0),
            reward=QuestReward.of(),
        )
        result = strategy.resolve(event)
        assert result == []

    def test_guild_member_ids_returns_empty_when_guild_id_negative(self, audience_query):
        """guild_id=-1 のとき GuildId 検証で失敗し空リストを返す"""
        guild_repo = MagicMock()
        strategy = QuestRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            guild_repository=guild_repo,
        )
        event = QuestPendingApprovalEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            guild_id=-1,
            issuer_player_id=PlayerId(1),
            scope=QuestScope.guild_scope(-1),
            reward=QuestReward.of(),
        )
        result = strategy.resolve(event)
        assert result == []

    def test_quest_approved_returns_empty_when_quest_repository_none(self, audience_query):
        """quest_repository が None のとき QuestApprovedEvent は空リスト"""
        strategy = QuestRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            quest_repository=None,
        )
        event = QuestApprovedEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            approved_by=PlayerId(5),
        )
        result = strategy.resolve(event)
        assert result == []

    def test_quest_approved_returns_empty_when_quest_not_found(self, audience_query):
        """quest が find_by_id で見つからないとき空リスト"""
        quest_repo = MagicMock()
        quest_repo.find_by_id.return_value = None
        strategy = QuestRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            quest_repository=quest_repo,
        )
        event = QuestApprovedEvent.create(
            aggregate_id=QuestId(99),
            aggregate_type="QuestAggregate",
            approved_by=PlayerId(5),
        )
        result = strategy.resolve(event)
        assert result == []

    def test_quest_approved_returns_acceptor_and_issuer_when_found(self, audience_query):
        """QuestApprovedEvent: クエスト取得時 acceptor と issuer が配信先"""
        quest_repo = MagicMock()
        quest = MagicMock()
        quest.acceptor_player_id = PlayerId(3)
        quest.issuer_player_id = PlayerId(7)
        quest.scope = None
        quest_repo.find_by_id.return_value = quest
        strategy = QuestRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=audience_query,
            quest_repository=quest_repo,
        )
        event = QuestApprovedEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            approved_by=PlayerId(5),
        )
        result = strategy.resolve(event)
        assert len(result) == 2
        assert {p.value for p in result} == {3, 7}


class TestQuestRecipientStrategySupports:
    """QuestRecipientStrategy supports テスト"""

    @pytest.fixture
    def strategy(self):
        return QuestRecipientStrategy(
            observed_event_registry=ObservedEventRegistry(),
            player_audience_query=MagicMock(),
        )

    def test_supports_quest_accepted_event(self, strategy):
        """QuestAcceptedEvent を supports"""
        event = QuestAcceptedEvent.create(
            aggregate_id=QuestId(1),
            aggregate_type="QuestAggregate",
            acceptor_player_id=PlayerId(1),
        )
        assert strategy.supports(event) is True

    def test_supports_returns_false_for_unknown_event(self, strategy):
        """未知のイベントでは False"""
        class UnknownEvent:
            pass
        assert strategy.supports(UnknownEvent()) is False

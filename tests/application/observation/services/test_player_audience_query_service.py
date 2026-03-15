"""PlayerAudienceQueryService のテスト（正常・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.player_audience_query_service import (
    PlayerAudienceQueryService,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.player_navigation_state import (
    PlayerNavigationState,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
    InMemoryDataStore,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)


def _make_status(
    player_id: int,
    spot_id: int = 1,
    spot_id_none: bool = False,
) -> PlayerStatusAggregate:
    """テスト用 PlayerStatusAggregate を作成"""
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
        navigation_state=PlayerNavigationState.from_parts(
            current_spot_id=None if spot_id_none else SpotId(spot_id),
            current_coordinate=Coordinate(0, 0, 0) if not spot_id_none else None,
        ),
    )


class TestPlayerAudienceQueryServicePlayersAtSpot:
    """players_at_spot のテスト（正常・境界）"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def service(self, status_repo):
        return PlayerAudienceQueryService(
            player_status_repository=status_repo,
        )

    def test_returns_multiple_players_at_same_spot(
        self, service, status_repo
    ):
        """同一スポットに複数プレイヤーがいる場合、すべて返す（正常）"""
        status_repo.save(_make_status(1, spot_id=5))
        status_repo.save(_make_status(2, spot_id=5))
        status_repo.save(_make_status(3, spot_id=5))
        result = service.players_at_spot(SpotId(5))
        assert len(result) == 3
        assert {p.value for p in result} == {1, 2, 3}

    def test_returns_single_player_when_only_one_at_spot(
        self, service, status_repo
    ):
        """スポットに1人だけいる場合、その1人を返す（正常）"""
        status_repo.save(_make_status(7, spot_id=10))
        result = service.players_at_spot(SpotId(10))
        assert len(result) == 1
        assert result[0].value == 7

    def test_returns_empty_list_when_no_players_at_spot(
        self, service, status_repo
    ):
        """指定スポットに誰もいない場合、空リストを返す（境界）"""
        status_repo.save(_make_status(1, spot_id=1))
        status_repo.save(_make_status(2, spot_id=2))
        result = service.players_at_spot(SpotId(99))
        assert result == []

    def test_returns_empty_list_when_repository_empty(
        self, service
    ):
        """リポジトリが空の場合、空リストを返す（境界）"""
        result = service.players_at_spot(SpotId(1))
        assert result == []

    def test_excludes_players_with_current_spot_id_none(
        self, service, status_repo
    ):
        """current_spot_id が None のプレイヤーは結果に含めない（境界）"""
        status_repo.save(_make_status(1, spot_id=3))
        status_repo.save(_make_status(2, spot_id_none=True))
        result = service.players_at_spot(SpotId(3))
        assert len(result) == 1
        assert result[0].value == 1

    def test_returns_only_players_at_specified_spot(
        self, service, status_repo
    ):
        """異なるスポットにいるプレイヤーは含めない（正常）"""
        status_repo.save(_make_status(1, spot_id=1))
        status_repo.save(_make_status(2, spot_id=2))
        status_repo.save(_make_status(3, spot_id=2))
        result = service.players_at_spot(SpotId(2))
        assert len(result) == 2
        assert {p.value for p in result} == {2, 3}


class TestPlayerAudienceQueryServiceAllKnownPlayers:
    """all_known_players のテスト（正常・境界）"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def service(self, status_repo):
        return PlayerAudienceQueryService(
            player_status_repository=status_repo,
        )

    def test_returns_all_players_in_world(self, service, status_repo):
        """ワールドに存在する全プレイヤーを返す（正常）"""
        status_repo.save(_make_status(1, spot_id=1))
        status_repo.save(_make_status(2, spot_id=2))
        status_repo.save(_make_status(3, spot_id=3))
        result = service.all_known_players()
        assert len(result) == 3
        assert {p.value for p in result} == {1, 2, 3}

    def test_returns_empty_list_when_no_players_exist(self, service):
        """プレイヤーが存在しない場合、空リストを返す（境界）"""
        result = service.all_known_players()
        assert result == []

    def test_includes_players_with_spot_id_none(self, service, status_repo):
        """current_spot_id が None のプレイヤーも含める（正常）"""
        status_repo.save(_make_status(1, spot_id=1))
        status_repo.save(_make_status(2, spot_id_none=True))
        result = service.all_known_players()
        assert len(result) == 2
        assert {p.value for p in result} == {1, 2}


class TestPlayerAudienceQueryServiceExceptions:
    """例外伝播のテスト"""

    def test_players_at_spot_propagates_repository_exception(self):
        """find_all が例外を投げた場合、players_at_spot はその例外を伝播する"""
        status_repo = MagicMock(spec=PlayerStatusRepository)
        status_repo.find_all.side_effect = RuntimeError("find_all failed")
        service = PlayerAudienceQueryService(
            player_status_repository=status_repo,
        )
        with pytest.raises(RuntimeError, match="find_all failed"):
            service.players_at_spot(SpotId(1))

    def test_all_known_players_propagates_repository_exception(self):
        """find_all が例外を投げた場合、all_known_players はその例外を伝播する"""
        status_repo = MagicMock(spec=PlayerStatusRepository)
        status_repo.find_all.side_effect = ValueError("repository error")
        service = PlayerAudienceQueryService(
            player_status_repository=status_repo,
        )
        with pytest.raises(ValueError, match="repository error"):
            service.all_known_players()

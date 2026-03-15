"""ObservationPipeline のテスト（正常・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.observation_pipeline import (
    ObservationPipeline,
)
from ai_rpg_world.application.observation.services.observation_formatter import (
    ObservationFormatter,
)
from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.player_navigation_state import (
    PlayerNavigationState,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.event.status_events import (
    PlayerGoldEarnedEvent,
    PlayerLocationChangedEvent,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
    InMemoryDataStore,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)


def _make_status(
    player_id: int,
    spot_id: int = 1,
    attention_level: AttentionLevel = AttentionLevel.FULL,
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
            current_spot_id=SpotId(spot_id),
            current_coordinate=Coordinate(0, 0, 0),
        ),
        attention_level=attention_level,
    )


class TestObservationPipelineNormal:
    """run のテスト（正常）"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def physical_map_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    @pytest.fixture
    def resolver(self, status_repo, physical_map_repo):
        return create_observation_recipient_resolver(
            player_status_repository=status_repo,
            physical_map_repository=physical_map_repo,
        )

    @pytest.fixture
    def formatter(self):
        return ObservationFormatter()

    @pytest.fixture
    def pipeline(self, resolver, formatter, status_repo):
        return ObservationPipeline(
            resolver=resolver,
            formatter=formatter,
            player_status_repository=status_repo,
        )

    def test_returns_outputs_for_resolved_recipients(
        self, pipeline, status_repo
    ):
        """resolver が返した配信先について formatter が output を返すとリストに含まれる（正常）"""
        status_repo.save(_make_status(1, spot_id=1))
        event = PlayerGoldEarnedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            earned_amount=100,
            total_gold=1100,
        )

        result = pipeline.run(event)

        assert len(result) == 1
        assert result[0][0] == PlayerId(1)
        assert isinstance(result[0][1], ObservationOutput)
        assert "100" in result[0][1].prose

    def test_returns_multiple_outputs_when_multiple_recipients(
        self, pipeline, status_repo
    ):
        """複数配信先のとき、各プレイヤー向け出力が返る（正常）"""
        status_repo.save(_make_status(1, spot_id=1))
        status_repo.save(_make_status(2, spot_id=1))
        event = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(0, 0, 0),
        )

        result = pipeline.run(event)

        assert len(result) == 1
        assert result[0][0] == PlayerId(1)
        assert "現在地" in result[0][1].prose

    def test_excludes_none_output_from_formatter(self):
        """formatter が None を返した場合は結果に含めない（境界）"""
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [PlayerId(1), PlayerId(2)]
        mock_formatter = MagicMock()
        mock_formatter.format.side_effect = [
            ObservationOutput("a", {}, schedules_turn=False, breaks_movement=False),
            None,
        ]
        pipeline = ObservationPipeline(
            resolver=mock_resolver,
            formatter=mock_formatter,
        )

        result = pipeline.run(object())

        assert len(result) == 1
        assert result[0][0] == PlayerId(1)
        assert result[0][1].prose == "a"
        assert mock_formatter.format.call_count == 2


class TestObservationPipelineBoundary:
    """境界条件のテスト"""

    def test_returns_empty_list_when_no_recipients(self):
        """配信先が空のとき空リストを返す（境界）"""
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = []
        mock_formatter = MagicMock()
        pipeline = ObservationPipeline(
            resolver=mock_resolver,
            formatter=mock_formatter,
        )

        result = pipeline.run(object())

        assert result == []
        mock_formatter.format.assert_not_called()

    def test_uses_full_attention_when_repository_none(self):
        """player_status_repository が None のとき FULL で formatter を呼ぶ（境界）"""
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [PlayerId(1)]
        mock_formatter = MagicMock()
        mock_formatter.format.return_value = ObservationOutput(
            "x", {}, schedules_turn=False, breaks_movement=False
        )
        pipeline = ObservationPipeline(
            resolver=mock_resolver,
            formatter=mock_formatter,
            player_status_repository=None,
        )

        pipeline.run(object())

        mock_formatter.format.assert_called_once()
        call_kwargs = mock_formatter.format.call_args[1]
        assert call_kwargs["attention_level"] == AttentionLevel.FULL

    def test_uses_status_attention_level_when_repository_returns_status(self):
        """リポジトリが status を返すとき、その attention_level で formatter を呼ぶ（正常）"""
        status_repo = MagicMock()
        status_repo.find_by_id.return_value = _make_status(
            1, spot_id=1, attention_level=AttentionLevel.FILTER_SOCIAL
        )
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [PlayerId(1)]
        mock_formatter = MagicMock()
        mock_formatter.format.return_value = ObservationOutput(
            "x", {}, schedules_turn=False, breaks_movement=False
        )
        pipeline = ObservationPipeline(
            resolver=mock_resolver,
            formatter=mock_formatter,
            player_status_repository=status_repo,
        )

        pipeline.run(object())

        call_kwargs = mock_formatter.format.call_args[1]
        assert call_kwargs["attention_level"] == AttentionLevel.FILTER_SOCIAL

    def test_uses_full_attention_when_repository_returns_none(self):
        """リポジトリが None を返すとき FULL で formatter を呼ぶ（境界）"""
        status_repo = MagicMock()
        status_repo.find_by_id.return_value = None
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [PlayerId(1)]
        mock_formatter = MagicMock()
        mock_formatter.format.return_value = ObservationOutput(
            "x", {}, schedules_turn=False, breaks_movement=False
        )
        pipeline = ObservationPipeline(
            resolver=mock_resolver,
            formatter=mock_formatter,
            player_status_repository=status_repo,
        )

        pipeline.run(object())

        call_kwargs = mock_formatter.format.call_args[1]
        assert call_kwargs["attention_level"] == AttentionLevel.FULL


class TestObservationPipelineExceptions:
    """例外伝播のテスト"""

    def test_propagates_resolver_exception(self):
        """resolver.resolve が例外を投げた場合、run はその例外を伝播する"""
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = RuntimeError("resolver failed")
        mock_formatter = MagicMock()
        pipeline = ObservationPipeline(
            resolver=mock_resolver,
            formatter=mock_formatter,
        )

        with pytest.raises(RuntimeError, match="resolver failed"):
            pipeline.run(object())

    def test_propagates_formatter_exception(self):
        """formatter.format が例外を投げた場合、run はその例外を伝播する"""
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [PlayerId(1)]
        mock_formatter = MagicMock()
        mock_formatter.format.side_effect = ValueError("format failed")
        pipeline = ObservationPipeline(
            resolver=mock_resolver,
            formatter=mock_formatter,
        )

        with pytest.raises(ValueError, match="format failed"):
            pipeline.run(object())

    def test_propagates_repository_exception(self):
        """player_status_repository.find_by_id が例外を投げた場合、run はその例外を伝播する"""
        status_repo = MagicMock()
        status_repo.find_by_id.side_effect = RuntimeError("repo failed")
        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = [PlayerId(1)]
        mock_formatter = MagicMock()
        mock_formatter.format.return_value = ObservationOutput(
            "x", {}, schedules_turn=False, breaks_movement=False
        )
        pipeline = ObservationPipeline(
            resolver=mock_resolver,
            formatter=mock_formatter,
            player_status_repository=status_repo,
        )

        with pytest.raises(RuntimeError, match="repo failed"):
            pipeline.run(object())

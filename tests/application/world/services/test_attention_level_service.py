"""AttentionLevelApplicationService と ChangeAttentionLevelCommand のテスト。正常・例外を網羅する。"""

import pytest
from unittest.mock import patch

from ai_rpg_world.application.world.services.attention_level_service import (
    AttentionLevelApplicationService,
)
from ai_rpg_world.application.world.contracts.commands import ChangeAttentionLevelCommand
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
)
from ai_rpg_world.application.world.exceptions.base_exception import WorldSystemErrorException
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)


def _create_sample_status(player_id: int, spot_id: int = 1) -> PlayerStatusAggregate:
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
    )


class TestAttentionLevelApplicationService:
    """AttentionLevelApplicationService の正常・例外ケース"""

    @pytest.fixture
    def data_store(self):
        store = InMemoryDataStore()
        store.clear_all()
        return store

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store=data_store)

    @pytest.fixture
    def service(self, status_repo):
        return AttentionLevelApplicationService(player_status_repository=status_repo)

    # --- 正常ケース ---

    def test_change_attention_level_updates_status_to_full(self, service, status_repo):
        """注意レベルを FULL に変更できること"""
        status = _create_sample_status(1)
        status.set_attention_level(AttentionLevel.IGNORE)
        status_repo.save(status)

        service.change_attention_level(
            ChangeAttentionLevelCommand(player_id=1, attention_level=AttentionLevel.FULL)
        )

        updated = status_repo.find_by_id(PlayerId(1))
        assert updated is not None
        assert updated.attention_level == AttentionLevel.FULL

    def test_change_attention_level_updates_status_to_filter_social(self, service, status_repo):
        """注意レベルを FILTER_SOCIAL に変更できること"""
        status_repo.save(_create_sample_status(1))

        service.change_attention_level(
            ChangeAttentionLevelCommand(player_id=1, attention_level=AttentionLevel.FILTER_SOCIAL)
        )

        updated = status_repo.find_by_id(PlayerId(1))
        assert updated is not None
        assert updated.attention_level == AttentionLevel.FILTER_SOCIAL

    def test_change_attention_level_updates_status_to_ignore(self, service, status_repo):
        """注意レベルを IGNORE に変更できること"""
        status_repo.save(_create_sample_status(1))

        service.change_attention_level(
            ChangeAttentionLevelCommand(player_id=1, attention_level=AttentionLevel.IGNORE)
        )

        updated = status_repo.find_by_id(PlayerId(1))
        assert updated is not None
        assert updated.attention_level == AttentionLevel.IGNORE

    # --- 例外ケース ---

    def test_change_attention_level_raises_player_not_found_when_status_missing(
        self, service, status_repo
    ):
        """プレイヤーステータスが存在しない場合に PlayerNotFoundException が発生すること"""
        with pytest.raises(PlayerNotFoundException) as exc_info:
            service.change_attention_level(
                ChangeAttentionLevelCommand(player_id=99999, attention_level=AttentionLevel.FULL)
            )
        assert exc_info.value.context.get("player_id") == 99999

    def test_change_attention_level_raises_world_system_error_on_unexpected_exception(
        self, service, status_repo
    ):
        """想定外の例外時に WorldSystemErrorException が発生すること"""
        status_repo.save(_create_sample_status(1))

        with patch.object(status_repo, "save", side_effect=RuntimeError("unexpected")):
            with pytest.raises(WorldSystemErrorException) as exc_info:
                service.change_attention_level(
                    ChangeAttentionLevelCommand(player_id=1, attention_level=AttentionLevel.IGNORE)
                )
            assert exc_info.value.original_exception is not None
            assert isinstance(exc_info.value.original_exception, RuntimeError)


class TestChangeAttentionLevelCommandValidation:
    """ChangeAttentionLevelCommand のバリデーション"""

    def test_command_raises_value_error_for_invalid_player_id_zero(self):
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            ChangeAttentionLevelCommand(player_id=0, attention_level=AttentionLevel.FULL)

    def test_command_raises_value_error_for_negative_player_id(self):
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            ChangeAttentionLevelCommand(player_id=-1, attention_level=AttentionLevel.FULL)

    def test_command_raises_value_error_when_attention_level_not_enum(self):
        with pytest.raises(ValueError, match="attention_level must be an AttentionLevel enum"):
            ChangeAttentionLevelCommand(player_id=1, attention_level="FULL")  # type: ignore[arg-type]

    def test_command_accepts_valid_player_id_and_attention_level(self):
        cmd = ChangeAttentionLevelCommand(player_id=1, attention_level=AttentionLevel.IGNORE)
        assert cmd.player_id == 1
        assert cmd.attention_level == AttentionLevel.IGNORE

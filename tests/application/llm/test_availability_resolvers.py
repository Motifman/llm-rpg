"""availability_resolvers（NoOp, SetDestination）のテスト（正常・境界）"""

import pytest

from ai_rpg_world.application.llm.services.availability_resolvers import (
    NoOpAvailabilityResolver,
    SetDestinationAvailabilityResolver,
    WhisperAvailabilityResolver,
)
from ai_rpg_world.application.world.contracts.dtos import (
    AvailableMoveDto,
    PlayerCurrentStateDto,
    VisibleObjectDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _minimal_current_state(
    current_spot_id: int | None = 1,
    available_moves: list | None = None,
    total_available_moves: int | None = 0,
    visible_objects: list | None = None,
) -> PlayerCurrentStateDto:
    """テスト用の最小限の PlayerCurrentStateDto"""
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="Test",
        current_spot_id=current_spot_id,
        current_spot_name="Spot",
        current_spot_description="",
        x=0,
        y=0,
        z=0,
        area_id=None,
        area_name=None,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="clear",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=visible_objects or [],
        view_distance=5,
        available_moves=available_moves,
        total_available_moves=total_available_moves,
        attention_level=AttentionLevel.FULL,
    )


class TestNoOpAvailabilityResolver:
    """NoOpAvailabilityResolver は常に True"""

    def test_available_when_context_is_none(self):
        """context が None でも利用可能"""
        resolver = NoOpAvailabilityResolver()
        assert resolver.is_available(None) is True

    def test_available_when_context_present(self):
        """context があっても利用可能"""
        resolver = NoOpAvailabilityResolver()
        ctx = _minimal_current_state()
        assert resolver.is_available(ctx) is True


class TestSetDestinationAvailabilityResolver:
    """SetDestinationAvailabilityResolver の境界・正常"""

    def test_not_available_when_context_none(self):
        """context が None のとき利用不可"""
        resolver = SetDestinationAvailabilityResolver()
        assert resolver.is_available(None) is False

    def test_not_available_when_current_spot_id_none(self):
        """current_spot_id が None のとき利用不可"""
        resolver = SetDestinationAvailabilityResolver()
        ctx = _minimal_current_state(current_spot_id=None)
        assert resolver.is_available(ctx) is False

    def test_not_available_when_available_moves_none(self):
        """available_moves が None のとき利用不可"""
        resolver = SetDestinationAvailabilityResolver()
        ctx = _minimal_current_state(available_moves=None, total_available_moves=None)
        assert resolver.is_available(ctx) is False

    def test_not_available_when_total_zero(self):
        """total_available_moves が 0 のとき利用不可"""
        resolver = SetDestinationAvailabilityResolver()
        ctx = _minimal_current_state(available_moves=[], total_available_moves=0)
        assert resolver.is_available(ctx) is False

    def test_available_when_has_moves(self):
        """現在地があり移動先が 1 件以上あるとき利用可能"""
        resolver = SetDestinationAvailabilityResolver()
        move = AvailableMoveDto(
            spot_id=2,
            spot_name="Next",
            road_id=1,
            road_description="",
            conditions_met=True,
            failed_conditions=[],
        )
        ctx = _minimal_current_state(
            available_moves=[move],
            total_available_moves=1,
        )
        assert resolver.is_available(ctx) is True


class TestWhisperAvailabilityResolver:
    def test_not_available_when_context_none(self):
        resolver = WhisperAvailabilityResolver()
        assert resolver.is_available(None) is False

    def test_not_available_when_no_other_player_visible(self):
        resolver = WhisperAvailabilityResolver()
        ctx = _minimal_current_state(
            visible_objects=[
                VisibleObjectDto(
                    object_id=1,
                    object_type="PLAYER",
                    x=0,
                    y=0,
                    z=0,
                    distance=0,
                    object_kind="player",
                    is_self=True,
                )
            ]
        )
        assert resolver.is_available(ctx) is False

    def test_available_when_other_player_visible(self):
        resolver = WhisperAvailabilityResolver()
        ctx = _minimal_current_state(
            visible_objects=[
                VisibleObjectDto(
                    object_id=2,
                    object_type="PLAYER",
                    x=1,
                    y=0,
                    z=0,
                    distance=1,
                    object_kind="player",
                    is_self=False,
                )
            ]
        )
        assert resolver.is_available(ctx) is True

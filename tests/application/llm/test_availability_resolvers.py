"""availability_resolvers（NoOp, SetDestination）のテスト（正常・境界）"""


from ai_rpg_world.application.llm.services.availability_resolvers import (
    GuildCreateAvailabilityResolver,
    GuildDisbandAvailabilityResolver,
    NoOpAvailabilityResolver,
    WhisperAvailabilityResolver,
)
from ai_rpg_world.application.world.contracts.dtos import (
    GuildMembershipSummaryDto,
    PlayerCurrentStateDto,
    VisibleObjectDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _minimal_current_state(
    current_spot_id: int | None = 1,
    available_moves: list | None = None,
    total_available_moves: int | None = 0,
    available_location_areas: list | None = None,
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
        available_location_areas=available_location_areas,
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


class TestWhisperVisibilityNone:
    """WhisperAvailabilityResolver の visible_objects=None 防御"""

    def test_not_available_when_visible_objects_none(self):
        """visible_objects が None のとき TypeError を避けて False を返す"""
        resolver = WhisperAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.visible_objects = None  # type: ignore[assignment]
        assert resolver.is_available(ctx) is False


class TestGuildCreateAvailabilityResolver:
    """GuildCreateAvailabilityResolver のテスト"""

    def test_not_available_when_context_none(self):
        resolver = GuildCreateAvailabilityResolver()
        assert resolver.is_available(None) is False

    def test_not_available_when_area_ids_empty(self):
        resolver = GuildCreateAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.area_ids = []
        assert resolver.is_available(ctx) is False

    def test_not_available_when_already_in_guild(self):
        resolver = GuildCreateAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.area_ids = [10]
        ctx.guild_memberships = [GuildMembershipSummaryDto(1, "テスト", "leader")]
        assert resolver.is_available(ctx) is False

    def test_available_when_no_guild_and_has_area_ids(self):
        resolver = GuildCreateAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.area_ids = [10]
        ctx.guild_memberships = []
        assert resolver.is_available(ctx) is True


class TestGuildDisbandAvailabilityResolver:
    """GuildDisbandAvailabilityResolver のテスト"""

    def test_not_available_when_no_leader(self):
        resolver = GuildDisbandAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.guild_memberships = [GuildMembershipSummaryDto(1, "テスト", "member")]
        assert resolver.is_available(ctx) is False

    def test_available_when_leader(self):
        resolver = GuildDisbandAvailabilityResolver()
        ctx = _minimal_current_state()
        ctx.guild_memberships = [GuildMembershipSummaryDto(1, "テスト", "leader")]
        assert resolver.is_available(ctx) is True

"""何もしない操作とギルド操作の利用条件を保証する。"""

from ai_rpg_world.application.llm.services.availability_resolvers import (
    GuildCreateAvailabilityResolver,
    GuildDisbandAvailabilityResolver,
    NoOpAvailabilityResolver,
)
from ai_rpg_world.application.world.contracts.dtos import (
    GuildMembershipSummaryDto,
    PlayerCurrentStateDto,
)


def _minimal_current_state(
    current_spot_id: int | None = 1,
) -> PlayerCurrentStateDto:
    """テスト用の最小限の PlayerCurrentStateDto"""
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="Test",
        current_spot_id=current_spot_id,
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

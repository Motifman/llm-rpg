"""GuildObservationFormatter の単体テスト。"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.guild_formatter import (
    GuildObservationFormatter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
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
from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.event.harvest_events import HarvestStartedEvent
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick


def _make_context(
    player_profile_repository=None,
) -> ObservationFormatterContext:
    """テスト用の ObservationFormatterContext を生成。"""
    name_resolver = ObservationNameResolver(
        spot_repository=None,
        player_profile_repository=player_profile_repository,
        item_spec_repository=None,
        item_repository=None,
        shop_repository=None,
        guild_repository=None,
        monster_repository=None,
        skill_spec_repository=None,
        sns_user_repository=None,
    )
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=None,
    )


class TestGuildObservationFormatterCreation:
    """GuildObservationFormatter 生成のテスト"""

    def test_creates_with_context_only(self):
        """context のみで生成できる（parent 不要）。"""
        ctx = _make_context()
        formatter = GuildObservationFormatter(ctx)
        assert formatter._context is ctx

    def test_format_method_exists(self):
        """format(event, recipient_player_id) が呼び出し可能。"""
        ctx = _make_context()
        formatter = GuildObservationFormatter(ctx)
        assert hasattr(formatter, "format")
        assert callable(formatter.format)


class TestGuildObservationFormatterGuildCreated:
    """GuildCreatedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return GuildObservationFormatter(_make_context())

    def test_returns_observation_output_with_prose_and_structured(self, formatter):
        """ギルド創設は prose と structured を返す。"""
        event = GuildCreatedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            name="紅蓮",
            description="guild",
            spot_id=SpotId(1),
            location_area_id=LocationAreaId(1),
            creator_player_id=PlayerId(1),
            creator_role=GuildRole.LEADER,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert isinstance(out, ObservationOutput)
        assert "紅蓮" in out.prose
        assert "創設されました" in out.prose
        assert out.structured.get("type") == "guild_created"
        assert out.structured.get("guild_name") == "紅蓮"
        assert out.structured.get("guild_id_value") == 1
        assert out.observation_category == "social"


class TestGuildObservationFormatterGuildMemberJoined:
    """GuildMemberJoinedEvent のフォーマットテスト"""

    def test_uses_player_repository_name(self):
        """player_profile_repository があればプレイヤー名を解決する。"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Bob"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(player_profile_repository=profile_repo)
        formatter = GuildObservationFormatter(ctx)
        event = GuildMemberJoinedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            membership=GuildMembership(
                player_id=PlayerId(2),
                role=GuildRole.MEMBER,
                joined_at=datetime(2024, 1, 1, 0, 0, 0),
            ),
            invited_by=PlayerId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Bob" in out.prose
        assert "加入しました" in out.prose
        assert out.structured.get("type") == "guild_member_joined"
        assert out.structured.get("member") == "Bob"
        assert out.structured.get("guild_id_value") == 1
        assert out.schedules_turn is True

    def test_uses_fallback_when_repository_none(self):
        """player_profile_repository が None の場合はフォールバック名。"""
        ctx = _make_context()
        formatter = GuildObservationFormatter(ctx)
        event = GuildMemberJoinedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            membership=GuildMembership(
                player_id=PlayerId(2),
                role=GuildRole.MEMBER,
                joined_at=datetime(2024, 1, 1, 0, 0, 0),
            ),
            invited_by=PlayerId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "不明なプレイヤー" in out.prose
        assert "加入しました" in out.prose


class TestGuildObservationFormatterGuildMemberLeft:
    """GuildMemberLeftEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return GuildObservationFormatter(_make_context())

    def test_returns_prose_with_member_and_role(self, formatter):
        """脱退は member と role を prose に含む。"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Alice"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(player_profile_repository=profile_repo)
        formatter = GuildObservationFormatter(ctx)
        event = GuildMemberLeftEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            player_id=PlayerId(2),
            role=GuildRole.OFFICER,
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Alice" in out.prose
        assert "脱退しました" in out.prose
        assert out.structured.get("type") == "guild_member_left"
        assert out.structured.get("role") == "officer"


class TestGuildObservationFormatterGuildRoleChanged:
    """GuildRoleChangedEvent のフォーマットテスト"""

    def test_includes_old_and_new_role_in_prose(self):
        """役職変更は old/new role を prose に含む。"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Bob"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(player_profile_repository=profile_repo)
        formatter = GuildObservationFormatter(ctx)
        event = GuildRoleChangedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            player_id=PlayerId(2),
            old_role=GuildRole.MEMBER,
            new_role=GuildRole.OFFICER,
            changed_by=PlayerId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Bob" in out.prose
        assert "member" in out.prose
        assert "officer" in out.prose
        assert out.structured.get("type") == "guild_role_changed"
        assert out.structured.get("old") == "member"
        assert out.structured.get("new") == "officer"


class TestGuildObservationFormatterGuildBankDeposited:
    """GuildBankDepositedEvent のフォーマットテスト"""

    def test_includes_amount_and_actor(self):
        """入金は amount と actor を prose に含む。"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Charlie"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(player_profile_repository=profile_repo)
        formatter = GuildObservationFormatter(ctx)
        event = GuildBankDepositedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildBankAggregate",
            amount=200,
            deposited_by=PlayerId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Charlie" in out.prose
        assert "200" in out.prose
        assert "入金" in out.prose
        assert out.structured.get("type") == "guild_bank_deposited"
        assert out.structured.get("amount") == 200


class TestGuildObservationFormatterGuildBankWithdrawn:
    """GuildBankWithdrawnEvent のフォーマットテスト"""

    def test_includes_amount_and_actor(self):
        """出金は amount と actor を prose に含む。"""
        profile_repo = MagicMock()
        profile = MagicMock()
        profile.name.value = "Dave"
        profile_repo.find_by_id.return_value = profile
        ctx = _make_context(player_profile_repository=profile_repo)
        formatter = GuildObservationFormatter(ctx)
        event = GuildBankWithdrawnEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildBankAggregate",
            amount=50,
            withdrawn_by=PlayerId(2),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "Dave" in out.prose
        assert "50" in out.prose
        assert "出金" in out.prose
        assert out.structured.get("type") == "guild_bank_withdrawn"
        assert out.structured.get("amount") == 50


class TestGuildObservationFormatterGuildDisbanded:
    """GuildDisbandedEvent のフォーマットテスト"""

    @pytest.fixture
    def formatter(self):
        return GuildObservationFormatter(_make_context())

    def test_returns_disbanded_message(self, formatter):
        """解散は「ギルドが解散しました。」を返す。"""
        event = GuildDisbandedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            disbanded_by=PlayerId(1),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is not None
        assert "解散しました" in out.prose
        assert out.structured.get("type") == "guild_disbanded"
        assert out.structured.get("guild_id_value") == 1
        assert out.observation_category == "social"
        assert out.schedules_turn is True


class TestGuildObservationFormatterUnknownEvent:
    """対象外イベントのテスト"""

    @pytest.fixture
    def formatter(self):
        return GuildObservationFormatter(_make_context())

    def test_returns_none_for_unknown_event(self, formatter):
        """対象外イベントは None。"""
        class UnknownEvent:
            pass
        out = formatter.format(UnknownEvent(), PlayerId(1))
        assert out is None

    def test_returns_none_for_harvest_event(self, formatter):
        """Harvest イベントは None。"""
        event = HarvestStartedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="Harvest",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            finish_tick=WorldTick(10),
        )
        out = formatter.format(event, PlayerId(1))
        assert out is None


class TestGuildObservationFormatterRecipientIndependence:
    """recipient_player_id への依存テスト"""

    def test_guild_created_output_does_not_depend_on_recipient(self):
        """GuildCreated は recipient に依存しない。"""
        ctx = _make_context()
        formatter = GuildObservationFormatter(ctx)
        event = GuildCreatedEvent.create(
            aggregate_id=GuildId(1),
            aggregate_type="GuildAggregate",
            name="蒼穹",
            description="guild",
            spot_id=SpotId(1),
            location_area_id=LocationAreaId(1),
            creator_player_id=PlayerId(1),
            creator_role=GuildRole.LEADER,
        )
        out1 = formatter.format(event, PlayerId(1))
        out2 = formatter.format(event, PlayerId(999))
        assert out1 is not None
        assert out2 is not None
        assert out1.prose == out2.prose
        assert out1.structured == out2.structured

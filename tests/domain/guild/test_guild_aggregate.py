import pytest
from datetime import datetime

from ai_rpg_world.domain.guild.aggregate.guild_aggregate import GuildAggregate
from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole
from ai_rpg_world.domain.guild.exception.guild_exception import (
    CannotJoinGuildException,
    CannotLeaveGuildException,
    CannotChangeRoleException,
    NotGuildMemberException,
    InsufficientGuildPermissionException,
    AlreadyGuildMemberException,
)
from ai_rpg_world.domain.guild.event.guild_event import (
    GuildCreatedEvent,
    GuildMemberJoinedEvent,
    GuildMemberLeftEvent,
    GuildRoleChangedEvent,
)
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestGuildAggregate:
    """GuildAggregateのテスト"""

    @pytest.fixture
    def guild_id(self) -> GuildId:
        return GuildId(1)

    @pytest.fixture
    def creator_id(self) -> PlayerId:
        return PlayerId(1)

    @pytest.fixture
    def player_2_id(self) -> PlayerId:
        return PlayerId(2)

    @pytest.fixture
    def player_3_id(self) -> PlayerId:
        return PlayerId(3)

    @pytest.fixture
    def guild(self, guild_id, creator_id) -> GuildAggregate:
        return GuildAggregate.create_guild(
            guild_id=guild_id,
            name="Test Guild",
            description="A test guild",
            creator_player_id=creator_id,
        )

    @pytest.fixture
    def guild_with_members(self, guild, guild_id, creator_id, player_2_id) -> GuildAggregate:
        """リーダー(1)とメンバー(2)がいるギルド。1はオフィサーに昇格可能。"""
        guild.add_member(inviter_player_id=creator_id, new_player_id=player_2_id)
        return guild

    class TestCreateGuild:
        def test_create_guild_success(self, guild_id, creator_id):
            g = GuildAggregate.create_guild(
                guild_id=guild_id,
                name=" My Guild ",
                description=" Desc ",
                creator_player_id=creator_id,
            )
            assert g.guild_id == guild_id
            assert g.name == "My Guild"
            assert g.description == "Desc"
            assert g.is_member(creator_id) is True
            assert g.get_member(creator_id).role == GuildRole.LEADER
            events = g.get_events()
            assert len(events) == 1
            assert isinstance(events[0], GuildCreatedEvent)
            assert events[0].creator_player_id == creator_id

        def test_create_guild_empty_name_raises(self, guild_id, creator_id):
            with pytest.raises(ValueError):
                GuildAggregate.create_guild(
                    guild_id=guild_id,
                    name="   ",
                    description="x",
                    creator_player_id=creator_id,
                )

    class TestAddMember:
        def test_add_member_success(self, guild, guild_id, creator_id, player_2_id):
            guild.add_member(inviter_player_id=creator_id, new_player_id=player_2_id)
            assert guild.is_member(player_2_id) is True
            assert guild.get_member(player_2_id).role == GuildRole.MEMBER
            events = guild.get_events()
            assert any(isinstance(e, GuildMemberJoinedEvent) for e in events)

        def test_add_member_already_member_raises(self, guild_with_members, creator_id, player_2_id):
            with pytest.raises(AlreadyGuildMemberException):
                guild_with_members.add_member(
                    inviter_player_id=creator_id,
                    new_player_id=player_2_id,
                )

        def test_add_member_inviter_not_member_raises(self, guild, guild_id, player_2_id, player_3_id):
            with pytest.raises(NotGuildMemberException):
                guild.add_member(
                    inviter_player_id=player_3_id,
                    new_player_id=player_2_id,
                )

        def test_add_member_member_cannot_invite_raises(
            self, guild_with_members, guild_id, player_2_id, player_3_id
        ):
            """MEMBER は招待権限がない"""
            with pytest.raises(InsufficientGuildPermissionException):
                guild_with_members.add_member(
                    inviter_player_id=player_2_id,
                    new_player_id=player_3_id,
                )

    class TestLeave:
        def test_leave_success(self, guild_with_members, player_2_id):
            guild_with_members.leave(player_2_id)
            assert guild_with_members.is_member(player_2_id) is False
            events = guild_with_members.get_events()
            assert any(isinstance(e, GuildMemberLeftEvent) for e in events)

        def test_leave_leader_when_only_member_success(self, guild, creator_id):
            """リーダー1人のみのギルドなら脱退可能"""
            guild.leave(creator_id)
            assert guild.is_member(creator_id) is False

        def test_leave_leader_when_other_members_raises(self, guild_with_members, creator_id):
            """他にメンバーがいる場合リーダーは脱退できない"""
            with pytest.raises(CannotLeaveGuildException):
                guild_with_members.leave(creator_id)

        def test_leave_not_member_raises(self, guild, player_2_id):
            with pytest.raises(CannotLeaveGuildException):
                guild.leave(player_2_id)

    class TestChangeRole:
        def test_change_role_to_officer_success(
            self, guild_with_members, creator_id, player_2_id
        ):
            guild_with_members.change_role(
                changer_player_id=creator_id,
                target_player_id=player_2_id,
                new_role=GuildRole.OFFICER,
            )
            assert guild_with_members.get_member(player_2_id).role == GuildRole.OFFICER
            events = guild_with_members.get_events()
            assert any(isinstance(e, GuildRoleChangedEvent) for e in events)

        def test_change_role_changer_not_officer_raises(
            self, guild_with_members, creator_id, player_2_id, player_3_id
        ):
            """MEMBER は役職変更権限がない"""
            guild_with_members.add_member(
                inviter_player_id=creator_id,
                new_player_id=player_3_id,
            )
            # player_2 は MEMBER なので change_role できない（1=LEADER, 2=MEMBER, 3=MEMBER）
            with pytest.raises(InsufficientGuildPermissionException):
                guild_with_members.change_role(
                    changer_player_id=player_2_id,
                    target_player_id=player_3_id,
                    new_role=GuildRole.OFFICER,
                )

        def test_change_role_target_not_member_raises(
            self, guild_with_members, creator_id, player_3_id
        ):
            with pytest.raises(NotGuildMemberException):
                guild_with_members.change_role(
                    changer_player_id=creator_id,
                    target_player_id=player_3_id,
                    new_role=GuildRole.MEMBER,
                )

        def test_change_role_leader_cannot_demote_self(
            self, guild_with_members, creator_id, player_2_id
        ):
            with pytest.raises(CannotChangeRoleException):
                guild_with_members.change_role(
                    changer_player_id=creator_id,
                    target_player_id=creator_id,
                    new_role=GuildRole.MEMBER,
                )

    class TestCanApproveQuest:
        def test_leader_can_approve_quest(self, guild, creator_id):
            assert guild.can_approve_quest(creator_id) is True

        def test_officer_can_approve_quest(
            self, guild_with_members, creator_id, player_2_id
        ):
            guild_with_members.change_role(
                changer_player_id=creator_id,
                target_player_id=player_2_id,
                new_role=GuildRole.OFFICER,
            )
            assert guild_with_members.can_approve_quest(player_2_id) is True

        def test_member_cannot_approve_quest(self, guild_with_members, player_2_id):
            assert guild_with_members.can_approve_quest(player_2_id) is False

        def test_non_member_cannot_approve_quest(self, guild, player_2_id):
            assert guild.can_approve_quest(player_2_id) is False

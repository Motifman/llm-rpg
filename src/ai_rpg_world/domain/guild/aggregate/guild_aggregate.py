from typing import Dict, Optional
from datetime import datetime

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
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
from ai_rpg_world.domain.guild.value_object.guild_membership import GuildMembership
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class GuildAggregate(AggregateRoot):
    """ギルド集約"""

    def __init__(
        self,
        guild_id: GuildId,
        name: str,
        description: str,
        members: Optional[Dict[PlayerId, GuildMembership]] = None,
    ):
        super().__init__()
        self.guild_id = guild_id
        self.name = name
        self.description = description
        self._members: Dict[PlayerId, GuildMembership] = dict(members) if members else {}

    @classmethod
    def create_guild(
        cls,
        guild_id: GuildId,
        name: str,
        description: str,
        creator_player_id: PlayerId,
    ) -> "GuildAggregate":
        """ギルドを作成する。作成者がリーダーとして参加する。"""
        if not name.strip():
            raise ValueError("Guild name must not be empty")
        membership = GuildMembership(
            player_id=creator_player_id,
            role=GuildRole.LEADER,
            joined_at=datetime.now(),
            contribution_points=0,
        )
        guild = cls(
            guild_id=guild_id,
            name=name.strip(),
            description=description.strip(),
            members={creator_player_id: membership},
        )
        event = GuildCreatedEvent.create(
            aggregate_id=guild_id,
            aggregate_type="GuildAggregate",
            name=guild.name,
            description=guild.description,
            creator_player_id=creator_player_id,
            creator_role=GuildRole.LEADER,
        )
        guild.add_event(event)
        return guild

    def is_member(self, player_id: PlayerId) -> bool:
        return player_id in self._members

    def get_member(self, player_id: PlayerId) -> Optional[GuildMembership]:
        return self._members.get(player_id)

    def can_approve_quest(self, player_id: PlayerId) -> bool:
        """指定プレイヤーがクエスト承認権限を持つか（オフィサー以上）"""
        membership = self._members.get(player_id)
        return membership is not None and membership.can_approve_quest()

    def add_member(
        self,
        inviter_player_id: PlayerId,
        new_player_id: PlayerId,
    ) -> None:
        """メンバーを追加する（招待）。招待者はオフィサー以上である必要がある。"""
        if self.is_member(new_player_id):
            raise AlreadyGuildMemberException(
                f"Player {new_player_id} is already a member of guild {self.guild_id}"
            )
        inviter = self._members.get(inviter_player_id)
        if inviter is None:
            raise NotGuildMemberException(
                f"Inviter {inviter_player_id} is not a member of guild {self.guild_id}"
            )
        if not inviter.can_invite_member():
            raise InsufficientGuildPermissionException(
                f"Player {inviter_player_id} cannot invite members (role={inviter.role})"
            )
        membership = GuildMembership(
            player_id=new_player_id,
            role=GuildRole.MEMBER,
            joined_at=datetime.now(),
            contribution_points=0,
        )
        self._members[new_player_id] = membership
        event = GuildMemberJoinedEvent.create(
            aggregate_id=self.guild_id,
            aggregate_type="GuildAggregate",
            membership=membership,
            invited_by=inviter_player_id,
        )
        self.add_event(event)

    def leave(self, player_id: PlayerId) -> None:
        """ギルドから脱退する。"""
        membership = self._members.get(player_id)
        if membership is None:
            raise CannotLeaveGuildException(
                f"Player {player_id} is not a member of guild {self.guild_id}"
            )
        if membership.role == GuildRole.LEADER:
            # リーダーは脱退前に後継者を決める必要がある（Phase 5 で詳細化）
            if len(self._members) <= 1:
                # 1人だけなら脱退＝ギルド実質解散は許可する
                pass
            else:
                raise CannotLeaveGuildException(
                    "Leader cannot leave until a successor is appointed. Use change_role first."
                )
        del self._members[player_id]
        event = GuildMemberLeftEvent.create(
            aggregate_id=self.guild_id,
            aggregate_type="GuildAggregate",
            player_id=player_id,
            role=membership.role,
        )
        self.add_event(event)

    def change_role(
        self,
        changer_player_id: PlayerId,
        target_player_id: PlayerId,
        new_role: GuildRole,
    ) -> None:
        """役職を変更する。変更者はオフィサー以上である必要がある。"""
        changer = self._members.get(changer_player_id)
        if changer is None:
            raise NotGuildMemberException(
                f"Changer {changer_player_id} is not a member of guild {self.guild_id}"
            )
        if not changer.can_change_role():
            raise InsufficientGuildPermissionException(
                f"Player {changer_player_id} cannot change roles (role={changer.role})"
            )
        target = self._members.get(target_player_id)
        if target is None:
            raise NotGuildMemberException(
                f"Target {target_player_id} is not a member of guild {self.guild_id}"
            )
        if target.role == new_role:
            return
        # リーダーは自分を降格できない（別のリーダーを任命してから脱退する）
        if target_player_id == changer_player_id and target.role == GuildRole.LEADER:
            raise CannotChangeRoleException(
                "Leader cannot demote themselves. Appoint another leader first."
            )
        old_role = target.role
        new_membership = GuildMembership(
            player_id=target_player_id,
            role=new_role,
            joined_at=target.joined_at,
            contribution_points=target.contribution_points,
        )
        self._members[target_player_id] = new_membership
        event = GuildRoleChangedEvent.create(
            aggregate_id=self.guild_id,
            aggregate_type="GuildAggregate",
            player_id=target_player_id,
            old_role=old_role,
            new_role=new_role,
            changed_by=changer_player_id,
        )
        self.add_event(event)

    @property
    def members(self) -> Dict[PlayerId, GuildMembership]:
        return dict(self._members)

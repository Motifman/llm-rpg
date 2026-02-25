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
    CannotDisbandGuildException,
)
from ai_rpg_world.domain.guild.event.guild_event import (
    GuildCreatedEvent,
    GuildMemberJoinedEvent,
    GuildMemberLeftEvent,
    GuildRoleChangedEvent,
    GuildDisbandedEvent,
)
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.guild.value_object.guild_membership import GuildMembership
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId


class GuildAggregate(AggregateRoot):
    """ギルド集約。1ロケーションに1ギルドのみ開設可能（LocationEstablishment で保証）。"""

    def __init__(
        self,
        guild_id: GuildId,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
        name: str,
        description: str,
        members: Optional[Dict[PlayerId, GuildMembership]] = None,
    ):
        super().__init__()
        self.guild_id = guild_id
        self._spot_id = spot_id
        self._location_area_id = location_area_id
        self.name = name
        self.description = description
        self._members: Dict[PlayerId, GuildMembership] = dict(members) if members else {}

    @property
    def spot_id(self) -> SpotId:
        return self._spot_id

    @property
    def location_area_id(self) -> LocationAreaId:
        return self._location_area_id

    @classmethod
    def create_guild(
        cls,
        guild_id: GuildId,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
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
            spot_id=spot_id,
            location_area_id=location_area_id,
            name=name.strip(),
            description=description.strip(),
            members={creator_player_id: membership},
        )
        event = GuildCreatedEvent.create(
            aggregate_id=guild_id,
            aggregate_type="GuildAggregate",
            name=guild.name,
            description=guild.description,
            spot_id=spot_id,
            location_area_id=location_area_id,
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

    def _assign_successor_leader(self, leaving_player_id: PlayerId) -> None:
        """リーダー脱退時に後継リーダーを任命する。貢献度は未実装のため joined_at が最も古いオフィサー、いなければ最も古いメンバーを昇格させる。"""
        candidates = [
            (pid, m)
            for pid, m in self._members.items()
            if pid != leaving_player_id
        ]
        if not candidates:
            return
        # オフィサーを joined_at 昇順、次にメンバーを joined_at 昇順で並べ、先頭をリーダーに
        officers = [(pid, m) for pid, m in candidates if m.role == GuildRole.OFFICER]
        members_only = [(pid, m) for pid, m in candidates if m.role == GuildRole.MEMBER]
        officers.sort(key=lambda x: x[1].joined_at)
        members_only.sort(key=lambda x: x[1].joined_at)
        successor_candidates = officers + members_only
        if not successor_candidates:
            return
        new_leader_id, new_leader_membership = successor_candidates[0]
        new_membership = GuildMembership(
            player_id=new_leader_id,
            role=GuildRole.LEADER,
            joined_at=new_leader_membership.joined_at,
            contribution_points=new_leader_membership.contribution_points,
        )
        self._members[new_leader_id] = new_membership
        event = GuildRoleChangedEvent.create(
            aggregate_id=self.guild_id,
            aggregate_type="GuildAggregate",
            player_id=new_leader_id,
            old_role=new_leader_membership.role,
            new_role=GuildRole.LEADER,
            changed_by=leaving_player_id,
        )
        self.add_event(event)

    def leave(self, player_id: PlayerId) -> None:
        """ギルドから脱退する。リーダー脱退時は joined_at が最も古いオフィサー（いなければメンバー）を後継リーダーに任命する。"""
        membership = self._members.get(player_id)
        if membership is None:
            raise CannotLeaveGuildException(
                f"Player {player_id} is not a member of guild {self.guild_id}"
            )
        if membership.role == GuildRole.LEADER and len(self._members) > 1:
            self._assign_successor_leader(player_id)
        del self._members[player_id]
        event = GuildMemberLeftEvent.create(
            aggregate_id=self.guild_id,
            aggregate_type="GuildAggregate",
            player_id=player_id,
            role=membership.role,
        )
        self.add_event(event)

    def disband(self, disbanded_by: PlayerId) -> None:
        """ギルドを解散する。リーダーのみ実行可能。権限チェックはアプリ層でも行う。"""
        membership = self._members.get(disbanded_by)
        if membership is None:
            raise NotGuildMemberException(
                f"Player {disbanded_by} is not a member of guild {self.guild_id}"
            )
        if membership.role != GuildRole.LEADER:
            raise CannotDisbandGuildException(
                "Only the guild leader can disband the guild"
            )
        self.add_event(
            GuildDisbandedEvent.create(
                aggregate_id=self.guild_id,
                aggregate_type="GuildAggregate",
                disbanded_by=disbanded_by,
            )
        )

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

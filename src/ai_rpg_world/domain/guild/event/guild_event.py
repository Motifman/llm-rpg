from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.guild.value_object.guild_membership import GuildMembership
from ai_rpg_world.domain.guild.enum.guild_enum import GuildRole
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@dataclass(frozen=True)
class GuildCreatedEvent(BaseDomainEvent[GuildId, "GuildAggregate"]):
    """ギルド作成イベント"""
    name: str
    description: str
    creator_player_id: PlayerId
    creator_role: GuildRole


@dataclass(frozen=True)
class GuildMemberJoinedEvent(BaseDomainEvent[GuildId, "GuildAggregate"]):
    """ギルドメンバー参加イベント"""
    membership: GuildMembership
    invited_by: Optional[PlayerId] = None


@dataclass(frozen=True)
class GuildMemberLeftEvent(BaseDomainEvent[GuildId, "GuildAggregate"]):
    """ギルドメンバー脱退イベント"""
    player_id: PlayerId
    role: GuildRole


@dataclass(frozen=True)
class GuildRoleChangedEvent(BaseDomainEvent[GuildId, "GuildAggregate"]):
    """ギルド役職変更イベント"""
    player_id: PlayerId
    old_role: GuildRole
    new_role: GuildRole
    changed_by: PlayerId


@dataclass(frozen=True)
class GuildBankDepositedEvent(BaseDomainEvent[GuildId, "GuildBankAggregate"]):
    """ギルド金庫入金イベント"""
    amount: int
    deposited_by: PlayerId


@dataclass(frozen=True)
class GuildBankWithdrawnEvent(BaseDomainEvent[GuildId, "GuildBankAggregate"]):
    """ギルド金庫出金イベント"""
    amount: int
    withdrawn_by: PlayerId


@dataclass(frozen=True)
class GuildDisbandedEvent(BaseDomainEvent[GuildId, "GuildAggregate"]):
    """ギルド解散イベント（リーダーによる解散）"""
    disbanded_by: PlayerId

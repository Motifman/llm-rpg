"""ギルド系イベントの観測配信先解決戦略"""

from typing import Any, List, Optional

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
)
from ai_rpg_world.domain.guild.event.guild_event import (
    GuildBankDepositedEvent,
    GuildBankWithdrawnEvent,
    GuildCreatedEvent,
    GuildDisbandedEvent,
    GuildMemberJoinedEvent,
    GuildMemberLeftEvent,
    GuildRoleChangedEvent,
)
from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class GuildRecipientStrategy(IRecipientResolutionStrategy):
    """ギルドイベントの配信先を解決する。"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        guild_repository: Optional[GuildRepository] = None,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._guild_repository = guild_repository

    def supports(self, event: Any) -> bool:
        return isinstance(
            event,
            (
                GuildCreatedEvent,
                GuildMemberJoinedEvent,
                GuildMemberLeftEvent,
                GuildRoleChangedEvent,
                GuildBankDepositedEvent,
                GuildBankWithdrawnEvent,
                GuildDisbandedEvent,
            ),
        )

    def resolve(self, event: Any) -> List[PlayerId]:
        if isinstance(event, GuildCreatedEvent):
            return [event.creator_player_id] + self._players_at_spot(event.spot_id)

        if isinstance(event, GuildMemberJoinedEvent):
            # 参加者 + 既存メンバー（取得できる場合）
            member_ids = self._all_member_ids(event.aggregate_id)
            if member_ids:
                return member_ids
            return [event.membership.player_id]

        if isinstance(event, GuildMemberLeftEvent):
            member_ids = self._all_member_ids(event.aggregate_id)
            if member_ids:
                return member_ids + [event.player_id]
            return [event.player_id]

        if isinstance(event, GuildRoleChangedEvent):
            member_ids = self._all_member_ids(event.aggregate_id)
            if member_ids:
                return member_ids
            return [event.player_id, event.changed_by]

        if isinstance(event, (GuildBankDepositedEvent, GuildBankWithdrawnEvent, GuildDisbandedEvent)):
            member_ids = self._all_member_ids(event.aggregate_id)
            if member_ids:
                return member_ids
            if isinstance(event, GuildBankDepositedEvent):
                return [event.deposited_by]
            if isinstance(event, GuildBankWithdrawnEvent):
                return [event.withdrawn_by]
            if isinstance(event, GuildDisbandedEvent):
                return [event.disbanded_by]
            return []

        return []

    def _players_at_spot(self, spot_id: SpotId) -> List[PlayerId]:
        all_statuses = self._player_status_repository.find_all()
        return [
            s.player_id
            for s in all_statuses
            if s.current_spot_id is not None and s.current_spot_id.value == spot_id.value
        ]

    def _all_member_ids(self, guild_id) -> List[PlayerId]:
        if self._guild_repository is None:
            return []
        guild = self._guild_repository.find_by_id(guild_id)
        if guild is None:
            return []
        return list(guild.members.keys())


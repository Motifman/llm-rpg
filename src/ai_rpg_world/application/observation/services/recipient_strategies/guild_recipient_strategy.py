"""ギルド系イベントの観測配信先解決戦略"""

from typing import Any, List, Optional

from ai_rpg_world.application.observation.contracts.interfaces import (
    IPlayerAudienceQueryPort,
    IRecipientResolutionStrategy,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
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
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class GuildRecipientStrategy(IRecipientResolutionStrategy):
    """ギルドイベントの配信先を解決する。"""

    _STRATEGY_KEY = "guild"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        player_audience_query: IPlayerAudienceQueryPort,
        guild_repository: Optional[GuildRepository] = None,
    ) -> None:
        self._registry = observed_event_registry
        self._player_audience_query = player_audience_query
        self._guild_repository = guild_repository

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    def resolve(self, event: Any) -> List[PlayerId]:
        if isinstance(event, GuildCreatedEvent):
            return [event.creator_player_id] + self._player_audience_query.players_at_spot(
                event.spot_id
            )

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

    def _all_member_ids(self, guild_id) -> List[PlayerId]:
        if self._guild_repository is None:
            return []
        guild = self._guild_repository.find_by_id(guild_id)
        if guild is None:
            return []
        return list(guild.members.keys())


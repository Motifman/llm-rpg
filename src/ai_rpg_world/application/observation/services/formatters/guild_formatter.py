"""ギルドイベント用の観測 formatter。"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
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
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class GuildObservationFormatter:
    """GuildCreatedEvent / GuildMemberJoinedEvent / GuildBankDepositedEvent 等を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, GuildCreatedEvent):
            return self._format_guild_created(event, recipient_player_id)
        if isinstance(event, GuildMemberJoinedEvent):
            return self._format_guild_member_joined(event, recipient_player_id)
        if isinstance(event, GuildMemberLeftEvent):
            return self._format_guild_member_left(event, recipient_player_id)
        if isinstance(event, GuildRoleChangedEvent):
            return self._format_guild_role_changed(event, recipient_player_id)
        if isinstance(event, GuildBankDepositedEvent):
            return self._format_guild_bank_deposited(event, recipient_player_id)
        if isinstance(event, GuildBankWithdrawnEvent):
            return self._format_guild_bank_withdrawn(event, recipient_player_id)
        if isinstance(event, GuildDisbandedEvent):
            return self._format_guild_disbanded(event, recipient_player_id)
        return None

    def _format_guild_created(
        self, event: GuildCreatedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"ギルド「{event.name}」が創設されました。"
        guild_id_value = event.aggregate_id.value
        structured = {
            "type": "guild_created",
            "guild_name": event.name,
            "guild_id_value": guild_id_value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
        )

    def _format_guild_member_joined(
        self, event: GuildMemberJoinedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        member_name = self._context.name_resolver.player_name(event.membership.player_id)
        prose = f"{member_name}がギルドに加入しました。"
        guild_id_value = event.aggregate_id.value
        structured = {
            "type": "guild_member_joined",
            "member": member_name,
            "guild_id_value": guild_id_value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
        )

    def _format_guild_member_left(
        self, event: GuildMemberLeftEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        member_name = self._context.name_resolver.player_name(event.player_id)
        prose = f"{member_name}がギルドから脱退しました。"
        guild_id_value = event.aggregate_id.value
        structured = {
            "type": "guild_member_left",
            "member": member_name,
            "role": event.role.value,
            "guild_id_value": guild_id_value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
        )

    def _format_guild_role_changed(
        self, event: GuildRoleChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        member_name = self._context.name_resolver.player_name(event.player_id)
        prose = f"{member_name}の役職が{event.old_role.value}から{event.new_role.value}に変わりました。"
        guild_id_value = event.aggregate_id.value
        structured = {
            "type": "guild_role_changed",
            "member": member_name,
            "old": event.old_role.value,
            "new": event.new_role.value,
            "guild_id_value": guild_id_value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
        )

    def _format_guild_bank_deposited(
        self, event: GuildBankDepositedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        actor = self._context.name_resolver.player_name(event.deposited_by)
        prose = f"{actor}がギルド金庫に{event.amount}ゴールドを入金しました。"
        guild_id_value = event.aggregate_id.value
        structured = {
            "type": "guild_bank_deposited",
            "amount": event.amount,
            "by": actor,
            "guild_id_value": guild_id_value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
        )

    def _format_guild_bank_withdrawn(
        self, event: GuildBankWithdrawnEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        actor = self._context.name_resolver.player_name(event.withdrawn_by)
        prose = f"{actor}がギルド金庫から{event.amount}ゴールドを出金しました。"
        guild_id_value = event.aggregate_id.value
        structured = {
            "type": "guild_bank_withdrawn",
            "amount": event.amount,
            "by": actor,
            "guild_id_value": guild_id_value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
        )

    def _format_guild_disbanded(
        self, event: GuildDisbandedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "ギルドが解散しました。"
        guild_id_value = event.aggregate_id.value
        structured = {
            "type": "guild_disbanded",
            "guild_id_value": guild_id_value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
        )

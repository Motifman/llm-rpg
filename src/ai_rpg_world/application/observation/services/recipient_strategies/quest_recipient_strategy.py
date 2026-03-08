"""クエスト系イベントの観測配信先解決戦略"""

from typing import Any, List, Optional

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
)
from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.quest.event.quest_event import (
    QuestAcceptedEvent,
    QuestApprovedEvent,
    QuestCancelledEvent,
    QuestCompletedEvent,
    QuestIssuedEvent,
    QuestPendingApprovalEvent,
)
from ai_rpg_world.domain.quest.repository.quest_repository import QuestRepository
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope


class QuestRecipientStrategy(IRecipientResolutionStrategy):
    """クエストイベントの配信先を解決する。"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        quest_repository: Optional[QuestRepository] = None,
        guild_repository: Optional[GuildRepository] = None,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._quest_repository = quest_repository
        self._guild_repository = guild_repository

    def supports(self, event: Any) -> bool:
        return isinstance(
            event,
            (
                QuestIssuedEvent,
                QuestAcceptedEvent,
                QuestCompletedEvent,
                QuestPendingApprovalEvent,
                QuestApprovedEvent,
                QuestCancelledEvent,
            ),
        )

    def resolve(self, event: Any) -> List[PlayerId]:
        if isinstance(event, QuestAcceptedEvent):
            return [event.acceptor_player_id]

        if isinstance(event, QuestCompletedEvent):
            return [event.acceptor_player_id]

        if isinstance(event, QuestIssuedEvent):
            return self._resolve_by_scope(event.scope)

        if isinstance(event, QuestPendingApprovalEvent):
            # ギルド掲示: ギルドメンバーに通知（取得できない場合は scope 解決へフォールバック）
            if event.scope is not None and hasattr(event.scope, "is_guild") and event.scope.is_guild():
                member_ids = self._guild_member_ids(event.guild_id)
                if member_ids:
                    return member_ids
            # それ以外は scope に従う
            return self._resolve_by_scope(event.scope)

        if isinstance(event, (QuestApprovedEvent, QuestCancelledEvent)):
            if self._quest_repository is None:
                return []
            quest = self._quest_repository.find_by_id(event.aggregate_id)
            if quest is None:
                return []
            recipients: List[PlayerId] = []
            if quest.acceptor_player_id is not None:
                recipients.append(quest.acceptor_player_id)
            if quest.issuer_player_id is not None:
                recipients.append(quest.issuer_player_id)
            # scope が direct の場合は対象へ
            if quest.scope is not None and isinstance(quest.scope, QuestScope) and quest.scope.is_direct():
                if quest.scope.target_player_id is not None:
                    recipients.append(quest.scope.target_player_id)
            # 重複は Resolver が除去する
            return recipients

        return []

    def _resolve_by_scope(self, scope: QuestScope) -> List[PlayerId]:
        if scope.is_direct() and scope.target_player_id is not None:
            return [scope.target_player_id]
        if scope.is_guild():
            return self._guild_member_ids(scope.guild_id)
        return self._all_known_player_ids()

    def _all_known_player_ids(self) -> List[PlayerId]:
        """公開クエストは現在ワールドに存在する全プレイヤーへ配信する。"""
        all_statuses = self._player_status_repository.find_all()
        return [s.player_id for s in all_statuses]

    def _guild_member_ids(self, guild_id_value: Optional[int]) -> List[PlayerId]:
        """int で保持される guild_id を GuildId に変換してギルドメンバーを返す。"""
        if self._guild_repository is None or guild_id_value is None:
            return []
        try:
            guild_id = GuildId(guild_id_value)
        except (TypeError, ValueError):
            return []
        guild = self._guild_repository.find_by_id(guild_id)
        if guild is None:
            return []
        return list(guild.members.keys())


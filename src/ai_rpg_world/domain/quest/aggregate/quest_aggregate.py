from typing import Optional, List, Tuple
from datetime import datetime

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.quest.enum.quest_enum import QuestStatus, QuestObjectiveType
from ai_rpg_world.domain.quest.exception.quest_exception import (
    InvalidQuestStatusException,
    CannotAcceptQuestException,
    CannotCancelQuestException,
    QuestObjectivesNotCompleteException,
)
from ai_rpg_world.domain.quest.event.quest_event import (
    QuestIssuedEvent,
    QuestPendingApprovalEvent,
    QuestApprovedEvent,
    QuestAcceptedEvent,
    QuestCompletedEvent,
    QuestCancelledEvent,
)
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope
from ai_rpg_world.domain.quest.value_object.quest_objective import QuestObjective
from ai_rpg_world.domain.quest.value_object.quest_reward import QuestReward
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId


class QuestAggregate(AggregateRoot):
    """クエスト集約"""

    def __init__(
        self,
        quest_id: QuestId,
        status: QuestStatus,
        objectives: List[QuestObjective],
        reward: QuestReward,
        scope: QuestScope,
        issuer_player_id: Optional[PlayerId] = None,
        guild_id: Optional[int] = None,
        acceptor_player_id: Optional[PlayerId] = None,
        reserved_gold: int = 0,
        reserved_item_instance_ids: Tuple[ItemInstanceId, ...] = (),
        version: int = 0,
        created_at: Optional[datetime] = None,
    ):
        super().__init__()
        self.quest_id = quest_id
        self.status = status
        self.objectives = list(objectives)
        self.reward = reward
        self.scope = scope
        self.issuer_player_id = issuer_player_id
        self.guild_id = guild_id
        self.acceptor_player_id = acceptor_player_id
        self.reserved_gold = reserved_gold
        self.reserved_item_instance_ids = reserved_item_instance_ids
        self.version = version
        self.created_at = created_at or datetime.now()

    @classmethod
    def issue_quest(
        cls,
        quest_id: QuestId,
        objectives: List[QuestObjective],
        reward: QuestReward,
        scope: QuestScope,
        issuer_player_id: Optional[PlayerId] = None,
        guild_id: Optional[int] = None,
        reserved_gold: int = 0,
        reserved_item_instance_ids: Tuple[ItemInstanceId, ...] = (),
    ) -> "QuestAggregate":
        """クエストを発行する。ギルド掲示時は guild_id を渡すと status=PENDING_APPROVAL になる。"""
        if not objectives:
            raise ValueError("objectives must not be empty")
        status = QuestStatus.PENDING_APPROVAL if guild_id is not None else QuestStatus.OPEN
        quest = cls(
            quest_id=quest_id,
            status=status,
            objectives=objectives,
            reward=reward,
            scope=scope,
            issuer_player_id=issuer_player_id,
            guild_id=guild_id,
            acceptor_player_id=None,
            reserved_gold=reserved_gold,
            reserved_item_instance_ids=reserved_item_instance_ids,
            version=0,
        )
        if status == QuestStatus.PENDING_APPROVAL:
            event = QuestPendingApprovalEvent.create(
                aggregate_id=quest_id,
                aggregate_type="QuestAggregate",
                guild_id=guild_id,
                issuer_player_id=issuer_player_id,
                scope=scope,
                reward=reward,
            )
        else:
            event = QuestIssuedEvent.create(
                aggregate_id=quest_id,
                aggregate_type="QuestAggregate",
                issuer_player_id=issuer_player_id,
                scope=scope,
                reward=reward,
            )
        quest.add_event(event)
        return quest

    def is_pending_approval(self) -> bool:
        return self.status == QuestStatus.PENDING_APPROVAL

    def approve_by(self, approver_player_id: PlayerId) -> None:
        """ギルド掲示クエストを承認して OPEN にする。権限チェックはアプリ層で行う。"""
        if self.status != QuestStatus.PENDING_APPROVAL:
            raise InvalidQuestStatusException(
                f"Quest is not pending approval: {self.status}"
            )
        self.status = QuestStatus.OPEN
        event = QuestApprovedEvent.create(
            aggregate_id=self.quest_id,
            aggregate_type="QuestAggregate",
            approved_by=approver_player_id,
        )
        self.add_event(event)

    def is_open(self) -> bool:
        return self.status == QuestStatus.OPEN

    def is_accepted(self) -> bool:
        return self.status == QuestStatus.ACCEPTED

    def is_completed(self) -> bool:
        return self.status == QuestStatus.COMPLETED

    def is_cancelled(self) -> bool:
        return self.status == QuestStatus.CANCELLED

    def can_be_accepted_by(self, player_id: PlayerId) -> bool:
        """指定プレイヤーが受託可能か"""
        if self.status != QuestStatus.OPEN:
            return False
        if self.scope.is_direct() and self.scope.target_player_id != player_id:
            return False
        if self.scope.is_guild():
            # Phase 3: ギルドメンバーかどうかはアプリ層でチェック
            pass
        return True

    def accept_by(self, player_id: PlayerId) -> None:
        """クエストを受託する"""
        if self.status != QuestStatus.OPEN:
            raise InvalidQuestStatusException(f"Quest is not open: {self.status}")
        if not self.can_be_accepted_by(player_id):
            raise CannotAcceptQuestException(
                f"Player {player_id} cannot accept quest {self.quest_id}"
            )
        self.acceptor_player_id = player_id
        self.status = QuestStatus.ACCEPTED
        event = QuestAcceptedEvent.create(
            aggregate_id=self.quest_id,
            aggregate_type="QuestAggregate",
            acceptor_player_id=player_id,
        )
        self.add_event(event)

    def advance_objective(
        self,
        objective_type: QuestObjectiveType,
        target_id: int,
        target_id_secondary: Optional[int] = None,
    ) -> bool:
        """
        指定した目標の進捗を 1 進める。
        該当する目標がなければ False、進めたら True。
        既に達成済みの目標は変更しない（True を返す）。
        TAKE_FROM_CHEST など target_id_secondary を持つ目標は両方一致で判定する。
        """
        if self.status != QuestStatus.ACCEPTED:
            return False
        for i, obj in enumerate(self.objectives):
            type_ok = obj.objective_type == objective_type
            primary_ok = obj.target_id == target_id
            secondary_ok = (
                obj.target_id_secondary == target_id_secondary
                if obj.target_id_secondary is not None
                else target_id_secondary is None
            )
            if type_ok and primary_ok and secondary_ok:
                if obj.is_completed():
                    return True
                self.objectives[i] = obj.with_progress(1)
                return True
        return False

    def is_all_objectives_completed(self) -> bool:
        return all(obj.is_completed() for obj in self.objectives)

    def complete(self) -> None:
        """クエストを完了する（全目標達成時のみ呼ぶ）"""
        if self.status != QuestStatus.ACCEPTED:
            raise InvalidQuestStatusException(f"Quest is not accepted: {self.status}")
        if not self.is_all_objectives_completed():
            raise QuestObjectivesNotCompleteException(
                "Cannot complete quest: not all objectives completed"
            )
        self.status = QuestStatus.COMPLETED
        event = QuestCompletedEvent.create(
            aggregate_id=self.quest_id,
            aggregate_type="QuestAggregate",
            acceptor_player_id=self.acceptor_player_id,
            reward=self.reward,
        )
        self.add_event(event)

    def is_issuer_or_acceptor(self, player_id: PlayerId) -> bool:
        if self.issuer_player_id and self.issuer_player_id == player_id:
            return True
        if self.acceptor_player_id and self.acceptor_player_id == player_id:
            return True
        return False

    def cancel_by(self, player_id: PlayerId) -> None:
        """クエストをキャンセルする（発行者または受託者のみ）"""
        if self.status not in (QuestStatus.OPEN, QuestStatus.ACCEPTED):
            raise InvalidQuestStatusException(f"Quest cannot be cancelled: {self.status}")
        if not self.is_issuer_or_acceptor(player_id):
            raise CannotCancelQuestException(
                f"Player {player_id} is not issuer or acceptor of quest {self.quest_id}"
            )
        self.status = QuestStatus.CANCELLED
        event = QuestCancelledEvent.create(
            aggregate_id=self.quest_id,
            aggregate_type="QuestAggregate",
        )
        self.add_event(event)

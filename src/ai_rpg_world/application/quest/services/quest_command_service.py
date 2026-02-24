import logging
from typing import Callable, Any, List, Tuple, Optional
from datetime import datetime

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.quest.aggregate.quest_aggregate import QuestAggregate
from ai_rpg_world.domain.quest.enum.quest_enum import QuestObjectiveType
from ai_rpg_world.domain.quest.repository.quest_repository import QuestRepository
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope
from ai_rpg_world.domain.quest.value_object.quest_objective import QuestObjective
from ai_rpg_world.domain.quest.value_object.quest_reward import QuestReward
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId

from ai_rpg_world.application.quest.contracts.commands import (
    IssueQuestCommand,
    AcceptQuestCommand,
    ApproveQuestCommand,
    CancelQuestCommand,
)
from ai_rpg_world.application.quest.contracts.dtos import QuestCommandResultDto
from ai_rpg_world.application.quest.exceptions.base_exception import (
    QuestApplicationException,
    QuestSystemErrorException,
)
from ai_rpg_world.application.quest.exceptions.command.quest_command_exception import (
    QuestCommandException,
    QuestCreationException,
    QuestNotFoundForCommandException,
    QuestAccessDeniedException,
)


def _parse_objective_type(s: str) -> QuestObjectiveType:
    """コマンドの文字列を QuestObjectiveType に変換"""
    try:
        return QuestObjectiveType(s)
    except ValueError:
        raise QuestCreationException(f"Invalid objective type: {s}")


def _find_slots_for_reward_item(
    inventory: Any,
    item_repository: ItemRepository,
    item_spec_id: ItemSpecId,
    quantity_needed: int,
) -> List[Tuple[SlotId, ItemInstanceId]]:
    """
    発行者インベントリから指定 item_spec_id のアイテムが quantity_needed 以上あるスロットを
    見つけ、予約用に (SlotId, ItemInstanceId) のリストを返す。スロットは先頭から使用する。
    """
    candidates: List[Tuple[SlotId, ItemInstanceId, int]] = []
    for i in range(inventory.max_slots):
        slot_id = SlotId(i)
        instance_id = inventory.get_item_instance_id_by_slot(slot_id)
        if instance_id is None:
            continue
        if inventory.is_item_reserved(instance_id):
            continue
        item_aggregate = item_repository.find_by_id(instance_id)
        if item_aggregate is None:
            continue
        if item_aggregate.item_spec.item_spec_id != item_spec_id:
            continue
        candidates.append((slot_id, instance_id, item_aggregate.quantity))
    # スロット番号順で確定性を保つ
    candidates.sort(key=lambda x: x[0].value)
    result: List[Tuple[SlotId, ItemInstanceId]] = []
    total = 0
    for slot_id, instance_id, qty in candidates:
        if total >= quantity_needed:
            break
        result.append((slot_id, instance_id))
        total += qty
    if total < quantity_needed:
        return []
    return result


class QuestCommandService:
    """クエストコマンドサービス"""

    def __init__(
        self,
        quest_repository: QuestRepository,
        unit_of_work: UnitOfWork,
        player_status_repository: Optional[PlayerStatusRepository] = None,
        player_inventory_repository: Optional[PlayerInventoryRepository] = None,
        item_repository: Optional[ItemRepository] = None,
        guild_repository: Optional[GuildRepository] = None,
    ):
        self._quest_repository = quest_repository
        self._unit_of_work = unit_of_work
        self._player_status_repository = player_status_repository
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._guild_repository = guild_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(
        self, operation: Callable[[], Any], context: dict
    ) -> Any:
        try:
            return operation()
        except QuestApplicationException:
            raise
        except DomainException as e:
            raise QuestCommandException(
                str(e),
                user_id=context.get("user_id"),
                quest_id=context.get("quest_id"),
            ) from e
        except Exception as e:
            self._logger.error(
                "Unexpected error in %s: %s",
                context.get("action", "unknown"),
                str(e),
                extra=context,
            )
            raise QuestSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            ) from e

    def issue_quest(self, command: IssueQuestCommand) -> QuestCommandResultDto:
        """クエストを発行する（システム発行またはプレイヤー発行）"""
        return self._execute_with_error_handling(
            operation=lambda: self._issue_quest_impl(command),
            context={
                "action": "issue_quest",
                "user_id": command.issuer_player_id,
            },
        )

    def _issue_quest_impl(self, command: IssueQuestCommand) -> QuestCommandResultDto:
        with self._unit_of_work:
            objectives = []
            for obj_type_str, target_id, required_count in command.objectives:
                ot = _parse_objective_type(obj_type_str)
                objectives.append(
                    QuestObjective(
                        objective_type=ot,
                        target_id=target_id,
                        required_count=required_count,
                        current_count=0,
                    )
                )
            if not objectives:
                raise QuestCreationException(
                    "クエストには1件以上の目標が必要です",
                    user_id=command.issuer_player_id,
                )
            item_rewards = []
            if command.reward_items:
                for item_spec_id_val, qty in command.reward_items:
                    item_rewards.append((ItemSpecId(item_spec_id_val), qty))
            reward = QuestReward.of(
                gold=command.reward_gold,
                exp=command.reward_exp,
                item_rewards=item_rewards,
            )
            if command.guild_id is not None:
                scope = QuestScope.guild_scope(command.guild_id)
            else:
                scope = QuestScope.public_scope()
            issuer_player_id: Optional[PlayerId] = None
            reserved_gold = 0
            reserved_item_instance_ids: Tuple[ItemInstanceId, ...] = ()

            if command.issuer_player_id is not None:
                issuer_player_id = PlayerId(command.issuer_player_id)
                if command.reward_exp > 0:
                    raise QuestCreationException(
                        "プレイヤー発行クエストでは経験値報酬を指定できません",
                        user_id=command.issuer_player_id,
                    )
                if self._player_status_repository is None or self._player_inventory_repository is None or self._item_repository is None:
                    raise QuestCreationException(
                        "プレイヤー発行には PlayerStatus / Inventory / Item リポジトリが必要です",
                        user_id=command.issuer_player_id,
                    )
                issuer_status = self._player_status_repository.find_by_id(issuer_player_id)
                if issuer_status is None:
                    raise QuestCreationException(
                        f"発行者が見つかりません: {command.issuer_player_id}",
                        user_id=command.issuer_player_id,
                    )
                issuer_inventory = self._player_inventory_repository.find_by_id(issuer_player_id)
                if issuer_inventory is None:
                    raise QuestCreationException(
                        f"発行者のインベントリが見つかりません: {command.issuer_player_id}",
                        user_id=command.issuer_player_id,
                    )
                if command.reward_gold > 0:
                    if issuer_status.gold.value < command.reward_gold:
                        raise QuestCreationException(
                            f"報酬に必要なゴールドが不足しています。必要: {command.reward_gold}, 所持: {issuer_status.gold.value}",
                            user_id=command.issuer_player_id,
                        )
                reserved_ids: List[ItemInstanceId] = []
                if command.reward_items:
                    for item_spec_id, qty in item_rewards:
                        slots_to_reserve = _find_slots_for_reward_item(
                            issuer_inventory,
                            self._item_repository,
                            item_spec_id,
                            qty,
                        )
                        if not slots_to_reserve:
                            raise QuestCreationException(
                                f"報酬アイテムが不足しています。item_spec_id={item_spec_id.value}, 必要数={qty}",
                                user_id=command.issuer_player_id,
                            )
                        for slot_id, instance_id in slots_to_reserve:
                            issuer_inventory.reserve_item(slot_id)
                            reserved_ids.append(instance_id)
                issuer_status.pay_gold(command.reward_gold)
                reserved_gold = command.reward_gold
                reserved_item_instance_ids = tuple(reserved_ids)
                self._player_status_repository.save(issuer_status)
                self._player_inventory_repository.save(issuer_inventory)

            quest_id = self._quest_repository.generate_quest_id()
            quest = QuestAggregate.issue_quest(
                quest_id=quest_id,
                objectives=objectives,
                reward=reward,
                scope=scope,
                issuer_player_id=issuer_player_id,
                guild_id=command.guild_id,
                reserved_gold=reserved_gold,
                reserved_item_instance_ids=reserved_item_instance_ids,
            )
            self._quest_repository.save(quest)
            self._logger.info("Quest issued: quest_id=%s", quest_id.value)
            return QuestCommandResultDto(
                success=True,
                message="クエストを発行しました",
                data={"quest_id": quest_id.value},
            )

    def approve_quest(self, command: ApproveQuestCommand) -> QuestCommandResultDto:
        """ギルド掲示クエストを承認して OPEN にする（オフィサー以上のみ）"""
        return self._execute_with_error_handling(
            operation=lambda: self._approve_quest_impl(command),
            context={
                "action": "approve_quest",
                "user_id": command.approver_player_id,
                "quest_id": command.quest_id,
            },
        )

    def _approve_quest_impl(self, command: ApproveQuestCommand) -> QuestCommandResultDto:
        with self._unit_of_work:
            quest_id = QuestId(command.quest_id)
            approver_id = PlayerId(command.approver_player_id)
            quest = self._quest_repository.find_by_id(quest_id)
            if quest is None:
                raise QuestNotFoundForCommandException(command.quest_id, "approve_quest")
            if not quest.is_pending_approval():
                raise QuestAccessDeniedException(
                    command.quest_id, command.approver_player_id, "approve_quest"
                )
            if quest.guild_id is None or self._guild_repository is None:
                raise QuestAccessDeniedException(
                    command.quest_id, command.approver_player_id, "approve_quest"
                )
            guild = self._guild_repository.find_by_id(GuildId(quest.guild_id))
            if guild is None:
                raise QuestAccessDeniedException(
                    command.quest_id, command.approver_player_id, "approve_quest"
                )
            if not guild.can_approve_quest(approver_id):
                raise QuestAccessDeniedException(
                    command.quest_id, command.approver_player_id, "approve_quest"
                )
            quest.approve_by(approver_id)
            self._quest_repository.save(quest)
            self._logger.info(
                "Quest approved: quest_id=%s, approver_id=%s",
                command.quest_id,
                command.approver_player_id,
            )
            return QuestCommandResultDto(
                success=True,
                message="クエストを承認しました",
                data={"quest_id": command.quest_id},
            )

    def accept_quest(self, command: AcceptQuestCommand) -> QuestCommandResultDto:
        """クエストを受託する"""
        return self._execute_with_error_handling(
            operation=lambda: self._accept_quest_impl(command),
            context={
                "action": "accept_quest",
                "user_id": command.player_id,
                "quest_id": command.quest_id,
            },
        )

    def _accept_quest_impl(self, command: AcceptQuestCommand) -> QuestCommandResultDto:
        with self._unit_of_work:
            quest_id = QuestId(command.quest_id)
            player_id = PlayerId(command.player_id)
            quest = self._quest_repository.find_by_id(quest_id)
            if quest is None:
                raise QuestNotFoundForCommandException(command.quest_id, "accept_quest")
            if quest.scope.is_guild():
                if quest.guild_id is None or self._guild_repository is None:
                    raise QuestAccessDeniedException(
                        command.quest_id, command.player_id, "accept_quest"
                    )
                guild = self._guild_repository.find_by_id(GuildId(quest.guild_id))
                if guild is None or not guild.is_member(player_id):
                    raise QuestAccessDeniedException(
                        command.quest_id, command.player_id, "accept_quest"
                    )
            if not quest.can_be_accepted_by(player_id):
                raise QuestAccessDeniedException(
                    command.quest_id, command.player_id, "accept_quest"
                )
            quest.accept_by(player_id)
            self._quest_repository.save(quest)
            self._logger.info(
                "Quest accepted: quest_id=%s, player_id=%s",
                command.quest_id,
                command.player_id,
            )
            return QuestCommandResultDto(
                success=True,
                message="クエストを受託しました",
                data={"quest_id": command.quest_id},
            )

    def cancel_quest(self, command: CancelQuestCommand) -> QuestCommandResultDto:
        """クエストをキャンセルする"""
        return self._execute_with_error_handling(
            operation=lambda: self._cancel_quest_impl(command),
            context={
                "action": "cancel_quest",
                "user_id": command.player_id,
                "quest_id": command.quest_id,
            },
        )

    def _cancel_quest_impl(self, command: CancelQuestCommand) -> QuestCommandResultDto:
        with self._unit_of_work:
            quest_id = QuestId(command.quest_id)
            player_id = PlayerId(command.player_id)
            quest = self._quest_repository.find_by_id(quest_id)
            if quest is None:
                raise QuestNotFoundForCommandException(command.quest_id, "cancel_quest")
            if not quest.is_issuer_or_acceptor(player_id):
                raise QuestAccessDeniedException(
                    command.quest_id, command.player_id, "cancel_quest"
                )
            if (
                quest.issuer_player_id is not None
                and (quest.reserved_gold > 0 or quest.reserved_item_instance_ids)
                and self._player_status_repository is not None
                and self._player_inventory_repository is not None
            ):
                issuer_status = self._player_status_repository.find_by_id(
                    quest.issuer_player_id
                )
                issuer_inventory = self._player_inventory_repository.find_by_id(
                    quest.issuer_player_id
                )
                if issuer_status is not None and quest.reserved_gold > 0:
                    issuer_status.earn_gold(quest.reserved_gold)
                    self._player_status_repository.save(issuer_status)
                if issuer_inventory is not None and quest.reserved_item_instance_ids:
                    for item_id in quest.reserved_item_instance_ids:
                        issuer_inventory.unreserve_item(item_id)
                    self._player_inventory_repository.save(issuer_inventory)
            quest.cancel_by(player_id)
            self._quest_repository.save(quest)
            self._logger.info(
                "Quest cancelled: quest_id=%s, player_id=%s",
                command.quest_id,
                command.player_id,
            )
            return QuestCommandResultDto(
                success=True,
                message="クエストをキャンセルしました",
                data={"quest_id": command.quest_id},
            )

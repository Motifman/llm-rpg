import logging
from typing import Callable, Any
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
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId

from ai_rpg_world.application.quest.contracts.commands import (
    IssueQuestCommand,
    AcceptQuestCommand,
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


class QuestCommandService:
    """クエストコマンドサービス"""

    def __init__(self, quest_repository: QuestRepository, unit_of_work: UnitOfWork):
        self._quest_repository = quest_repository
        self._unit_of_work = unit_of_work
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
        """クエストを発行する（Phase 1 ではシステム発行のみ）"""
        return self._execute_with_error_handling(
            operation=lambda: self._issue_quest_impl(command),
            context={"action": "issue_quest"},
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
            item_rewards = []
            if command.reward_items:
                for item_spec_id_val, qty in command.reward_items:
                    item_rewards.append((ItemSpecId(item_spec_id_val), qty))
            reward = QuestReward.of(
                gold=command.reward_gold,
                exp=command.reward_exp,
                item_rewards=item_rewards,
            )
            scope = QuestScope.public_scope()
            quest_id = self._quest_repository.generate_quest_id()
            quest = QuestAggregate.issue_quest(
                quest_id=quest_id,
                objectives=objectives,
                reward=reward,
                scope=scope,
                issuer_player_id=None,
                guild_id=None,
            )
            self._quest_repository.save(quest)
            self._logger.info("Quest issued: quest_id=%s", quest_id.value)
            return QuestCommandResultDto(
                success=True,
                message="クエストを発行しました",
                data={"quest_id": quest_id.value},
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

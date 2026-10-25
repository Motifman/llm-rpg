"""Quest 進捗の非同期ハンドラ群と後方互換ラッパー。"""

import logging
from collections.abc import Callable
from typing import Any

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.quest.exceptions import QuestApplicationException
from ai_rpg_world.application.quest.services.quest_progress_reaction_service import (
    QuestProgressReactionService,
)
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.conversation.event.conversation_event import (
    ConversationEndedEvent,
)
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.player.event.inventory_events import ItemAddedToInventoryEvent
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent


class _AsyncQuestProgressHandler:
    """Quest の反応サービスを別トランザクションで実行する共通基底。"""

    def __init__(
        self,
        reaction_service: QuestProgressReactionService,
        unit_of_work_factory: UnitOfWorkFactory,
    ) -> None:
        self._reaction_service = reaction_service
        self._unit_of_work_factory = unit_of_work_factory
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute(self, operation: Callable[[], None], *, handler_name: str) -> None:
        try:
            self._execute_in_separate_transaction(
                operation,
                context={"handler": handler_name},
            )
        except (ApplicationException, DomainException, QuestApplicationException):
            raise
        except Exception as e:
            self._logger.exception("Unexpected error in %s: %s", self.__class__.__name__, e)
            raise SystemErrorException(
                f"Quest progress handling failed in {handler_name}: {e}",
                original_exception=e,
            ) from e

    def _execute_in_separate_transaction(
        self,
        operation: Callable[[], None],
        context: dict[str, Any],
    ) -> None:
        unit_of_work = self._unit_of_work_factory.create()
        try:
            with unit_of_work:
                operation()
        except (ApplicationException, DomainException, QuestApplicationException):
            raise
        except Exception as e:
            self._logger.exception(
                "Failed to handle event in %s: %s",
                context.get("handler", "unknown"),
                e,
                extra=context,
            )
            raise SystemErrorException(
                f"Quest progress handling failed in {context.get('handler', 'unknown')}: {e}",
                original_exception=e,
            ) from e


class MonsterDiedQuestProgressHandler(
    _AsyncQuestProgressHandler,
    EventHandler[MonsterDiedEvent],
):
    def handle(self, event: MonsterDiedEvent) -> None:
        self._execute(
            lambda: self._reaction_service.process_monster_died(event),
            handler_name="quest_progress_monster_died",
        )


class PlayerDownedQuestProgressHandler(
    _AsyncQuestProgressHandler,
    EventHandler[PlayerDownedEvent],
):
    def handle(self, event: PlayerDownedEvent) -> None:
        self._execute(
            lambda: self._reaction_service.process_player_downed(event),
            handler_name="quest_progress_player_downed",
        )


class ItemAddedToInventoryQuestProgressHandler(
    _AsyncQuestProgressHandler,
    EventHandler[ItemAddedToInventoryEvent],
):
    def handle(self, event: ItemAddedToInventoryEvent) -> None:
        self._execute(
            lambda: self._reaction_service.process_item_added_to_inventory(event),
            handler_name="quest_progress_item_added_to_inventory",
        )


class ConversationEndedQuestProgressHandler(
    _AsyncQuestProgressHandler,
    EventHandler[ConversationEndedEvent],
):
    def handle(self, event: ConversationEndedEvent) -> None:
        self._execute(
            lambda: self._reaction_service.process_conversation_ended(event),
            handler_name="quest_progress_conversation_ended",
        )

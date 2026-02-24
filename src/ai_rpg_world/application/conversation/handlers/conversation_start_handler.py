"""WorldObjectInteractedEvent(TALK) を受けて会話セッションを開始するハンドラ"""
import logging
from typing import Callable, Optional

from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.world.event.map_events import WorldObjectInteractedEvent
from ai_rpg_world.domain.world.enum.world_enum import InteractionTypeEnum
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

from ai_rpg_world.application.conversation.services.conversation_command_service import (
    ConversationCommandService,
)
from ai_rpg_world.application.conversation.contracts.commands import (
    StartConversationCommand,
)


class ConversationStartHandler(EventHandler[WorldObjectInteractedEvent]):
    """WorldObjectInteractedEvent のうち TALK のとき会話セッションを開始する"""

    def __init__(
        self,
        conversation_command_service: ConversationCommandService,
        resolve_player_id_from_actor: Callable[[WorldObjectId], Optional[PlayerId]],
    ):
        self._conversation_command_service = conversation_command_service
        self._resolve_player_id_from_actor = resolve_player_id_from_actor
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: WorldObjectInteractedEvent) -> None:
        if event.interaction_type != InteractionTypeEnum.TALK:
            return
        player_id = self._resolve_player_id_from_actor(event.actor_id)
        if player_id is None:
            self._logger.debug(
                "TALK event: actor_id %s could not be resolved to player, skipping",
                event.actor_id,
            )
            return
        data = event.data or {}
        dialogue_tree_id_raw = data.get("dialogue_tree_id")
        if dialogue_tree_id_raw is None:
            self._logger.debug(
                "TALK event: target %s has no dialogue_tree_id in data, skipping",
                event.target_id,
            )
            return
        try:
            dialogue_tree_id = int(dialogue_tree_id_raw)
        except (TypeError, ValueError):
            self._logger.warning(
                "TALK event: invalid dialogue_tree_id %s for target %s",
                dialogue_tree_id_raw,
                event.target_id,
            )
            return
        command = StartConversationCommand(
            player_id=player_id.value,
            npc_id_value=event.target_id.value,
            dialogue_tree_id=dialogue_tree_id,
        )
        self._conversation_command_service.start_conversation(command)

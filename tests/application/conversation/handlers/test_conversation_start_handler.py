"""ConversationStartHandler のテスト"""
import pytest
from unittest.mock import Mock

from ai_rpg_world.application.conversation.handlers.conversation_start_handler import (
    ConversationStartHandler,
)
from ai_rpg_world.application.conversation.services.conversation_command_service import (
    ConversationCommandService,
)
from ai_rpg_world.domain.world.event.map_events import WorldObjectInteractedEvent
from ai_rpg_world.domain.world.enum.world_enum import InteractionTypeEnum
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TestConversationStartHandler:
    """ConversationStartHandler のテスト"""

    @pytest.fixture
    def conversation_service(self):
        return Mock(spec=ConversationCommandService)

    @pytest.fixture
    def resolve_player_id(self):
        """actor_id を PlayerId に変換。デフォルトは actor_id.value を PlayerId にする"""
        def _resolve(actor_id: WorldObjectId) -> PlayerId:
            return PlayerId.create(actor_id.value)
        return _resolve

    @pytest.fixture
    def handler(self, conversation_service, resolve_player_id):
        return ConversationStartHandler(
            conversation_command_service=conversation_service,
            resolve_player_id_from_actor=resolve_player_id,
        )

    def test_handle_ignores_non_talk_event(self, handler, conversation_service):
        """TALK 以外のインタラクションでは何もしない"""
        event = WorldObjectInteractedEvent.create(
            aggregate_id=WorldObjectId(100),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(100),
            interaction_type=InteractionTypeEnum.OPEN_CHEST,
            data={},
        )
        handler.handle(event)
        conversation_service.start_conversation.assert_not_called()

    def test_handle_starts_conversation_when_talk_and_dialogue_tree_id(
        self, handler, conversation_service
    ):
        """TALK かつ dialogue_tree_id があるとき会話開始"""
        event = WorldObjectInteractedEvent.create(
            aggregate_id=WorldObjectId(100),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(5),
            target_id=WorldObjectId(100),
            interaction_type=InteractionTypeEnum.TALK,
            data={"dialogue_tree_id": 1},
        )
        handler.handle(event)
        conversation_service.start_conversation.assert_called_once()
        call_cmd = conversation_service.start_conversation.call_args[0][0]
        assert call_cmd.player_id == 5
        assert call_cmd.npc_id_value == 100
        assert call_cmd.dialogue_tree_id == 1

    def test_handle_skips_when_no_dialogue_tree_id(self, handler, conversation_service):
        """data に dialogue_tree_id がなければ start_conversation を呼ばない"""
        event = WorldObjectInteractedEvent.create(
            aggregate_id=WorldObjectId(100),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(100),
            interaction_type=InteractionTypeEnum.TALK,
            data={},
        )
        handler.handle(event)
        conversation_service.start_conversation.assert_not_called()

    def test_handle_skips_when_resolve_returns_none(self, conversation_service):
        """resolve が None を返すときは start_conversation を呼ばない"""
        def resolve_none(_):
            return None
        h = ConversationStartHandler(
            conversation_command_service=conversation_service,
            resolve_player_id_from_actor=resolve_none,
        )
        event = WorldObjectInteractedEvent.create(
            aggregate_id=WorldObjectId(100),
            aggregate_type="WorldObject",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(100),
            interaction_type=InteractionTypeEnum.TALK,
            data={"dialogue_tree_id": 1},
        )
        h.handle(event)
        conversation_service.start_conversation.assert_not_called()

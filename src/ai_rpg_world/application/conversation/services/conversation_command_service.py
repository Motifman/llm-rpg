"""会話コマンドサービス（ルールベース会話の開始・進行・終了）"""
import logging
from typing import Callable, Any, Optional, Dict, Tuple

from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.conversation.event.conversation_event import (
    ConversationStartedEvent,
    ConversationEndedEvent,
)
from ai_rpg_world.domain.conversation.repository.dialogue_tree_repository import (
    DialogueTreeRepository,
)
from ai_rpg_world.domain.conversation.value_object.dialogue_tree_id import DialogueTreeId
from ai_rpg_world.domain.conversation.value_object.dialogue_node_id import DialogueNodeId
from ai_rpg_world.domain.conversation.value_object.dialogue_node import DialogueNode
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId

from ai_rpg_world.application.conversation.contracts.commands import (
    StartConversationCommand,
    AdvanceConversationCommand,
    GetCurrentNodeQuery,
)
from ai_rpg_world.application.conversation.contracts.dtos import (
    ConversationNodeDto,
    ConversationSessionDto,
    StartConversationResultDto,
    AdvanceConversationResultDto,
)
from ai_rpg_world.application.conversation.exceptions import (
    ConversationApplicationException,
    ConversationCommandException,
    ConversationSystemErrorException,
    DialogueTreeNotFoundException,
    DialogueNodeNotFoundException,
    NoActiveSessionException,
)


def _node_to_dto(node: DialogueNode) -> ConversationNodeDto:
    has_next = not node.is_terminal and (
        node.next_node_id is not None or len(node.choices) > 0
    )
    return ConversationNodeDto(
        node_id_value=node.node_id,
        text=node.text,
        choices=node.choices,
        is_terminal=node.is_terminal,
        has_next=has_next,
    )


class ConversationCommandService:
    """会話コマンドサービス。ルールベース会話の開始・進行・終端時の報酬付与とイベント発行を行う。"""

    def __init__(
        self,
        dialogue_tree_repository: DialogueTreeRepository,
        event_publisher: EventPublisher,
        player_status_repository: Optional[PlayerStatusRepository] = None,
        player_inventory_repository: Optional[PlayerInventoryRepository] = None,
        item_spec_repository: Optional[ItemSpecRepository] = None,
        item_repository: Optional[ItemRepository] = None,
    ):
        self._dialogue_tree_repository = dialogue_tree_repository
        self._event_publisher = event_publisher
        self._player_status_repository = player_status_repository
        self._player_inventory_repository = player_inventory_repository
        self._item_spec_repository = item_spec_repository
        self._item_repository = item_repository
        # (player_id_value, npc_id_value) -> {"tree_id": DialogueTreeId, "current_node_id": DialogueNodeId}
        self._sessions: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(
        self, operation: Callable[[], Any], context: dict
    ) -> Any:
        try:
            return operation()
        except ConversationApplicationException:
            raise
        except DomainException as e:
            raise ConversationCommandException(str(e), **context) from e
        except Exception as e:
            self._logger.error(
                "Unexpected error in %s: %s",
                context.get("action", "unknown"),
                str(e),
                extra=context,
            )
            raise ConversationSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            ) from e

    def start_conversation(self, command: StartConversationCommand) -> StartConversationResultDto:
        """会話を開始する。エントリノードでセッションを作成し、ConversationStartedEvent を発行する。"""
        return self._execute_with_error_handling(
            operation=lambda: self._start_conversation_impl(command),
            context={"action": "start_conversation", "player_id": command.player_id},
        )

    def _start_conversation_impl(
        self, command: StartConversationCommand
    ) -> StartConversationResultDto:
        tree_id = DialogueTreeId.create(command.dialogue_tree_id)
        entry_node_id = self._dialogue_tree_repository.get_entry_node_id(tree_id)
        if entry_node_id is None:
            raise DialogueTreeNotFoundException(command.dialogue_tree_id)
        node = self._dialogue_tree_repository.get_node(tree_id, entry_node_id)
        if node is None:
            raise DialogueNodeNotFoundException(
                command.dialogue_tree_id, entry_node_id.value
            )
        key = (command.player_id, command.npc_id_value)
        self._sessions[key] = {
            "tree_id": tree_id,
            "current_node_id": entry_node_id,
        }
        player_id = PlayerId.create(command.player_id)
        self._event_publisher.publish(
            ConversationStartedEvent.create(
                aggregate_id=player_id,
                aggregate_type="Conversation",
                npc_id_value=command.npc_id_value,
                dialogue_tree_id_value=command.dialogue_tree_id,
                entry_node_id_value=entry_node_id.value,
            )
        )
        session_dto = ConversationSessionDto(
            player_id=command.player_id,
            npc_id_value=command.npc_id_value,
            dialogue_tree_id_value=command.dialogue_tree_id,
            current_node=_node_to_dto(node),
        )
        return StartConversationResultDto(
            success=True,
            message="会話を開始しました",
            session=session_dto,
        )

    def get_current_node(self, query: GetCurrentNodeQuery) -> Optional[ConversationSessionDto]:
        """現在の会話ノードを返す。セッションがなければ None。"""
        key = (query.player_id, query.npc_id_value)
        session = self._sessions.get(key)
        if not session:
            return None
        tree_id = session["tree_id"]
        current_node_id = session["current_node_id"]
        node = self._dialogue_tree_repository.get_node(tree_id, current_node_id)
        if node is None:
            return None
        return ConversationSessionDto(
            player_id=query.player_id,
            npc_id_value=query.npc_id_value,
            dialogue_tree_id_value=tree_id.value,
            current_node=_node_to_dto(node),
        )

    def advance_conversation(
        self, command: AdvanceConversationCommand
    ) -> AdvanceConversationResultDto:
        """会話を進める。「次へ」または選択肢で次のノードへ。終端ノードなら報酬付与・イベント発行・セッション削除。"""
        return self._execute_with_error_handling(
            operation=lambda: self._advance_conversation_impl(command),
            context={"action": "advance_conversation", "player_id": command.player_id},
        )

    def _advance_conversation_impl(
        self, command: AdvanceConversationCommand
    ) -> AdvanceConversationResultDto:
        key = (command.player_id, command.npc_id_value)
        session = self._sessions.get(key)
        if not session:
            raise NoActiveSessionException(command.player_id, command.npc_id_value)
        tree_id = session["tree_id"]
        current_node_id = session["current_node_id"]
        node = self._dialogue_tree_repository.get_node(tree_id, current_node_id)
        if node is None:
            raise DialogueNodeNotFoundException(tree_id.value, current_node_id.value)
        next_node_id_value: Optional[int] = None
        if command.choice_index is not None:
            if command.choice_index < 0 or command.choice_index >= len(node.choices):
                raise ConversationCommandException(
                    f"無効な選択肢インデックス: {command.choice_index}",
                    player_id=command.player_id,
                    npc_id_value=command.npc_id_value,
                )
            next_node_id_value = node.choices[command.choice_index][1]
        else:
            next_node_id_value = node.next_node_id
        if next_node_id_value is None:
            if node.is_terminal:
                return self._end_conversation(
                    command.player_id,
                    command.npc_id_value,
                    tree_id,
                    node,
                )
            raise ConversationCommandException(
                "終端ノードでないのに次ノードがありません",
                player_id=command.player_id,
                npc_id_value=command.npc_id_value,
            )
        next_node_id = DialogueNodeId.create(next_node_id_value)
        next_node = self._dialogue_tree_repository.get_node(tree_id, next_node_id)
        if next_node is None:
            raise DialogueNodeNotFoundException(tree_id.value, next_node_id_value)
        session["current_node_id"] = next_node_id
        if next_node.is_terminal:
            return self._end_conversation(
                command.player_id,
                command.npc_id_value,
                tree_id,
                next_node,
            )
        session_dto = ConversationSessionDto(
            player_id=command.player_id,
            npc_id_value=command.npc_id_value,
            dialogue_tree_id_value=tree_id.value,
            current_node=_node_to_dto(next_node),
        )
        return AdvanceConversationResultDto(
            success=True,
            message="",
            session=session_dto,
            conversation_ended=False,
        )

    def _end_conversation(
        self,
        player_id_value: int,
        npc_id_value: int,
        tree_id: DialogueTreeId,
        node: DialogueNode,
    ) -> AdvanceConversationResultDto:
        """終端ノードに到達したときの報酬付与・イベント発行・セッション削除"""
        key = (player_id_value, npc_id_value)
        self._sessions.pop(key, None)
        rewards_gold = node.reward_gold
        rewards_items = node.reward_items
        quest_unlocked = node.quest_unlock_ids
        quest_completed = node.quest_complete_quest_ids
        player_id = PlayerId.create(player_id_value)
        if rewards_gold > 0 and self._player_status_repository:
            status = self._player_status_repository.find_by_id(player_id)
            if status:
                status.earn_gold(rewards_gold)
                self._player_status_repository.save(status)
        if rewards_items and self._player_inventory_repository and self._item_spec_repository and self._item_repository:
            inv = self._player_inventory_repository.find_by_id(player_id)
            if inv:
                for item_spec_id_val, qty in rewards_items:
                    item_spec = self._item_spec_repository.find_by_id(
                        ItemSpecId(item_spec_id_val)
                    )
                    if item_spec and self._item_repository:
                        for _ in range(qty):
                            instance_id = self._item_repository.generate_item_instance_id()
                            from ai_rpg_world.domain.item.aggregate.item_aggregate import (
                                ItemAggregate,
                            )
                            item_agg = ItemAggregate.create(
                                item_instance_id=instance_id,
                                item_spec=item_spec,
                                quantity=1,
                            )
                            self._item_repository.save(item_agg)
                            inv.acquire_item(instance_id)
                        self._player_inventory_repository.save(inv)
        self._event_publisher.publish(
            ConversationEndedEvent.create(
                aggregate_id=player_id,
                aggregate_type="Conversation",
                npc_id_value=npc_id_value,
                end_node_id_value=node.node_id,
                outcome=None,
                rewards_claimed_gold=rewards_gold,
                rewards_claimed_items=rewards_items,
                quest_unlocked_ids=quest_unlocked,
                quest_completed_quest_ids=quest_completed,
            )
        )
        return AdvanceConversationResultDto(
            success=True,
            message="会話を終了しました",
            session=None,
            conversation_ended=True,
            rewards_claimed_gold=rewards_gold,
            rewards_claimed_items=rewards_items,
            quest_unlocked_ids=tuple(quest_unlocked),
            quest_completed_quest_ids=tuple(quest_completed),
        )

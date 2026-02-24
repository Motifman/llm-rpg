"""ダイアログツリー（読み取り専用）のリポジトリインターフェース"""
from abc import ABC, abstractmethod
from typing import Optional

from ai_rpg_world.domain.conversation.value_object.dialogue_tree_id import DialogueTreeId
from ai_rpg_world.domain.conversation.value_object.dialogue_node_id import DialogueNodeId
from ai_rpg_world.domain.conversation.value_object.dialogue_node import DialogueNode


class DialogueTreeRepository(ABC):
    """ダイアログツリーのノードを取得するリポジトリ（読み取り専用）"""

    @abstractmethod
    def get_entry_node_id(self, tree_id: DialogueTreeId) -> Optional[DialogueNodeId]:
        """ツリーの開始ノードIDを返す。存在しなければ None。"""
        pass

    @abstractmethod
    def get_node(
        self, tree_id: DialogueTreeId, node_id: DialogueNodeId
    ) -> Optional[DialogueNode]:
        """指定ツリー・ノードの DialogueNode を返す。存在しなければ None。"""
        pass

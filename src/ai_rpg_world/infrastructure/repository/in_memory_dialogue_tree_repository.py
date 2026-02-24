"""ダイアログツリーのインメモリリポジトリ（読み取り専用）"""
from typing import Optional, Dict, Any

from ai_rpg_world.domain.conversation.repository.dialogue_tree_repository import (
    DialogueTreeRepository,
)
from ai_rpg_world.domain.conversation.value_object.dialogue_tree_id import DialogueTreeId
from ai_rpg_world.domain.conversation.value_object.dialogue_node_id import DialogueNodeId
from ai_rpg_world.domain.conversation.value_object.dialogue_node import DialogueNode


class InMemoryDialogueTreeRepository(DialogueTreeRepository):
    """ダイアログツリーのインメモリ実装。ツリー・ノードを登録して利用する。"""

    def __init__(self) -> None:
        # tree_id_value -> {"entry_node_id": int, "nodes": {node_id: DialogueNode}}
        self._trees: Dict[int, Dict[str, Any]] = {}

    def register_tree(
        self,
        tree_id: int,
        entry_node_id: int,
        nodes: Dict[int, DialogueNode],
    ) -> None:
        """ツリーを登録する（テスト・初期化用）"""
        self._trees[tree_id] = {
            "entry_node_id": entry_node_id,
            "nodes": dict(nodes),
        }

    def get_entry_node_id(self, tree_id: DialogueTreeId) -> Optional[DialogueNodeId]:
        data = self._trees.get(tree_id.value)
        if not data:
            return None
        entry = data["entry_node_id"]
        return DialogueNodeId(entry)

    def get_node(
        self, tree_id: DialogueTreeId, node_id: DialogueNodeId
    ) -> Optional[DialogueNode]:
        data = self._trees.get(tree_id.value)
        if not data:
            return None
        return data["nodes"].get(node_id.value)

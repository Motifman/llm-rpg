"""会話コマンド・クエリ"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StartConversationCommand:
    """会話開始コマンド（NPC に話しかけたとき）"""
    player_id: int
    npc_id_value: int  # NPC の WorldObjectId.value
    dialogue_tree_id: int


@dataclass(frozen=True)
class AdvanceConversationCommand:
    """会話進行コマンド（「次へ」または選択肢クリック）"""
    player_id: int
    npc_id_value: int
    choice_index: Optional[int] = None  # None のときは「次へ」（next_node_id へ）


@dataclass(frozen=True)
class GetCurrentNodeQuery:
    """現在の会話ノード取得クエリ"""
    player_id: int
    npc_id_value: int

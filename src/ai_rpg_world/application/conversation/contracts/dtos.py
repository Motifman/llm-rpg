"""会話 DTO"""
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass(frozen=True)
class ConversationNodeDto:
    """会話ノード表示用 DTO"""
    node_id_value: int
    text: str
    choices: Tuple[Tuple[str, int], ...]  # (表示ラベル, 次ノードID)
    is_terminal: bool
    has_next: bool  # 「次へ」で進めるか（choices が空で next_node_id があるとき True）


@dataclass(frozen=True)
class ConversationSessionDto:
    """会話セッション情報（現在ノード含む）"""
    player_id: int
    npc_id_value: int
    dialogue_tree_id_value: int
    current_node: ConversationNodeDto


@dataclass(frozen=True)
class StartConversationResultDto:
    """会話開始結果"""
    success: bool
    message: str
    session: Optional[ConversationSessionDto] = None


@dataclass(frozen=True)
class AdvanceConversationResultDto:
    """会話進行結果"""
    success: bool
    message: str
    session: Optional[ConversationSessionDto] = None  # 終了時は None
    conversation_ended: bool = False
    rewards_claimed_gold: int = 0
    rewards_claimed_items: Tuple[Tuple[int, int], ...] = ()
    quest_unlocked_ids: Tuple[int, ...] = ()
    quest_completed_quest_ids: Tuple[int, ...] = ()

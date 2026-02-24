"""会話ノードの値オブジェクト（読み取り専用。ルールベース会話の1ノード分）"""
from dataclasses import dataclass
from typing import Tuple, List


@dataclass(frozen=True)
class DialogueNode:
    """ダイアログツリーの1ノード。テキスト・選択肢・終端時の報酬・クエスト解放・完了を持つ。"""

    node_id: int  # DialogueNodeId.value と一致
    text: str
    choices: Tuple[Tuple[str, int], ...]  # (表示ラベル, 次ノードID) のリスト。空なら「次へ」で次ノードへ
    next_node_id: int | None  # choices が空のときのデフォルト次ノード。None かつ is_terminal で終了
    is_terminal: bool
    reward_gold: int = 0
    reward_items: Tuple[Tuple[int, int], ...] = ()  # (item_spec_id, quantity)
    quest_unlock_ids: Tuple[int, ...] = ()  # このノードで解放するクエストID
    quest_complete_quest_ids: Tuple[int, ...] = ()  # このノードで完了扱いにするクエストID

    def __post_init__(self):
        if self.reward_gold < 0:
            raise ValueError("reward_gold must be non-negative")
        if self.node_id < 0:
            raise ValueError("node_id must be non-negative")

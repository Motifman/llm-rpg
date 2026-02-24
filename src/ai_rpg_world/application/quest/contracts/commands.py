from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass(frozen=True)
class IssueQuestCommand:
    """クエスト発行コマンド（Phase 1 ではシステム発行のみ）"""
    objectives: List[Tuple[str, int, int]]  # (objective_type, target_id, required_count)
    reward_gold: int = 0
    reward_exp: int = 0
    reward_items: Optional[List[Tuple[int, int]]] = None  # [(item_spec_id, quantity)]


@dataclass(frozen=True)
class AcceptQuestCommand:
    """クエスト受託コマンド"""
    quest_id: int
    player_id: int


@dataclass(frozen=True)
class CancelQuestCommand:
    """クエストキャンセルコマンド"""
    quest_id: int
    player_id: int

from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass(frozen=True)
class IssueQuestCommand:
    """クエスト発行コマンド。issuer_player_id が None のときはシステム発行。"""
    objectives: List[Tuple[str, int, int]]  # (objective_type, target_id, required_count)
    reward_gold: int = 0
    reward_exp: int = 0
    reward_items: Optional[List[Tuple[int, int]]] = None  # [(item_spec_id, quantity)]
    issuer_player_id: Optional[int] = None  # プレイヤー発行時は指定。システム発行時は None。


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

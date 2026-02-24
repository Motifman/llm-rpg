from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass(frozen=True)
class IssueQuestCommand:
    """クエスト発行コマンド。issuer_player_id が None のときはシステム発行。guild_id を指定するとギルド掲示（承認待ち）になる。"""
    objectives: List[Tuple[str, int, int]]  # (objective_type, target_id, required_count)
    reward_gold: int = 0
    reward_exp: int = 0
    reward_items: Optional[List[Tuple[int, int]]] = None  # [(item_spec_id, quantity)]
    issuer_player_id: Optional[int] = None  # プレイヤー発行時は指定。システム発行時は None。
    guild_id: Optional[int] = None  # ギルド掲示時は指定。非メンバーがギルドに依頼する形で発行可能。


@dataclass(frozen=True)
class AcceptQuestCommand:
    """クエスト受託コマンド"""
    quest_id: int
    player_id: int


@dataclass(frozen=True)
class ApproveQuestCommand:
    """クエスト承認コマンド（ギルド掲示クエストを OPEN にする。オフィサー以上のみ）"""
    quest_id: int
    approver_player_id: int


@dataclass(frozen=True)
class CancelQuestCommand:
    """クエストキャンセルコマンド"""
    quest_id: int
    player_id: int

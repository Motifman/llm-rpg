"""会話開始・終了のドメインイベント（Phase 6: 会話・NPC）"""
from dataclasses import dataclass
from typing import Optional, Tuple

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@dataclass(frozen=True)
class ConversationStartedEvent(BaseDomainEvent[PlayerId, str]):
    """会話開始イベント（aggregate_id = 話し手の PlayerId）"""

    npc_id_value: int  # NPC の WorldObjectId.value
    dialogue_tree_id_value: int
    entry_node_id_value: int


@dataclass(frozen=True)
class ConversationEndedEvent(BaseDomainEvent[PlayerId, str]):
    """会話終了イベント（aggregate_id = 話し手の PlayerId）。
    TALK_TO_NPC 進捗・クエスト解放・報酬付与はこのイベントのハンドラで処理する。
    """

    npc_id_value: int  # NPC の WorldObjectId.value
    end_node_id_value: int
    outcome: Optional[str] = None
    rewards_claimed_gold: int = 0
    rewards_claimed_items: Tuple[Tuple[int, int], ...] = ()  # (item_spec_id, quantity)
    quest_unlocked_ids: Tuple[int, ...] = ()
    quest_completed_quest_ids: Tuple[int, ...] = ()

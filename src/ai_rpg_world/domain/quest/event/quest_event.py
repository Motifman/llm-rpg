from dataclasses import dataclass
from typing import Optional, List

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.quest.value_object.quest_id import QuestId
from ai_rpg_world.domain.quest.value_object.quest_scope import QuestScope
from ai_rpg_world.domain.quest.value_object.quest_reward import QuestReward
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@dataclass(frozen=True)
class QuestIssuedEvent(BaseDomainEvent[QuestId, "QuestAggregate"]):
    """クエスト発行イベント"""
    issuer_player_id: Optional[PlayerId]
    scope: QuestScope
    reward: QuestReward


@dataclass(frozen=True)
class QuestAcceptedEvent(BaseDomainEvent[QuestId, "QuestAggregate"]):
    """クエスト受託イベント"""
    acceptor_player_id: PlayerId


@dataclass(frozen=True)
class QuestCompletedEvent(BaseDomainEvent[QuestId, "QuestAggregate"]):
    """クエスト完了イベント"""
    acceptor_player_id: PlayerId
    reward: QuestReward


@dataclass(frozen=True)
class QuestCancelledEvent(BaseDomainEvent[QuestId, "QuestAggregate"]):
    """クエストキャンセルイベント"""

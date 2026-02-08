from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.enum.player_enum import Role, Race, Element


@dataclass(frozen=True)
class PlayerProfileChangedEvent(BaseDomainEvent[PlayerId, "PlayerProfileAggregate"]):
    """プレイヤープロフィール変更イベント"""
    old_name: Optional[PlayerName]
    new_name: Optional[PlayerName]
    old_role: Optional[Role]
    new_role: Optional[Role]
    old_race: Optional[Race]
    new_race: Optional[Race]
    old_element: Optional[Element]
    new_element: Optional[Element]

from dataclasses import dataclass

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.player.enum.player_enum import Element, Race, Role
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName


@dataclass(frozen=True)
class PlayerProfileChangedEvent(BaseDomainEvent[PlayerId, "PlayerProfileAggregate"]):
    """プレイヤープロフィール変更イベント"""
    old_name: PlayerName | None
    new_name: PlayerName | None
    old_role: Role | None
    new_role: Role | None
    old_race: Race | None
    new_race: Race | None
    old_element: Element | None
    new_element: Element | None

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List
from src.domain.player.level import Level
from src.domain.player.gold import Gold
from src.domain.player.player_enum import Role
from src.domain.spot.spot_exception import PlayerNotMeetConditionException

if TYPE_CHECKING:
    from src.domain.player.player import Player


class ConditionChecker(ABC):
    @abstractmethod
    def check(self, player: 'Player'):
        pass


class LevelConditionChecker(ConditionChecker):
    def __init__(self, value: int):
        self.level = Level(value)

    def check(self, player: 'Player'):
        if not player.level_is_above(self.level):
            raise PlayerNotMeetConditionException(f"Player {player.player_id} does not meet the level condition: {self.level}")


class ItemConditionChecker(ConditionChecker):
    def __init__(self, item_id: int, quantity: int):
        self.item_id = item_id
        self.quantity = quantity
    
    def check(self, player: 'Player'):
        if not player.has_item(self.item_id, self.quantity):
            raise PlayerNotMeetConditionException(f"Player {player.player_id} does not meet the item condition: {self.item_id} {self.quantity}")


class GoldConditionChecker(ConditionChecker):
    def __init__(self, value: int):
        self.gold = Gold(value)

    def check(self, player: 'Player'):
        if not player.can_pay_gold(self.gold):
            raise PlayerNotMeetConditionException(f"Player {player.player_id} does not meet the gold condition: {self.gold}")


class RoleConditionChecker(ConditionChecker):
    def __init__(self, role: Role):
        self.role = role

    def check(self, player: 'Player'):
        if not player.is_role(self.role):
            raise PlayerNotMeetConditionException(f"Player {player.player_id} does not meet the role condition: {self.role}")


class CompositeConditionChecker(ConditionChecker):
    def __init__(self, conditions: List[ConditionChecker]):
        self.conditions = conditions

    def check(self, player: 'Player'):
        for condition in self.conditions:
            condition.check(player)
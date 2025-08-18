import pytest
from src.domain.player.player import Player
from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.player_enum import Role
from src.domain.conversation.message_box import MessageBox


def make_player():
    base = BaseStatus(attack=10, defense=5, speed=7, critical_rate=0.1, evasion_rate=0.05)
    dyn = DynamicStatus(hp=20, max_hp=20, mp=10, max_mp=10, exp=0, level=1, gold=0)
    inventory = Inventory()
    equipment_set = EquipmentSet()
    message_box = MessageBox()
    return Player(player_id=1, name="Hero", role=Role.ADVENTURER, current_spot_id=100, base_status=base, dynamic_status=dyn, inventory=inventory, equipment_set=equipment_set, message_box=message_box)


@pytest.mark.unit
class TestPlayerStatusBasics:
    def test_derived_attack_defense_speed_from_equipment(self):
        player = make_player()
        assert player.attack == 10
        assert player.defense == 5
        assert player.speed == 7

    def test_take_damage_and_heal(self):
        player = make_player()
        # incoming 3 damage
        player.take_damage(3)
        assert player.is_alive() is True
        assert player._dynamic_status.hp == 17
        # incoming 8 damage
        player.take_damage(8)
        assert player._dynamic_status.hp == 9

    def test_heal_and_bounds(self):
        player = make_player()
        player.take_damage(15)
        assert player._dynamic_status.hp == 5
        player.heal(5)
        assert player._dynamic_status.hp == 10
        player.heal(100)
        assert player._dynamic_status.hp == 20

    def test_gold_and_exp_gate(self):
        player = make_player()
        player.receive_gold(10)
        assert player._dynamic_status.gold == 10
        player.pay_gold(3)
        assert player._dynamic_status.gold == 7
        with pytest.raises(AssertionError):
            player.pay_gold(100)

        player.receive_exp(5)
        assert player._dynamic_status.exp == 5
        player.pay_exp(2)
        assert player._dynamic_status.exp == 3
        with pytest.raises(AssertionError):
            player.pay_exp(100)



import pytest

from domain.player.base_status import BaseStatus
from domain.player.dynamic_status import DynamicStatus
from domain.player.inventory import Inventory
from domain.player.player_enum import Role, StatusEffectType
from domain.player.player import Player


def make_player(
    base: BaseStatus | None = None,
    dyn: DynamicStatus | None = None,
):
    base = base or BaseStatus(attack=10, defense=5, speed=7, critical_rate=0.1, evasion_rate=0.05)
    dyn = dyn or DynamicStatus(hp=20, mp=10, max_hp=20, max_mp=10, exp=0, level=1, gold=0)
    inventory = Inventory()
    return Player(player_id=1, name="Hero", role=Role.ADVENTURER, current_spot_id=100, base_status=base, dynamic_status=dyn, inventory=inventory)


@pytest.mark.unit
class TestPlayerStatusBasics:
    def test_derived_attack_defense_speed_from_effects(self):
        player = make_player()
        assert player.attack == 10
        assert player.defense == 5
        assert player.speed == 7

        player.add_status_effect(StatusEffectType.ATTACK_UP, duration=3, value=4)
        player.add_status_effect(StatusEffectType.DEFENSE_UP, duration=3, value=2)
        player.add_status_effect(StatusEffectType.SPEED_UP, duration=3, value=3)

        assert player.attack == 14
        assert player.defense == 7
        assert player.speed == 10

    def test_take_damage_applies_defense_and_floor_zero(self):
        player = make_player()
        # incoming 3, defense=5 -> effective 0
        player.take_damage(3)
        assert player.is_alive() is True
        assert player._dynamic_status.hp == 20
        # incoming 8, defense=5 -> 3 damage
        player.take_damage(8)
        assert player._dynamic_status.hp == 17

    def test_heal_and_bounds(self):
        player = make_player()
        # defense=5 が適用されるため、15ダメージで実効10
        player.take_damage(15)
        assert player._dynamic_status.hp == 10
        player.heal(5)
        assert player._dynamic_status.hp == 15
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


@pytest.mark.unit
class TestPlayerStatusEffectsFlow:
    def test_turn_start_messages_and_confusion_self_damage(self):
        player = make_player()
        # paralysis message only
        player.add_status_effect(StatusEffectType.PARALYSIS, duration=2, value=0)
        msgs = player.process_status_effects_on_turn_start()
        assert any(m.status_effect_type == StatusEffectType.PARALYSIS for m in msgs)
        # add sleep too
        player.add_status_effect(StatusEffectType.SLEEP, duration=2, value=0)
        msgs = player.process_status_effects_on_turn_start()
        assert any(m.status_effect_type == StatusEffectType.SLEEP for m in msgs)

        # confusion causes self-damage: damage = max(1, attack//2)
        hp_before = player._dynamic_status.hp
        player.add_status_effect(StatusEffectType.CONFUSION, duration=1, value=0)
        msgs = player.process_status_effects_on_turn_start()
        assert any(m.status_effect_type == StatusEffectType.CONFUSION for m in msgs)
        assert player._dynamic_status.hp < hp_before

    def test_turn_end_damage_heal_and_duration_progress(self):
        player = make_player()
        player.add_status_effect(StatusEffectType.POISON, duration=2, value=3)
        player.add_status_effect(StatusEffectType.BURN, duration=2, value=4)
        player.add_status_effect(StatusEffectType.BLESSING, duration=2, value=5)

        hp_before = player._dynamic_status.hp
        msgs = player.process_status_effects_on_turn_end()
        assert any(m.status_effect_type == StatusEffectType.POISON for m in msgs)
        assert any(m.status_effect_type == StatusEffectType.BURN for m in msgs)
        assert any(m.status_effect_type == StatusEffectType.BLESSING for m in msgs)
        assert player._dynamic_status.hp != hp_before

        # duration progress removes after 2 ticks
        player.progress_status_effects_on_turn_end()
        assert player.has_status_effect(StatusEffectType.POISON) is True
        assert player.has_status_effect(StatusEffectType.BLESSING) is True

        # second tick -> removal
        msgs = player.process_status_effects_on_turn_end()
        player.progress_status_effects_on_turn_end()
        assert player.has_status_effect(StatusEffectType.POISON) is False
        assert player.has_status_effect(StatusEffectType.BURN) is False
        assert player.has_status_effect(StatusEffectType.BLESSING) is False

    def test_action_permissions_with_effects(self):
        player = make_player()
        assert player.can_act() is True
        assert player.can_magic() is True

        player.defend()
        assert player.can_act() is False
        assert player.can_magic() is False
        player.un_defend()

        player.add_status_effect(StatusEffectType.PARALYSIS, duration=1, value=0)
        assert player.can_act() is False

        player.add_status_effect(StatusEffectType.SLEEP, duration=1, value=0)
        assert player.can_act() is False

        player.add_status_effect(StatusEffectType.SILENCE, duration=1, value=0)
        assert player.can_magic() is False



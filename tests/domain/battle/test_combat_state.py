import pytest
from unittest.mock import Mock
from src.domain.battle.combat_state import CombatState, StatusEffectState, BuffState
from src.domain.battle.battle_enum import (
    Element, Race, ParticipantType, StatusEffectType, BuffType
)
from src.domain.player.hp import Hp
from src.domain.player.mp import Mp
from src.domain.player.base_status import BaseStatus


class TestStatusEffectState:
    """StatusEffectStateのテスト"""

    def test_creation_valid_duration(self):
        """有効なdurationで作成できる"""
        effect = StatusEffectState(StatusEffectType.POISON, 3)
        assert effect.effect_type == StatusEffectType.POISON
        assert effect.duration == 3

    def test_creation_invalid_duration_negative(self):
        """負のdurationで作成するとエラー"""
        with pytest.raises(ValueError, match="duration must be non-negative"):
            StatusEffectState(StatusEffectType.POISON, -1)

    def test_with_turn_progression_decreases_duration(self):
        """ターン進行でdurationが減少する"""
        effect = StatusEffectState(StatusEffectType.POISON, 3)
        new_effect = effect.with_turn_progression()
        assert new_effect.duration == 2

    def test_is_expired_when_duration_zero(self):
        """durationが0のときexpired"""
        effect = StatusEffectState(StatusEffectType.POISON, 0)
        assert effect.is_expired()

    def test_is_expired_when_duration_positive(self):
        """durationが正のときexpiredではない"""
        effect = StatusEffectState(StatusEffectType.POISON, 1)
        assert not effect.is_expired()


class TestBuffState:
    """BuffStateのテスト"""

    def test_creation_valid_multiplier(self):
        """有効なmultiplierで作成できる"""
        buff = BuffState(BuffType.ATTACK, 1.5, 2)
        assert buff.buff_type == BuffType.ATTACK
        assert buff.multiplier == 1.5
        assert buff.duration == 2

    def test_creation_invalid_multiplier_negative(self):
        """負のmultiplierで作成するとエラー"""
        with pytest.raises(ValueError, match="multiplier must be positive"):
            BuffState(BuffType.ATTACK, -1.0, 2)

    def test_creation_invalid_multiplier_zero(self):
        """0のmultiplierで作成するとエラー"""
        with pytest.raises(ValueError, match="multiplier must be positive"):
            BuffState(BuffType.ATTACK, 0.0, 2)

    def test_creation_invalid_duration_negative(self):
        """負のdurationで作成するとエラー"""
        with pytest.raises(ValueError, match="duration must be non-negative"):
            BuffState(BuffType.ATTACK, 1.5, -1)

    def test_with_turn_progression_decreases_duration(self):
        """ターン進行でdurationが減少する"""
        buff = BuffState(BuffType.ATTACK, 1.5, 2)
        new_buff = buff.with_turn_progression()
        assert new_buff.duration == 1

    def test_is_expired_when_duration_zero(self):
        """durationが0のときexpired"""
        buff = BuffState(BuffType.ATTACK, 1.5, 0)
        assert buff.is_expired()

    def test_is_expired_when_duration_positive(self):
        """durationが正のときexpiredではない"""
        buff = BuffState(BuffType.ATTACK, 1.5, 1)
        assert not buff.is_expired()


class TestCombatState:
    """CombatStateのテスト"""

    @pytest.fixture
    def base_status(self):
        """テスト用のBaseStatus"""
        return BaseStatus(
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

    def test_from_player_creates_combat_state(self, base_status):
        """PlayerからCombatStateを作成"""
        # Playerのモックを作成
        player = Mock()
        player.name = "TestPlayer"
        player.race = Race.HUMAN
        player.element = Element.FIRE
        player.hp = Hp(100, 100)
        player.mp = Mp(50, 50)
        player.calculate_status_including_equipment.return_value = base_status

        combat_state = CombatState.from_player(player, 1)

        assert combat_state.entity_id == 1
        assert combat_state.participant_type == ParticipantType.PLAYER
        assert combat_state.name == "TestPlayer"
        assert combat_state.race == Race.HUMAN
        assert combat_state.element == Element.FIRE
        assert combat_state.current_hp == Hp(100, 100)
        assert combat_state.current_mp == Mp(50, 50)
        assert combat_state.status_effects == {}
        assert combat_state.buffs == {}
        assert combat_state.is_defending == False
        assert combat_state.can_act == True
        assert combat_state.attack == 50
        assert combat_state.defense == 30
        assert combat_state.speed == 20
        assert combat_state.critical_rate == 0.1
        assert combat_state.evasion_rate == 0.05

    def test_from_monster_creates_combat_state(self, base_status):
        """MonsterからCombatStateを作成"""
        # Monsterのモックを作成
        monster = Mock()
        monster.name = "TestMonster"
        monster.race = Race.DRAGON
        monster.element = Element.FIRE
        monster.max_hp = 200
        monster.max_mp = 30
        monster.calculate_status_including_equipment.return_value = base_status

        combat_state = CombatState.from_monster(monster, 2)

        assert combat_state.entity_id == 2
        assert combat_state.participant_type == ParticipantType.MONSTER
        assert combat_state.name == "TestMonster"
        assert combat_state.race == Race.DRAGON
        assert combat_state.element == Element.FIRE
        assert combat_state.current_hp == Hp(200, 200)
        assert combat_state.current_mp == Mp(30, 30)
        assert combat_state.status_effects == {}
        assert combat_state.buffs == {}
        assert combat_state.is_defending == False
        assert combat_state.can_act == True
        assert combat_state.attack == 50
        assert combat_state.defense == 30
        assert combat_state.speed == 20
        assert combat_state.critical_rate == 0.1
        assert combat_state.evasion_rate == 0.05

    def test_with_hp_damaged(self):
        """HPダメージ処理"""
        original = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        damaged = original.with_hp_damaged(30)
        assert damaged.current_hp.value == 70
        assert damaged.current_hp != original.current_hp  # 新しいインスタンス

    def test_with_hp_healed(self):
        """HP回復処理"""
        original = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(50, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        healed = original.with_hp_healed(20)
        assert healed.current_hp.value == 70

    def test_with_mp_consumed(self):
        """MP消費処理"""
        original = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        consumed = original.with_mp_consumed(15)
        assert consumed.current_mp.value == 35

    def test_with_mp_healed(self):
        """MP回復処理"""
        original = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(30, 50),
            status_effects={},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        healed = original.with_mp_healed(10)
        assert healed.current_mp.value == 40

    def test_with_status_effect(self):
        """状態異常追加"""
        original = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        with_effect = original.with_status_effect(StatusEffectType.POISON, 3)
        assert StatusEffectType.POISON in with_effect.status_effects
        assert with_effect.status_effects[StatusEffectType.POISON].duration == 3

    def test_without_status_effect(self):
        """状態異常削除"""
        original = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={StatusEffectType.POISON: StatusEffectState(StatusEffectType.POISON, 3)},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        without_effect = original.without_status_effect(StatusEffectType.POISON)
        assert StatusEffectType.POISON not in without_effect.status_effects

    def test_with_buff(self):
        """バフ追加"""
        original = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        with_buff = original.with_buff(BuffType.ATTACK, 1.5, 2)
        assert BuffType.ATTACK in with_buff.buffs
        assert with_buff.buffs[BuffType.ATTACK].multiplier == 1.5
        assert with_buff.buffs[BuffType.ATTACK].duration == 2

    def test_without_buff(self):
        """バフ削除"""
        original = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={BuffType.ATTACK: BuffState(BuffType.ATTACK, 1.5, 2)},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        without_buff = original.without_buff(BuffType.ATTACK)
        assert BuffType.ATTACK not in without_buff.buffs

    def test_with_turn_progression_expires_effects_and_buffs(self):
        """ターン進行で期限切れの効果が削除される"""
        original = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={
                StatusEffectType.POISON: StatusEffectState(StatusEffectType.POISON, 1),  # 期限切れ
                StatusEffectType.BURN: StatusEffectState(StatusEffectType.BURN, 2),     # 継続
            },
            buffs={
                BuffType.ATTACK: BuffState(BuffType.ATTACK, 1.5, 1),  # 期限切れ
                BuffType.DEFENSE: BuffState(BuffType.DEFENSE, 1.2, 3), # 継続
            },
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        progressed = original.with_turn_progression()

        # POISONは削除され、BURNは継続（duration=1）
        assert StatusEffectType.POISON not in progressed.status_effects
        assert StatusEffectType.BURN in progressed.status_effects
        assert progressed.status_effects[StatusEffectType.BURN].duration == 1

        # ATTACKバフは削除され、DEFENSEバフは継続（duration=2）
        assert BuffType.ATTACK not in progressed.buffs
        assert BuffType.DEFENSE in progressed.buffs
        assert progressed.buffs[BuffType.DEFENSE].duration == 2

    def test_with_defend_and_without_defend(self):
        """防御状態の変更"""
        original = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        defending = original.with_defend()
        assert defending.is_defending == True

        not_defending = defending.without_defend()
        assert not_defending.is_defending == False

    def test_calculate_current_attack_with_buff(self):
        """攻撃力計算（バフあり）"""
        state = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={BuffType.ATTACK: BuffState(BuffType.ATTACK, 1.5, 2)},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        assert state.calculate_current_attack() == 75  # 50 * 1.5

    def test_calculate_current_attack_without_buff(self):
        """攻撃力計算（バフなし）"""
        state = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        assert state.calculate_current_attack() == 50

    def test_calculate_current_defense_with_buff_and_defending(self):
        """防御力計算（バフあり、防御中）"""
        state = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={BuffType.DEFENSE: BuffState(BuffType.DEFENSE, 1.2, 2)},
            is_defending=True,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        expected_defense = int(30 * 1.2 * 0.5)  # 防御中は0.5倍
        assert state.calculate_current_defense() == expected_defense

    def test_calculate_current_speed_with_buff(self):
        """速度計算（バフあり）"""
        state = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={BuffType.SPEED: BuffState(BuffType.SPEED, 1.3, 2)},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        assert state.calculate_current_speed() == 26  # 20 * 1.3

    def test_has_status_effect(self):
        """状態異常所持判定"""
        state_with_effect = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={StatusEffectType.POISON: StatusEffectState(StatusEffectType.POISON, 3)},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        state_without_effect = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        assert state_with_effect.has_status_effect(StatusEffectType.POISON)
        assert not state_without_effect.has_status_effect(StatusEffectType.POISON)

    def test_get_status_effect_remaining_duration(self):
        """状態異常の残りターン数取得"""
        state_with_effect = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={StatusEffectType.POISON: StatusEffectState(StatusEffectType.POISON, 5)},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        state_without_effect = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(100, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        assert state_with_effect.get_status_effect_remaining_duration(StatusEffectType.POISON) == 5
        assert state_without_effect.get_status_effect_remaining_duration(StatusEffectType.POISON) == 0

    def test_is_alive(self):
        """生存判定"""
        alive_state = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(50, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        dead_state = CombatState(
            entity_id=1,
            participant_type=ParticipantType.PLAYER,
            name="Test",
            race=Race.HUMAN,
            element=Element.FIRE,
            current_hp=Hp(0, 100),
            current_mp=Mp(50, 50),
            status_effects={},
            buffs={},
            is_defending=False,
            can_act=True,
            attack=50,
            defense=30,
            speed=20,
            critical_rate=0.1,
            evasion_rate=0.05
        )

        assert alive_state.is_alive()
        assert not dead_state.is_alive()

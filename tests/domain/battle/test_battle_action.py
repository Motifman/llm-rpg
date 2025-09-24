import pytest
from unittest.mock import Mock, MagicMock
from typing import List

from src.domain.battle.battle_action import (
    BattleAction,
    HealAction,
    AttackAction,
    StatusEffectApplyAction,
    BuffApplyAction,
    DefendAction,
    EscapeAction,
    StatusEffectInfo,
    BuffInfo,
)
from src.domain.battle.battle_enum import (
    StatusEffectType,
    BuffType,
    Element,
    Race,
    ActionType,
    TargetSelectionMethod,
    ParticipantType,
)
from src.domain.battle.battle_result import BattleActionResult, ActorStateChange, TargetStateChange, BattleActionMetadata
from src.domain.battle.combat_state import CombatState
from src.domain.player.hp import Hp
from src.domain.player.mp import Mp


@pytest.fixture
def mock_combat_state():
    """テスト用のCombatStateモック"""
    mock = Mock(spec=CombatState)
    mock.entity_id = 1
    mock.participant_type = ParticipantType.PLAYER
    mock.name = "Test Player"
    return mock


@pytest.fixture
def sample_combat_state():
    """テスト用のCombatStateインスタンス"""
    return CombatState(
        entity_id=1,
        participant_type=ParticipantType.PLAYER,
        name="Test Player",
        race=Race.HUMAN,
        element=Element.NEUTRAL,
        current_hp=Hp(100, 100),
        current_mp=Mp(50, 50),
        status_effects={},
        buffs={},
        is_defending=False,
        can_act=True,
        attack=10,
        defense=10,
        speed=10,
        critical_rate=0.1,
        evasion_rate=0.1,
    )


@pytest.fixture
def mock_battle_service():
    """テスト用のBattleLogicServiceモック"""
    service = Mock()
    service.target_resolver = Mock()
    service.action_validator = Mock()
    service.resource_consumer = Mock()
    return service


class TestBattleAction:
    """BattleAction基底クラスのテスト"""

    def test_abstract_methods(self):
        """抽象メソッドが正しく定義されていることを確認"""
        # BattleActionは抽象クラスなので直接インスタンス化できない
        with pytest.raises(TypeError):
            BattleAction(
                action_id=1,
                name="Test Action",
                description="Test Description",
                action_type=ActionType.PHYSICAL,
                target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            )


class TestHealAction:
    """HealActionクラスのテスト"""

    def test_creation_with_valid_hp_heal(self):
        """有効なHP回復値での作成テスト"""
        action = HealAction(
            action_id=1,
            name="Heal",
            description="HP回復",
            action_type=ActionType.MAGIC,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            heal_hp_amount=50,
            mp_cost=10,
        )
        assert action.action_id == 1
        assert action.name == "Heal"
        assert action.heal_hp_amount == 50
        assert action.mp_cost == 10

    def test_creation_with_valid_mp_heal(self):
        """有効なMP回復値での作成テスト"""
        action = HealAction(
            action_id=2,
            name="Mana Restore",
            description="MP回復",
            action_type=ActionType.MAGIC,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            heal_mp_amount=20,
            mp_cost=5,
        )
        assert action.heal_mp_amount == 20

    def test_creation_with_both_hp_and_mp_heal(self):
        """HPとMP両方の回復での作成テスト"""
        action = HealAction(
            action_id=3,
            name="Full Restore",
            description="HP/MP回復",
            action_type=ActionType.MAGIC,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            heal_hp_amount=30,
            heal_mp_amount=15,
            mp_cost=15,
        )
        assert action.heal_hp_amount == 30
        assert action.heal_mp_amount == 15

    def test_creation_without_heal_amounts_raises_error(self):
        """回復量が指定されていない場合エラーが発生することをテスト"""
        with pytest.raises(ValueError, match="At least one of heal_hp_amount or heal_mp_amount must be specified"):
            HealAction(
                action_id=4,
                name="Invalid Heal",
                description="無効な回復",
                action_type=ActionType.MAGIC,
                target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            )

    def test_creation_with_negative_heal_amount_raises_error(self):
        """負の回復量での作成テスト"""
        with pytest.raises(ValueError, match="heal_hp_amount must be positive value"):
            HealAction(
                action_id=5,
                name="Invalid Heal",
                description="無効な回復",
                action_type=ActionType.MAGIC,
                target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
                heal_hp_amount=-10,
            )

    def test_creation_with_negative_mp_cost_raises_error(self):
        """負のMPコストでの作成テスト"""
        with pytest.raises(ValueError, match="mp_cost must be non-negative"):
            HealAction(
                action_id=6,
                name="Invalid Heal",
                description="無効な回復",
                action_type=ActionType.MAGIC,
                target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
                heal_hp_amount=50,
                mp_cost=-5,
            )

    @pytest.mark.parametrize("heal_hp,heal_mp,expected_hp_change,expected_mp_change", [
        (50, None, 50, 0),
        (None, 20, 0, 20),
        (30, 15, 30, 15),
    ])
    def test_execute_core_success(self, mock_combat_state, mock_battle_service, heal_hp, heal_mp, expected_hp_change, expected_mp_change):
        """回復アクションの実行が成功することをテスト"""
        # セットアップ
        action = HealAction(
            action_id=1,
            name="Heal",
            description="HP回復",
            action_type=ActionType.MAGIC,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            heal_hp_amount=heal_hp,
            heal_mp_amount=heal_mp,
            mp_cost=10,
        )

        targets = [mock_combat_state]
        base_messages = ["回復を開始"]

        # モックの設定
        mock_battle_service.target_resolver.resolve_targets.return_value = targets
        mock_battle_service.action_validator.validate_action.return_value = None
        mock_battle_service.resource_consumer.consume_resource.return_value = Mock(messages=["MPを10消費"])

        # 実行
        result = action.execute(mock_combat_state, None, mock_battle_service, [mock_combat_state])

        # 検証
        assert result.success is True
        assert len(result.target_state_changes) == 1
        target_change = result.target_state_changes[0]
        assert target_change.hp_change == expected_hp_change
        assert target_change.mp_change == expected_mp_change
        assert result.actor_state_change.mp_change == -10


class TestAttackAction:
    """AttackActionクラスのテスト"""

    def test_creation_with_valid_parameters(self):
        """有効なパラメータでの作成テスト"""
        action = AttackAction(
            action_id=1,
            name="Sword Attack",
            description="剣での攻撃",
            action_type=ActionType.PHYSICAL,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            damage_multiplier=1.5,
            element=Element.FIRE,
            mp_cost=5,
            hit_rate=0.9,
        )
        assert action.action_id == 1
        assert action.name == "Sword Attack"
        # サブクラスのフィールドが正しく設定されていることを確認
        assert action.damage_multiplier == 1.5
        assert action.element == Element.FIRE
        assert action.hit_rate == 0.9

    def test_creation_with_invalid_hit_rate_raises_error(self):
        """無効な命中率での作成テスト"""
        with pytest.raises(ValueError, match="hit_rate must be between 0 and 1"):
            action = AttackAction(
                action_id=1,
                name="Invalid Attack",
                description="無効な攻撃",
                action_type=ActionType.PHYSICAL,
                target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
                hit_rate=1.5,
            )

    def test_execute_core_hit_success(self, mock_combat_state, mock_battle_service):
        """攻撃が命中した場合のテスト"""
        # セットアップ
        action = AttackAction(
            action_id=1,
            name="Attack",
            description="攻撃",
            action_type=ActionType.PHYSICAL,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
        )

        targets = [mock_combat_state]
        base_messages = []

        # モックの設定
        mock_hit_result = Mock()
        mock_hit_result.missed = False
        mock_hit_result.evaded_targets = []
        mock_battle_service.target_resolver.resolve_targets.return_value = targets
        mock_battle_service.action_validator.validate_action.return_value = None
        mock_battle_service.resource_consumer.consume_resource.return_value = Mock(messages=[])
        mock_battle_service.hit_resolver.resolve_hits.return_value = mock_hit_result

        # ダメージ計算のモック
        mock_damage_result = Mock()
        mock_damage_result.damage = -30
        mock_damage_result.is_critical = True
        mock_damage_result.compatibility_multiplier = 1.5
        mock_damage_result.race_attack_multiplier = 1.2
        mock_battle_service.damage_calculator.calculate_damage.return_value = mock_damage_result

        # 効果適用のモック
        mock_effect_result = Mock()
        mock_effect_result.status_effects_to_add = []
        mock_effect_result.buffs_to_add = []
        mock_effect_result.messages = []
        mock_battle_service.effect_applier.apply_effects.return_value = mock_effect_result

        # 実行
        result = action.execute(mock_combat_state, None, mock_battle_service, [mock_combat_state])

        # 検証
        assert result.success is True
        assert len(result.target_state_changes) == 1
        target_change = result.target_state_changes[0]
        assert target_change.hp_change == -30
        assert result.metadata.critical_hits == [True]
        assert result.metadata.compatibility_multipliers == [1.5]
        assert result.metadata.race_attack_multipliers == [1.2]

    def test_execute_core_miss(self, mock_combat_state, mock_battle_service):
        """攻撃が外れた場合のテスト"""
        # セットアップ
        action = AttackAction(
            action_id=1,
            name="Attack",
            description="攻撃",
            action_type=ActionType.PHYSICAL,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
        )

        targets = [mock_combat_state]
        base_messages = []

        # モックの設定
        mock_hit_result = Mock()
        mock_hit_result.missed = True
        mock_hit_result.evaded_targets = []
        mock_battle_service.target_resolver.resolve_targets.return_value = targets
        mock_battle_service.action_validator.validate_action.return_value = None
        mock_battle_service.resource_consumer.consume_resource.return_value = Mock(messages=[])
        mock_battle_service.hit_resolver.resolve_hits.return_value = mock_hit_result

        # 実行
        result = action.execute(mock_combat_state, None, mock_battle_service, [mock_combat_state])

        # 検証
        assert result.success is False
        assert result.failure_reason == "missed"
        assert "攻撃が外れた！" in result.messages


class TestStatusEffectApplyAction:
    """StatusEffectApplyActionクラスのテスト"""

    def test_creation_with_valid_parameters(self):
        """有効なパラメータでの作成テスト"""
        action = StatusEffectApplyAction(
            action_id=1,
            name="Poison",
            description="毒を付与",
            action_type=ActionType.MAGIC,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            status_effect_rate={StatusEffectType.POISON: 0.8},
            status_effect_duration={StatusEffectType.POISON: 3},
            mp_cost=5,
        )
        assert hasattr(action, 'status_effect_rate') and action.status_effect_rate[StatusEffectType.POISON] == 0.8
        assert hasattr(action, 'status_effect_duration') and action.status_effect_duration[StatusEffectType.POISON] == 3

    def test_creation_with_invalid_rate_raises_error(self):
        """無効な付与率での作成テスト"""
        with pytest.raises(ValueError, match="status_effect_rate must be between 0 and 1.0"):
            action = StatusEffectApplyAction(
                action_id=1,
                name="Invalid Poison",
                description="無効な毒",
                action_type=ActionType.MAGIC,
                target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
                status_effect_rate={StatusEffectType.POISON: 1.5},
                status_effect_duration={StatusEffectType.POISON: 3},
            )

    def test_execute_core_success(self, mock_combat_state, mock_battle_service):
        """状態異常付与が成功する場合のテスト"""
        # セットアップ
        action = StatusEffectApplyAction(
            action_id=1,
            name="Poison",
            description="毒を付与",
            action_type=ActionType.MAGIC,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            status_effect_rate={StatusEffectType.POISON: 1.0},
            status_effect_duration={StatusEffectType.POISON: 3},
        )

        targets = [mock_combat_state]
        base_messages = []

        # モックの設定
        mock_hit_result = Mock()
        mock_hit_result.missed = False
        mock_hit_result.evaded_targets = []
        mock_battle_service.target_resolver.resolve_targets.return_value = targets
        mock_battle_service.action_validator.validate_action.return_value = None
        mock_battle_service.resource_consumer.consume_resource.return_value = Mock(messages=[])
        mock_battle_service.hit_resolver.resolve_hits.return_value = mock_hit_result

        # 効果適用のモック
        mock_effect_result = Mock()
        mock_effect_result.status_effects_to_add = [(StatusEffectType.POISON, 3)]
        mock_effect_result.messages = ["毒が付与された！"]
        mock_battle_service.effect_applier.apply_effects.return_value = mock_effect_result

        # 実行
        result = action.execute(mock_combat_state, None, mock_battle_service, [mock_combat_state])

        # 検証
        assert result.success is True
        assert len(result.target_state_changes) == 1
        target_change = result.target_state_changes[0]
        assert target_change.status_effects_to_add == [(StatusEffectType.POISON, 3)]
        assert any("状態異常を付与した！" in msg for msg in result.messages)


class TestBuffApplyAction:
    """BuffApplyActionクラスのテスト"""

    def test_creation_with_valid_parameters(self):
        """有効なパラメータでの作成テスト"""
        action = BuffApplyAction(
            action_id=1,
            name="Power Up",
            description="攻撃力を上げる",
            action_type=ActionType.MAGIC,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            buff_rate={BuffType.ATTACK: 0.9},
            buff_duration={BuffType.ATTACK: 3},
            mp_cost=5,
        )
        assert hasattr(action, 'buff_rate') and action.buff_rate[BuffType.ATTACK] == 0.9
        assert hasattr(action, 'buff_duration') and action.buff_duration[BuffType.ATTACK] == 3

    def test_creation_with_invalid_rate_raises_error(self):
        """無効なバフ率での作成テスト"""
        with pytest.raises(ValueError, match="buff_rate must be between 0 and 1.0"):
            action = BuffApplyAction(
                action_id=1,
                name="Invalid Buff",
                description="無効なバフ",
                action_type=ActionType.MAGIC,
                target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
                buff_rate={BuffType.ATTACK: 1.2},
                buff_duration={BuffType.ATTACK: 3},
            )

    def test_execute_core_success(self, mock_combat_state, mock_battle_service):
        """バフ付与が成功する場合のテスト"""
        # セットアップ
        action = BuffApplyAction(
            action_id=1,
            name="Power Up",
            description="攻撃力を上げる",
            action_type=ActionType.MAGIC,
            target_selection_method=TargetSelectionMethod.SINGLE_TARGET,
            buff_rate={BuffType.ATTACK: 1.0},
            buff_duration={BuffType.ATTACK: 3},
        )

        targets = [mock_combat_state]
        base_messages = []

        # モックの設定
        mock_hit_result = Mock()
        mock_hit_result.missed = False
        mock_hit_result.evaded_targets = []
        mock_battle_service.target_resolver.resolve_targets.return_value = targets
        mock_battle_service.action_validator.validate_action.return_value = None
        mock_battle_service.resource_consumer.consume_resource.return_value = Mock(messages=[])
        mock_battle_service.hit_resolver.resolve_hits.return_value = mock_hit_result

        # 効果適用のモック
        mock_effect_result = Mock()
        mock_effect_result.buffs_to_add = [(BuffType.ATTACK, 1.5, 3)]
        mock_effect_result.messages = ["攻撃力が上がった！"]
        mock_battle_service.effect_applier.apply_effects.return_value = mock_effect_result

        # 実行
        result = action.execute(mock_combat_state, None, mock_battle_service, [mock_combat_state])

        # 検証
        assert result.success is True
        assert len(result.target_state_changes) == 1
        target_change = result.target_state_changes[0]
        assert target_change.buffs_to_add == [(BuffType.ATTACK, 1.5, 3)]
        assert any("バフを付与した！" in msg for msg in result.messages)


class TestDefendAction:
    """DefendActionクラスのテスト"""

    def test_creation(self):
        """作成テスト"""
        action = DefendAction(
            action_id=1,
            name="Defend",
            description="防御",
            action_type=ActionType.PHYSICAL,
            target_selection_method=TargetSelectionMethod.SELF,
        )
        assert action.action_id == 1
        assert action.name == "Defend"

    def test_execute_core_success(self, mock_combat_state, mock_battle_service):
        """防御アクションの実行が成功することをテスト"""
        # セットアップ
        action = DefendAction(
            action_id=1,
            name="Defend",
            description="防御",
            action_type=ActionType.PHYSICAL,
            target_selection_method=TargetSelectionMethod.SELF,
        )

        targets = [mock_combat_state]
        base_messages = []

        # モックの設定
        mock_battle_service.target_resolver.resolve_targets.return_value = targets
        mock_battle_service.action_validator.validate_action.return_value = None
        mock_battle_service.resource_consumer.consume_resource.return_value = Mock(messages=[])

        # 実行
        result = action.execute(mock_combat_state, None, mock_battle_service, [mock_combat_state])

        # 検証
        assert result.success is True
        assert result.actor_state_change.is_defend is True
        assert any("防御の構えを取った！" in msg for msg in result.messages)


class TestEscapeAction:
    """EscapeActionクラスのテスト"""

    def test_creation(self):
        """作成テスト"""
        action = EscapeAction(
            action_id=1,
            name="Escape",
            description="逃亡",
            action_type=ActionType.SPECIAL,
            target_selection_method=TargetSelectionMethod.NONE,
        )
        assert action.action_id == 1
        assert action.name == "Escape"

    def test_execute_core_success(self, mock_combat_state, mock_battle_service):
        """逃亡アクションの実行が成功することをテスト"""
        # セットアップ
        action = EscapeAction(
            action_id=1,
            name="Escape",
            description="逃亡",
            action_type=ActionType.SPECIAL,
            target_selection_method=TargetSelectionMethod.NONE,
        )

        targets = []
        base_messages = []

        # モックの設定
        mock_battle_service.target_resolver.resolve_targets.return_value = targets
        mock_battle_service.action_validator.validate_action.return_value = None
        mock_battle_service.resource_consumer.consume_resource.return_value = Mock(messages=[])

        # 実行
        result = action.execute(mock_combat_state, None, mock_battle_service, [mock_combat_state])

        # 検証
        assert result.success is True
        assert any("逃亡した！" in msg for msg in result.messages)


class TestStatusEffectInfo:
    """StatusEffectInfoクラスのテスト"""

    def test_creation_with_valid_parameters(self):
        """有効なパラメータでの作成テスト"""
        info = StatusEffectInfo(
            effect_type=StatusEffectType.POISON,
            apply_rate=0.8,
            duration=3,
        )
        assert info.effect_type == StatusEffectType.POISON
        assert info.apply_rate == 0.8
        assert info.duration == 3

    def test_creation_with_invalid_apply_rate_raises_error(self):
        """無効な付与率での作成テスト"""
        with pytest.raises(ValueError, match="apply_rate must be between 0 and 1"):
            StatusEffectInfo(
                effect_type=StatusEffectType.POISON,
                apply_rate=1.5,
                duration=3,
            )

    def test_creation_with_negative_duration_raises_error(self):
        """負の持続時間での作成テスト"""
        with pytest.raises(ValueError, match="duration must be positive"):
            StatusEffectInfo(
                effect_type=StatusEffectType.POISON,
                apply_rate=0.8,
                duration=-1,
            )


class TestBuffInfo:
    """BuffInfoクラスのテスト"""

    def test_creation_with_valid_parameters(self):
        """有効なパラメータでの作成テスト"""
        info = BuffInfo(
            buff_type=BuffType.ATTACK,
            apply_rate=0.9,
            multiplier=1.5,
            duration=3,
        )
        assert info.buff_type == BuffType.ATTACK
        assert info.apply_rate == 0.9
        assert info.multiplier == 1.5
        assert info.duration == 3

    def test_creation_with_invalid_apply_rate_raises_error(self):
        """無効な付与率での作成テスト"""
        with pytest.raises(ValueError, match="apply_rate must be between 0 and 1"):
            BuffInfo(
                buff_type=BuffType.ATTACK,
                apply_rate=1.2,
                multiplier=1.5,
                duration=3,
            )

    def test_creation_with_invalid_multiplier_raises_error(self):
        """無効な倍率での作成テスト"""
        with pytest.raises(ValueError, match="multiplier must be positive"):
            BuffInfo(
                buff_type=BuffType.ATTACK,
                apply_rate=0.9,
                multiplier=-1.0,
                duration=3,
            )

    def test_creation_with_negative_duration_raises_error(self):
        """負の持続時間での作成テスト"""
        with pytest.raises(ValueError, match="duration must be positive"):
            BuffInfo(
                buff_type=BuffType.ATTACK,
                apply_rate=0.9,
                multiplier=1.5,
                duration=-1,
            )

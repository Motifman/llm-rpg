import pytest
from unittest.mock import Mock
from src.domain.battle.battle_service import (
    TargetResolver, ActionValidator, ResourceConsumer, HitResolver,
    DamageCalculator, EffectApplier, EffectProcessor, BattleLogicService
)
from src.domain.battle.battle_action import BattleAction, StatusEffectInfo, BuffInfo
from src.domain.battle.battle_enum import (
    BuffType, StatusEffectType, ParticipantType, TargetSelectionMethod, Element, ActionType
)
from src.domain.battle.battle_exception import (
    InsufficientMpException, InsufficientHpException, SilencedException, BlindedException
)
from src.domain.battle.combat_state import CombatState
from src.domain.player.hp import Hp as HP
from src.domain.player.mp import Mp as MP


@pytest.fixture
def mock_combat_state():
    """モックのCombatStateを作成"""
    state = Mock(spec=CombatState)
    state.entity_id = 1
    state.participant_type = ParticipantType.PLAYER
    state.name = "Test Player"
    state.current_hp = Mock(spec=HP)
    state.current_mp = Mock(spec=MP)
    state.attack = 50
    state.defense = 20
    state.critical_rate = 0.1
    state.evasion_rate = 0.05
    state.element = Element.FIRE
    state.race = "Human"
    return state


@pytest.fixture
def mock_battle_action():
    """モックのBattleActionを作成"""
    action = Mock(spec=BattleAction)
    action.action_type = ActionType.PHYSICAL
    action.target_selection_method = TargetSelectionMethod.SINGLE_TARGET
    action.mp_cost = 10
    action.hp_cost = 5
    action.damage_multiplier = 1.0
    action.hit_rate = 0.9
    action.element = Element.FIRE
    action.race_attack_multiplier = {}
    action.status_effect_infos = []
    action.buff_infos = []
    return action


class TestTargetResolver:
    """TargetResolverクラスのテスト"""

    @pytest.fixture
    def resolver(self):
        return TargetResolver()

    @pytest.fixture
    def mock_participants(self, mock_combat_state):
        """複数のモック参加者を作成"""
        enemy_state = Mock(spec=CombatState)
        enemy_state.entity_id = 2
        enemy_state.participant_type = ParticipantType.MONSTER
        enemy_state.name = "Test Monster"

        ally_state = Mock(spec=CombatState)
        ally_state.entity_id = 3
        ally_state.participant_type = ParticipantType.PLAYER
        ally_state.name = "Test Ally"

        return [mock_combat_state, enemy_state, ally_state]

    def test_resolve_single_target(self, resolver, mock_combat_state, mock_participants):
        """単一ターゲット解決のテスト"""
        action = Mock()
        action.target_selection_method = TargetSelectionMethod.SINGLE_TARGET

        targets = [mock_participants[1]]  # enemy
        result = resolver.resolve_targets(mock_combat_state, action, targets, mock_participants)

        assert len(result) == 1
        assert result[0] == mock_participants[1]

    def test_resolve_all_enemies(self, resolver, mock_combat_state, mock_participants):
        """全敵解決のテスト"""
        action = Mock()
        action.target_selection_method = TargetSelectionMethod.ALL_ENEMIES

        result = resolver.resolve_targets(mock_combat_state, action, None, mock_participants)

        assert len(result) == 1
        assert result[0].participant_type == ParticipantType.MONSTER

    def test_resolve_all_allies(self, resolver, mock_combat_state, mock_participants):
        """全味方解決のテスト"""
        action = Mock()
        action.target_selection_method = TargetSelectionMethod.ALL_ALLIES

        result = resolver.resolve_targets(mock_combat_state, action, None, mock_participants)

        assert len(result) == 2
        assert all(p.participant_type == ParticipantType.PLAYER for p in result)

    def test_resolve_random_enemy(self, resolver, mock_combat_state, mock_participants):
        """ランダム敵解決のテスト"""
        action = Mock()
        action.target_selection_method = TargetSelectionMethod.RANDOM_ENEMY

        result = resolver.resolve_targets(mock_combat_state, action, None, mock_participants)

        assert len(result) == 1
        assert result[0].participant_type == ParticipantType.MONSTER

    def test_resolve_self(self, resolver, mock_combat_state, mock_participants):
        """自己解決のテスト"""
        action = Mock()
        action.target_selection_method = TargetSelectionMethod.SELF

        result = resolver.resolve_targets(mock_combat_state, action, None, mock_participants)

        assert len(result) == 1
        assert result[0] == mock_combat_state


class TestActionValidator:
    """ActionValidatorクラスのテスト"""

    @pytest.fixture
    def validator(self):
        return ActionValidator()

    def test_validate_magic_action_without_silence(self, validator, mock_combat_state, mock_battle_action):
        """沈黙状態でない魔法アクションのテスト"""
        mock_combat_state.has_status_effect.return_value = False
        mock_combat_state.current_mp.can_consume.return_value = True
        mock_combat_state.current_hp.can_consume.return_value = True
        mock_battle_action.action_type = ActionType.MAGIC

        # 例外が発生しないことを確認
        validator.validate_action(mock_combat_state, mock_battle_action)

    def test_validate_magic_action_with_silence(self, validator, mock_combat_state, mock_battle_action):
        """沈黙状態の魔法アクションのテスト"""
        mock_combat_state.has_status_effect.return_value = True
        mock_battle_action.action_type = ActionType.MAGIC

        with pytest.raises(SilencedException):
            validator.validate_action(mock_combat_state, mock_battle_action)

    def test_validate_physical_action_with_blindness(self, validator, mock_combat_state, mock_battle_action):
        """暗闇状態の物理アクションのテスト"""
        mock_combat_state.has_status_effect.return_value = True
        mock_battle_action.action_type = ActionType.PHYSICAL

        with pytest.raises(BlindedException):
            validator.validate_action(mock_combat_state, mock_battle_action)

    def test_validate_insufficient_mp(self, validator, mock_combat_state, mock_battle_action):
        """MP不足のテスト"""
        mock_combat_state.has_status_effect.return_value = False
        mock_combat_state.current_mp.can_consume.return_value = False

        with pytest.raises(InsufficientMpException):
            validator.validate_action(mock_combat_state, mock_battle_action)

    def test_validate_insufficient_hp(self, validator, mock_combat_state, mock_battle_action):
        """HP不足のテスト"""
        mock_combat_state.has_status_effect.return_value = False
        mock_combat_state.current_mp.can_consume.return_value = True
        mock_combat_state.current_hp.can_consume.return_value = False

        with pytest.raises(InsufficientHpException):
            validator.validate_action(mock_combat_state, mock_battle_action)


class TestResourceConsumer:
    """ResourceConsumerクラスのテスト"""

    @pytest.fixture
    def consumer(self):
        return ResourceConsumer()

    def test_consume_resource_with_mp_and_hp(self, consumer, mock_combat_state, mock_battle_action):
        """MPとHP消費のテスト"""
        result = consumer.consume_resource(mock_combat_state, mock_battle_action)

        assert result.mp_consumed == 10
        assert result.hp_consumed == 5
        assert len(result.messages) == 2
        assert "10MPを消費した" in result.messages[0]
        assert "5HPを消費した" in result.messages[1]

    def test_consume_resource_no_cost(self, consumer, mock_combat_state):
        """消費なしのテスト"""
        action = Mock()
        action.mp_cost = None
        action.hp_cost = None

        result = consumer.consume_resource(mock_combat_state, action)

        assert result.mp_consumed == 0
        assert result.hp_consumed == 0
        assert len(result.messages) == 0


class TestHitResolver:
    """HitResolverクラスのテスト"""

    @pytest.fixture
    def resolver(self):
        return HitResolver()

    def test_resolve_hits_success(self, resolver, mock_combat_state):
        """命中成功のテスト"""
        defenders = [Mock(spec=CombatState)]
        defenders[0].evasion_rate = 0.0
        action = Mock()
        action.hit_rate = 1.0

        result = resolver.resolve_hits(mock_combat_state, defenders, action)

        assert not result.missed
        assert len(result.evaded_targets) == 0

    def test_resolve_hits_miss(self, resolver, mock_combat_state):
        """命中失敗のテスト"""
        defenders = [Mock(spec=CombatState)]
        action = Mock()
        action.hit_rate = 0.0

        result = resolver.resolve_hits(mock_combat_state, defenders, action)

        assert result.missed
        assert len(result.evaded_targets) == 0

    def test_resolve_hits_evasion(self, resolver, mock_combat_state):
        """回避のテスト"""
        defenders = [Mock(spec=CombatState)]
        defenders[0].entity_id = 2
        defenders[0].participant_type = ParticipantType.MONSTER
        defenders[0].evasion_rate = 1.0
        action = Mock()
        action.hit_rate = 1.0

        result = resolver.resolve_hits(mock_combat_state, defenders, action)

        assert not result.missed
        assert len(result.evaded_targets) == 1
        assert result.evaded_targets[0] == (2, ParticipantType.MONSTER)


class TestDamageCalculator:
    """DamageCalculatorクラスのテスト"""

    @pytest.fixture
    def calculator(self):
        return DamageCalculator()

    def test_calculate_damage_normal(self, calculator, mock_combat_state):
        """通常ダメージ計算のテスト"""
        defender = Mock(spec=CombatState)
        defender.element = Element.WATER
        defender.race = "Human"
        defender.calculate_current_defense.return_value = 10

        mock_combat_state.calculate_current_attack.return_value = 50

        action = Mock()
        action.damage_multiplier = 1.0
        action.element = Element.FIRE
        action.race_attack_multiplier = {}

        result = calculator.calculate_damage(mock_combat_state, defender, action)

        assert result.damage >= 0
        assert not result.is_critical
        assert result.compatibility_multiplier == 0.5  # FIRE vs WATER = weak
        assert result.race_attack_multiplier == 1.0

    def test_calculate_damage_with_critical(self, calculator, mock_combat_state):
        """クリティカルダメージのテスト"""
        defender = Mock(spec=CombatState)
        defender.element = Element.WATER
        defender.race = "Human"
        defender.calculate_current_defense.return_value = 10

        mock_combat_state.calculate_current_attack.return_value = 50
        mock_combat_state.critical_rate = 1.0  # 必ずクリティカル

        action = Mock()
        action.damage_multiplier = 1.0
        action.element = Element.FIRE
        action.race_attack_multiplier = {}

        result = calculator.calculate_damage(mock_combat_state, defender, action)

        assert result.is_critical
        assert result.damage >= 0


class TestEffectApplier:
    """EffectApplierクラスのテスト"""

    @pytest.fixture
    def applier(self):
        return EffectApplier()

    def test_apply_effects_with_status_and_buff(self, mock_combat_state):
        """状態異常とバフ適用テスト"""
        applier = EffectApplier()

        status_effect_info = Mock()
        status_effect_info.effect_type = StatusEffectType.POISON
        status_effect_info.apply_rate = 1.0
        status_effect_info.duration = 3

        buff_info = Mock()
        buff_info.buff_type = BuffType.ATTACK
        buff_info.duration = 2
        buff_info.multiplier = 1.5

        action = Mock()
        action.status_effect_infos = [status_effect_info]
        action.buff_infos = [buff_info]

        result = applier.apply_effects(mock_combat_state, action)

        assert len(result.status_effects_to_add) == 1
        assert result.status_effects_to_add[0] == (StatusEffectType.POISON, 3)
        assert len(result.buffs_to_add) == 1
        assert result.buffs_to_add[0] == (BuffType.ATTACK, 1.5, 2)
        assert len(result.messages) == 2

    def test_apply_effects_no_effects(self, mock_combat_state):
        """効果なしのテスト"""
        applier = EffectApplier()

        action = Mock()
        action.status_effect_infos = []
        action.buff_infos = []

        result = applier.apply_effects(mock_combat_state, action)

        assert len(result.status_effects_to_add) == 0
        assert len(result.buffs_to_add) == 0
        assert len(result.messages) == 0


class TestEffectProcessor:
    """EffectProcessorクラスのテスト"""

    @pytest.fixture
    def processor(self):
        return EffectProcessor()

    def test_process_sleep_on_turn_start_awake(self, processor, mock_combat_state):
        """眠りから覚醒のテスト"""
        mock_combat_state.has_status_effect.return_value = True

        result = processor.process_sleep_on_turn_start(mock_combat_state)

        # 確率的なので、結果は変動する可能性がある
        assert result.actor_id == mock_combat_state.entity_id
        assert isinstance(result.can_act, bool)

    def test_process_paralysis_on_turn_start(self, processor, mock_combat_state):
        """麻痺のテスト"""
        mock_combat_state.has_status_effect.return_value = True

        result = processor.process_paralysis_on_turn_start(mock_combat_state)

        assert not result.can_act
        assert "麻痺" in result.messages[0]

    def test_process_poison_on_turn_end(self, processor, mock_combat_state):
        """毒のテスト"""
        mock_combat_state.has_status_effect.return_value = True
        mock_combat_state.current_hp.value = 100

        result = processor.process_poison_on_turn_end(mock_combat_state)

        assert result.damage == 10  # 100 * 0.1
        assert "毒により" in result.messages[0]

    def test_process_blessing_on_turn_end(self, processor, mock_combat_state):
        """加護のテスト"""
        mock_combat_state.has_status_effect.return_value = True

        result = processor.process_blessing_on_turn_end(mock_combat_state)

        assert result.healing == 20
        assert "加護により" in result.messages[0]


class TestBattleLogicService:
    """BattleLogicServiceクラスのテスト"""

    @pytest.fixture
    def service(self):
        return BattleLogicService()

    def test_process_on_turn_start_normal(self, service, mock_combat_state):
        """ターン開始処理のテスト"""
        mock_combat_state.has_status_effect.return_value = False

        result = service.process_on_turn_start(mock_combat_state)

        assert result.actor_id == mock_combat_state.entity_id
        assert result.can_act
        assert isinstance(result.messages, list)
        assert result.damage == 0

    def test_process_on_turn_end_normal(self, service, mock_combat_state):
        """ターン終了処理のテスト"""
        mock_combat_state.has_status_effect.return_value = False

        result = service.process_on_turn_end(mock_combat_state)

        assert result.actor_id == mock_combat_state.entity_id
        assert isinstance(result.messages, list)
        assert result.damage == 0
        assert result.healing == 0

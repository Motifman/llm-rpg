import pytest
from src.domain.battle.battle_result import (
    TurnStartResult,
    TurnEndResult,
    BattleActionResult
)
from src.domain.battle.battle_enum import StatusEffectType, BuffType


class TestTurnStartResult:
    """TurnStartResultのテストクラス"""
    
    def test_create_basic(self):
        """基本的なTurnStartResultの作成テスト"""
        result = TurnStartResult(can_act=True)
        
        assert result.can_act is True
        assert len(result.messages) == 0
        assert result.self_damage == 0
        assert len(result.recovered_status_effects) == 0
    
    def test_create_with_all_fields(self):
        """全てのフィールドを含むTurnStartResultの作成テスト"""
        messages = ["眠りから覚めた！", "麻痺で動けない"]
        recovered_effects = [StatusEffectType.SLEEP]
        
        result = TurnStartResult(
            can_act=False,
            messages=messages,
            self_damage=15,
            recovered_status_effects=recovered_effects
        )
        
        assert result.can_act is False
        assert result.messages == messages
        assert result.self_damage == 15
        assert result.recovered_status_effects == recovered_effects
    
    def test_immutable(self):
        """不変性のテスト"""
        result = TurnStartResult(can_act=True)
        
        # frozen=Trueなので変更できない
        with pytest.raises(Exception):
            result.can_act = False


class TestTurnEndResult:
    """TurnEndResultのテストクラス"""
    
    def test_create_basic(self):
        """基本的なTurnEndResultの作成テスト"""
        result = TurnEndResult()
        
        assert len(result.messages) == 0
        assert result.is_attacker_defeated is False
        assert result.damage_from_status_effects == 0
        assert result.healing_from_status_effects == 0
        assert len(result.expired_status_effects) == 0
        assert len(result.expired_buffs) == 0
    
    def test_create_with_all_fields(self):
        """全てのフィールドを含むTurnEndResultの作成テスト"""
        messages = ["毒でダメージを受けた", "祝福で回復した"]
        expired_status = [StatusEffectType.POISON]
        expired_buffs = [BuffType.ATTACK]
        
        result = TurnEndResult(
            messages=messages,
            is_attacker_defeated=True,
            damage_from_status_effects=25,
            healing_from_status_effects=30,
            expired_status_effects=expired_status,
            expired_buffs=expired_buffs
        )
        
        assert result.messages == messages
        assert result.is_attacker_defeated is True
        assert result.damage_from_status_effects == 25
        assert result.healing_from_status_effects == 30
        assert result.expired_status_effects == expired_status
        assert result.expired_buffs == expired_buffs
    
    def test_immutable(self):
        """不変性のテスト"""
        result = TurnEndResult()
        
        # frozen=Trueなので変更できない
        with pytest.raises(Exception):
            result.is_attacker_defeated = True


class TestBattleActionResult:
    """BattleActionResultのテストクラス"""
    
    def test_create_success_basic(self):
        """基本的な成功時のBattleActionResultの作成テスト"""
        messages = ["攻撃が命中した！"]
        
        result = BattleActionResult.create_success(messages)
        
        assert result.success is True
        assert result.messages == messages
        assert len(result.target_ids) == 0
        assert len(result.damages) == 0
        assert len(result.healing_amounts) == 0
        assert len(result.is_target_defeated) == 0
        assert len(result.applied_status_effects) == 0
        assert len(result.applied_buffs) == 0
        assert result.hp_consumed == 0
        assert result.mp_consumed == 0
        assert len(result.critical_hits) == 0
        assert len(result.compatibility_multipliers) == 0
        assert result.failure_reason is None
    
    def test_create_success_with_all_fields(self):
        """全てのフィールドを含む成功時のBattleActionResultの作成テスト"""
        messages = ["強力な攻撃！", "クリティカル！"]
        target_ids = [1, 2]
        damages = [25, 30]
        healing_amounts = [0, 0]
        is_target_defeated = [False, True]
        applied_status_effects = [(1, StatusEffectType.POISON, 3)]
        applied_buffs = [(2, BuffType.ATTACK, 1.5, 2)]
        critical_hits = [True, False]
        compatibility_multipliers = [1.5, 1.0]
        
        result = BattleActionResult.create_success(
            messages=messages,
            target_ids=target_ids,
            damages=damages,
            healing_amounts=healing_amounts,
            is_target_defeated=is_target_defeated,
            applied_status_effects=applied_status_effects,
            applied_buffs=applied_buffs,
            hp_consumed=10,
            mp_consumed=20,
            critical_hits=critical_hits,
            compatibility_multipliers=compatibility_multipliers
        )
        
        assert result.success is True
        assert result.messages == messages
        assert result.target_ids == target_ids
        assert result.damages == damages
        assert result.healing_amounts == healing_amounts
        assert result.is_target_defeated == is_target_defeated
        assert result.applied_status_effects == applied_status_effects
        assert result.applied_buffs == applied_buffs
        assert result.hp_consumed == 10
        assert result.mp_consumed == 20
        assert result.critical_hits == critical_hits
        assert result.compatibility_multipliers == compatibility_multipliers
        assert result.failure_reason is None
    
    def test_create_failure(self):
        """失敗時のBattleActionResultの作成テスト"""
        messages = ["MPが足りない"]
        failure_reason = "insufficient_mp"
        
        result = BattleActionResult.create_failure(
            messages=messages,
            failure_reason=failure_reason,
            hp_consumed=5,
            mp_consumed=0
        )
        
        assert result.success is False
        assert result.messages == messages
        assert result.failure_reason == failure_reason
        assert result.hp_consumed == 5
        assert result.mp_consumed == 0
        
        # 失敗時は空のリストが設定される
        assert len(result.target_ids) == 0
        assert len(result.damages) == 0
        assert len(result.healing_amounts) == 0
        assert len(result.is_target_defeated) == 0
        assert len(result.applied_status_effects) == 0
        assert len(result.applied_buffs) == 0
        assert len(result.critical_hits) == 0
        assert len(result.compatibility_multipliers) == 0
    
    def test_total_damage_property(self):
        """total_damageプロパティのテスト"""
        damages = [10, 15, 20]
        
        result = BattleActionResult.create_success(
            messages=["テスト"],
            target_ids=[1, 2, 3],
            damages=damages,
            healing_amounts=[0, 0, 0],
            is_target_defeated=[False, False, False]
        )
        
        assert result.total_damage == 45  # 10 + 15 + 20
    
    def test_total_healing_property(self):
        """total_healingプロパティのテスト"""
        healing_amounts = [25, 30, 35]
        
        result = BattleActionResult.create_success(
            messages=["テスト"],
            target_ids=[1, 2, 3],
            damages=[0, 0, 0],
            healing_amounts=healing_amounts,
            is_target_defeated=[False, False, False]
        )
        
        assert result.total_healing == 90  # 25 + 30 + 35
    
    def test_validation_target_count_mismatch(self):
        """ターゲット数と配列長の不一致バリデーションテスト"""
        messages = ["テスト"]
        target_ids = [1, 2]
        damages = [10]  # 長さが異なる
        
        with pytest.raises(ValueError, match="damages length \\(1\\) must match target_ids length \\(2\\)"):
            BattleActionResult.create_success(
                messages=messages,
                target_ids=target_ids,
                damages=damages
            )
    
    def test_validation_healing_amounts_mismatch(self):
        """回復量配列の長さ不一致バリデーションテスト"""
        messages = ["テスト"]
        target_ids = [1, 2]
        healing_amounts = [10]  # 長さが異なる
        
        with pytest.raises(ValueError, match="damages length \\(0\\) must match target_ids length \\(2\\)"):
            BattleActionResult.create_success(
                messages=messages,
                target_ids=target_ids,
                damages=[],
                healing_amounts=healing_amounts
            )
    
    def test_validation_is_target_defeated_mismatch(self):
        """撃破フラグ配列の長さ不一致バリデーションテスト"""
        messages = ["テスト"]
        target_ids = [1, 2]
        is_target_defeated = [False]  # 長さが異なる
        
        with pytest.raises(ValueError, match="damages length \\(0\\) must match target_ids length \\(2\\)"):
            BattleActionResult.create_success(
                messages=messages,
                target_ids=target_ids,
                damages=[],
                is_target_defeated=is_target_defeated
            )
    
    def test_validation_critical_hits_mismatch(self):
        """クリティカル配列の長さ不一致バリデーションテスト"""
        messages = ["テスト"]
        target_ids = [1, 2]
        critical_hits = [True]  # 長さが異なる
        
        with pytest.raises(ValueError, match="damages length \\(0\\) must match target_ids length \\(2\\)"):
            BattleActionResult.create_success(
                messages=messages,
                target_ids=target_ids,
                damages=[],
                critical_hits=critical_hits
            )
    
    def test_validation_compatibility_multipliers_mismatch(self):
        """相性倍率配列の長さ不一致バリデーションテスト"""
        messages = ["テスト"]
        target_ids = [1, 2]
        compatibility_multipliers = [1.5]  # 長さが異なる
        
        with pytest.raises(ValueError, match="damages length \\(0\\) must match target_ids length \\(2\\)"):
            BattleActionResult.create_success(
                messages=messages,
                target_ids=target_ids,
                damages=[],
                compatibility_multipliers=compatibility_multipliers
            )
    
    def test_validation_empty_critical_hits_allowed(self):
        """空のクリティカル配列は許可されるテスト"""
        messages = ["テスト"]
        target_ids = [1, 2]
        damages = [10, 15]
        critical_hits = []  # 空は許可
        
        result = BattleActionResult.create_success(
            messages=messages,
            target_ids=target_ids,
            damages=damages,
            healing_amounts=[0, 0],
            is_target_defeated=[False, False],
            critical_hits=critical_hits
        )
        
        assert result.critical_hits == []
    
    def test_validation_empty_compatibility_multipliers_allowed(self):
        """空の相性倍率配列は許可されるテスト"""
        messages = ["テスト"]
        target_ids = [1, 2]
        damages = [10, 15]
        compatibility_multipliers = []  # 空は許可
        
        result = BattleActionResult.create_success(
            messages=messages,
            target_ids=target_ids,
            damages=damages,
            healing_amounts=[0, 0],
            is_target_defeated=[False, False],
            compatibility_multipliers=compatibility_multipliers
        )
        
        assert result.compatibility_multipliers == []
    
    def test_validation_matching_lengths(self):
        """一致する長さでのバリデーションテスト"""
        messages = ["テスト"]
        target_ids = [1, 2, 3]
        damages = [10, 15, 20]
        healing_amounts = [0, 5, 0]
        is_target_defeated = [False, False, True]
        critical_hits = [True, False, True]
        compatibility_multipliers = [1.5, 1.0, 0.8]
        
        result = BattleActionResult.create_success(
            messages=messages,
            target_ids=target_ids,
            damages=damages,
            healing_amounts=healing_amounts,
            is_target_defeated=is_target_defeated,
            critical_hits=critical_hits,
            compatibility_multipliers=compatibility_multipliers
        )
        
        assert len(result.target_ids) == 3
        assert len(result.damages) == 3
        assert len(result.healing_amounts) == 3
        assert len(result.is_target_defeated) == 3
        assert len(result.critical_hits) == 3
        assert len(result.compatibility_multipliers) == 3
    
    def test_immutable(self):
        """不変性のテスト"""
        result = BattleActionResult.create_success(["テスト"])
        
        # frozen=Trueなので変更できない
        with pytest.raises(Exception):
            result.success = False
    
    def test_edge_cases(self):
        """エッジケースのテスト"""
        # 空の配列
        result = BattleActionResult.create_success(
            messages=[],
            target_ids=[],
            damages=[],
            healing_amounts=[],
            is_target_defeated=[]
        )
        
        assert result.total_damage == 0
        assert result.total_healing == 0
        
        # ゼロダメージ
        result2 = BattleActionResult.create_success(
            messages=["テスト"],
            target_ids=[1, 2, 3],
            damages=[0, 0, 0],
            healing_amounts=[0, 0, 0],
            is_target_defeated=[False, False, False]
        )
        
        assert result2.total_damage == 0
        
        # ゼロ回復
        result3 = BattleActionResult.create_success(
            messages=["テスト"],
            target_ids=[1, 2, 3],
            damages=[0, 0, 0],
            healing_amounts=[0, 0, 0],
            is_target_defeated=[False, False, False]
        )
        
        assert result3.total_healing == 0
    
    def test_status_effect_tuple_structure(self):
        """状態異常タプルの構造テスト"""
        applied_status_effects = [
            (1, StatusEffectType.POISON, 3),
            (2, StatusEffectType.BURN, 2)
        ]
        
        result = BattleActionResult.create_success(
            messages=["テスト"],
            applied_status_effects=applied_status_effects
        )
        
        assert len(result.applied_status_effects) == 2
        assert result.applied_status_effects[0][0] == 1  # target_id
        assert result.applied_status_effects[0][1] == StatusEffectType.POISON  # status_effect_type
        assert result.applied_status_effects[0][2] == 3  # duration
        assert result.applied_status_effects[1][0] == 2  # target_id
        assert result.applied_status_effects[1][1] == StatusEffectType.BURN  # status_effect_type
        assert result.applied_status_effects[1][2] == 2  # duration
    
    def test_buff_tuple_structure(self):
        """バフタプルの構造テスト"""
        applied_buffs = [
            (1, BuffType.ATTACK, 1.5, 3),
            (2, BuffType.DEFENSE, 1.2, 2)
        ]
        
        result = BattleActionResult.create_success(
            messages=["テスト"],
            applied_buffs=applied_buffs
        )
        
        assert len(result.applied_buffs) == 2
        assert result.applied_buffs[0][0] == 1  # target_id
        assert result.applied_buffs[0][1] == BuffType.ATTACK  # buff_type
        assert result.applied_buffs[0][2] == 1.5  # multiplier
        assert result.applied_buffs[0][3] == 3  # duration
        assert result.applied_buffs[1][0] == 2  # target_id
        assert result.applied_buffs[1][1] == BuffType.DEFENSE  # buff_type
        assert result.applied_buffs[1][2] == 1.2  # multiplier
        assert result.applied_buffs[1][3] == 2  # duration

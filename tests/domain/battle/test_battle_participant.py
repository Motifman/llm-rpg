import pytest
from src.domain.battle.battle_participant import BattleParticipant
from src.domain.battle.battle_enum import StatusEffectType, BuffType
from src.domain.monster.monster_enum import Race
from src.domain.battle.battle_enum import Element


class MockCombatEntity:
    """テスト用のモック戦闘エンティティ"""
    def __init__(self, name: str = "テストエンティティ"):
        self.name = name
    
    def is_alive(self) -> bool:
        return True


class TestBattleParticipant:
    """BattleParticipantのテストクラス"""
    
    def setup_method(self):
        """テスト用のBattleParticipantを作成"""
        self.entity = MockCombatEntity("テストエンティティ")
        self.participant = BattleParticipant.create(self.entity, 1)
    
    def test_create(self):
        """BattleParticipantの作成テスト"""
        assert self.participant.entity == self.entity
        assert self.participant.entity_id == 1
        assert len(self.participant.status_effects_remaining_duration) == 0
        assert len(self.participant.buffs_remaining_duration) == 0
        assert len(self.participant.buffs_multiplier) == 0
    
    def test_add_status_effect(self):
        """状態異常の追加テスト"""
        self.participant.add_status_effect(StatusEffectType.POISON, 3)
        
        assert StatusEffectType.POISON in self.participant.status_effects_remaining_duration
        assert self.participant.status_effects_remaining_duration[StatusEffectType.POISON] == 3
    
    def test_add_status_effect_invalid_duration(self):
        """無効な持続時間での状態異常追加テスト"""
        with pytest.raises(ValueError, match="Duration must be greater than 0"):
            self.participant.add_status_effect(StatusEffectType.POISON, 0)
        
        with pytest.raises(ValueError, match="Duration must be greater than 0"):
            self.participant.add_status_effect(StatusEffectType.POISON, -1)
    
    def test_get_status_effects(self):
        """状態異常の取得テスト"""
        # 状態異常を追加
        self.participant.add_status_effect(StatusEffectType.POISON, 3)
        self.participant.add_status_effect(StatusEffectType.BURN, 2)
        
        status_effects = self.participant.get_status_effects()
        
        assert len(status_effects) == 2
        assert StatusEffectType.POISON in status_effects
        assert StatusEffectType.BURN in status_effects
    
    def test_has_status_effect(self):
        """状態異常の存在確認テスト"""
        assert self.participant.has_status_effect(StatusEffectType.POISON) is False
        
        self.participant.add_status_effect(StatusEffectType.POISON, 3)
        assert self.participant.has_status_effect(StatusEffectType.POISON) is True
    
    def test_get_status_effect_remaining_duration(self):
        """状態異常の残りターン数取得テスト"""
        # 存在しない状態異常
        duration = self.participant.get_status_effect_remaining_duration(StatusEffectType.POISON)
        assert duration == 0
        
        # 存在する状態異常
        self.participant.add_status_effect(StatusEffectType.POISON, 3)
        duration = self.participant.get_status_effect_remaining_duration(StatusEffectType.POISON)
        assert duration == 3
    
    def test_add_buff(self):
        """バフの追加テスト"""
        self.participant.add_buff(BuffType.ATTACK, 3, 1.5)
        
        assert BuffType.ATTACK in self.participant.buffs_remaining_duration
        assert self.participant.buffs_remaining_duration[BuffType.ATTACK] == 3
        assert BuffType.ATTACK in self.participant.buffs_multiplier
        assert self.participant.buffs_multiplier[BuffType.ATTACK] == 1.5
    
    def test_add_buff_invalid_duration(self):
        """無効な持続時間でのバフ追加テスト"""
        with pytest.raises(ValueError, match="Duration must be greater than 0"):
            self.participant.add_buff(BuffType.ATTACK, 0, 1.5)
        
        with pytest.raises(ValueError, match="Duration must be greater than 0"):
            self.participant.add_buff(BuffType.ATTACK, -1, 1.5)
    
    def test_add_buff_invalid_multiplier(self):
        """無効な倍率でのバフ追加テスト"""
        with pytest.raises(ValueError, match="Multiplier must be greater than 0"):
            self.participant.add_buff(BuffType.ATTACK, 3, 0)
        
        with pytest.raises(ValueError, match="Multiplier must be greater than 0"):
            self.participant.add_buff(BuffType.ATTACK, 3, -0.5)
    
    def test_get_buff_multiplier(self):
        """バフ倍率の取得テスト"""
        # 存在しないバフ
        multiplier = self.participant.get_buff_multiplier(BuffType.ATTACK)
        assert multiplier == 1.0  # デフォルト値
        
        # 存在するバフ
        self.participant.add_buff(BuffType.ATTACK, 3, 1.5)
        multiplier = self.participant.get_buff_multiplier(BuffType.ATTACK)
        assert multiplier == 1.5
    
    def test_process_status_effects_on_turn_start(self):
        """ターン開始時の状態異常処理テスト"""
        # 状態異常を追加
        self.participant.add_status_effect(StatusEffectType.POISON, 3)
        self.participant.add_status_effect(StatusEffectType.BURN, 1)
        
        # ターン開始処理
        self.participant.process_status_effects_on_turn_start()
        
        # 残りターン数が減っていることを確認
        assert self.participant.status_effects_remaining_duration[StatusEffectType.POISON] == 2
        assert self.participant.status_effects_remaining_duration[StatusEffectType.BURN] == 0
        
        # ターン終了処理
        self.participant.process_status_effects_on_turn_end()
        
        # 残りターン数が0になった状態異常は削除される
        assert StatusEffectType.BURN not in self.participant.status_effects_remaining_duration
        assert StatusEffectType.POISON in self.participant.status_effects_remaining_duration
    
    def test_process_status_effects_on_turn_start_invalid_duration(self):
        """無効な持続時間でのターン開始処理テスト"""
        # 負の持続時間を直接設定（異常な状態）
        self.participant.status_effects_remaining_duration[StatusEffectType.POISON] = -1
        
        with pytest.raises(ValueError, match="Duration must be greater than 0"):
            self.participant.process_status_effects_on_turn_start()
    
    def test_process_status_effects_on_turn_end(self):
        """ターン終了時の状態異常処理テスト"""
        # 状態異常を追加（残り0ターン）
        self.participant.status_effects_remaining_duration[StatusEffectType.POISON] = 0
        self.participant.status_effects_remaining_duration[StatusEffectType.BURN] = 1
        
        # ターン終了処理
        self.participant.process_status_effects_on_turn_end()
        
        # 残り0ターンの状態異常は削除される
        assert StatusEffectType.POISON not in self.participant.status_effects_remaining_duration
        assert StatusEffectType.BURN in self.participant.status_effects_remaining_duration
        assert self.participant.status_effects_remaining_duration[StatusEffectType.BURN] == 1
    
    def test_process_status_effects_on_turn_end_invalid_duration(self):
        """無効な持続時間でのターン終了処理テスト"""
        # 負の持続時間を直接設定（異常な状態）
        self.participant.status_effects_remaining_duration[StatusEffectType.POISON] = -1
        
        with pytest.raises(ValueError, match="Duration must be greater than 0"):
            self.participant.process_status_effects_on_turn_end()
    
    def test_recover_status_effects(self):
        """状態異常の回復テスト"""
        # 状態異常を追加
        self.participant.add_status_effect(StatusEffectType.POISON, 3)
        self.participant.add_status_effect(StatusEffectType.BURN, 2)
        
        # 特定の状態異常を回復
        self.participant.recover_status_effects(StatusEffectType.POISON)
        
        # 指定した状態異常のみ削除される
        assert StatusEffectType.POISON not in self.participant.status_effects_remaining_duration
        assert StatusEffectType.BURN in self.participant.status_effects_remaining_duration
    
    def test_recover_status_effects_nonexistent(self):
        """存在しない状態異常の回復テスト"""
        # 存在しない状態異常を回復しようとしてもエラーにならない
        self.participant.recover_status_effects(StatusEffectType.POISON)
        
        # 状態異常リストは空のまま
        assert len(self.participant.status_effects_remaining_duration) == 0
    
    def test_process_buffs_on_turn_start(self):
        """ターン開始時のバフ処理テスト"""
        # バフを追加
        self.participant.add_buff(BuffType.ATTACK, 3, 1.5)
        self.participant.add_buff(BuffType.DEFENSE, 1, 1.2)
        
        # ターン開始処理
        self.participant.process_buffs_on_turn_start()
        
        # 残りターン数が減っていることを確認
        assert self.participant.buffs_remaining_duration[BuffType.ATTACK] == 2
        assert self.participant.buffs_remaining_duration[BuffType.DEFENSE] == 0
        
        # ターン終了処理
        self.participant.process_buffs_on_turn_end()
        
        # 残りターン数が0になったバフは削除される
        assert BuffType.DEFENSE not in self.participant.buffs_remaining_duration
        assert BuffType.ATTACK in self.participant.buffs_remaining_duration
    
    def test_process_buffs_on_turn_start_invalid_duration(self):
        """無効な持続時間でのターン開始処理テスト"""
        # 負の持続時間を直接設定（異常な状態）
        self.participant.buffs_remaining_duration[BuffType.ATTACK] = -1
        
        with pytest.raises(ValueError, match="Duration must be greater than 0"):
            self.participant.process_buffs_on_turn_start()
    
    def test_process_buffs_on_turn_end(self):
        """ターン終了時のバフ処理テスト"""
        # バフを追加（残り0ターン）
        self.participant.buffs_remaining_duration[BuffType.ATTACK] = 0
        self.participant.buffs_multiplier[BuffType.ATTACK] = 1.5
        self.participant.buffs_remaining_duration[BuffType.DEFENSE] = 1
        self.participant.buffs_multiplier[BuffType.DEFENSE] = 1.2
        
        # ターン終了処理
        self.participant.process_buffs_on_turn_end()
        
        # 残り0ターンのバフは削除される
        assert BuffType.ATTACK not in self.participant.buffs_remaining_duration
        assert BuffType.ATTACK not in self.participant.buffs_multiplier
        assert BuffType.DEFENSE in self.participant.buffs_remaining_duration
        assert BuffType.DEFENSE in self.participant.buffs_multiplier
        assert self.participant.buffs_remaining_duration[BuffType.DEFENSE] == 1
    
    def test_process_buffs_on_turn_end_invalid_duration(self):
        """無効な持続時間でのターン終了処理テスト"""
        # 負の持続時間を直接設定（異常な状態）
        self.participant.buffs_remaining_duration[BuffType.ATTACK] = -1
        
        with pytest.raises(ValueError, match="Duration must be greater than 0"):
            self.participant.process_buffs_on_turn_end()
    
    def test_multiple_status_effects(self):
        """複数の状態異常の管理テスト"""
        # 複数の状態異常を追加
        self.participant.add_status_effect(StatusEffectType.POISON, 3)
        self.participant.add_status_effect(StatusEffectType.BURN, 2)
        self.participant.add_status_effect(StatusEffectType.SLEEP, 1)
        
        # 状態異常の確認
        status_effects = self.participant.get_status_effects()
        assert len(status_effects) == 3
        assert StatusEffectType.POISON in status_effects
        assert StatusEffectType.BURN in status_effects
        assert StatusEffectType.SLEEP in status_effects
        
        # 1ターン目: 開始処理
        self.participant.process_status_effects_on_turn_start()
        # 残りターン数の確認
        assert self.participant.get_status_effect_remaining_duration(StatusEffectType.POISON) == 2
        assert self.participant.get_status_effect_remaining_duration(StatusEffectType.BURN) == 1
        assert self.participant.get_status_effect_remaining_duration(StatusEffectType.SLEEP) == 0
        
        # 1ターン目: 終了処理
        self.participant.process_status_effects_on_turn_end()
        # 期限切れの状態異常は削除される
        status_effects = self.participant.get_status_effects()
        assert len(status_effects) == 2
        assert StatusEffectType.POISON in status_effects
        assert StatusEffectType.BURN in status_effects
        assert StatusEffectType.SLEEP not in status_effects
    
    def test_multiple_buffs(self):
        """複数のバフの管理テスト"""
        # 複数のバフを追加
        self.participant.add_buff(BuffType.ATTACK, 3, 1.5)
        self.participant.add_buff(BuffType.DEFENSE, 2, 1.2)
        self.participant.add_buff(BuffType.SPEED, 1, 1.1)
        
        # バフ倍率の確認
        assert self.participant.get_buff_multiplier(BuffType.ATTACK) == 1.5
        assert self.participant.get_buff_multiplier(BuffType.DEFENSE) == 1.2
        assert self.participant.get_buff_multiplier(BuffType.SPEED) == 1.1
        
        # 1ターン目: 開始処理
        self.participant.process_buffs_on_turn_start()
        # 残りターン数の確認
        assert self.participant.buffs_remaining_duration[BuffType.ATTACK] == 2
        assert self.participant.buffs_remaining_duration[BuffType.DEFENSE] == 1
        assert self.participant.buffs_remaining_duration[BuffType.SPEED] == 0
        
        # 1ターン目: 終了処理
        self.participant.process_buffs_on_turn_end()
        # 期限切れのバフは削除される
        assert BuffType.ATTACK in self.participant.buffs_remaining_duration
        assert BuffType.DEFENSE in self.participant.buffs_remaining_duration
        assert BuffType.SPEED not in self.participant.buffs_remaining_duration
        assert BuffType.SPEED not in self.participant.buffs_multiplier
    
    def test_status_effect_overwrite(self):
        """状態異常の上書きテスト"""
        # 同じ状態異常を複数回追加
        self.participant.add_status_effect(StatusEffectType.POISON, 3)
        self.participant.add_status_effect(StatusEffectType.POISON, 5)
        
        # 後から追加したものが有効
        assert self.participant.get_status_effect_remaining_duration(StatusEffectType.POISON) == 5
    
    def test_buff_overwrite(self):
        """バフの上書きテスト"""
        # 同じバフを複数回追加
        self.participant.add_buff(BuffType.ATTACK, 3, 1.5)
        self.participant.add_buff(BuffType.ATTACK, 5, 2.0)
        
        # 後から追加したものが有効
        assert self.participant.buffs_remaining_duration[BuffType.ATTACK] == 5
        assert self.participant.buffs_multiplier[BuffType.ATTACK] == 2.0
    
    def test_empty_participant(self):
        """空の参加者のテスト"""
        # 何も追加されていない状態
        assert len(self.participant.get_status_effects()) == 0
        assert self.participant.get_buff_multiplier(BuffType.ATTACK) == 1.0
        assert self.participant.get_buff_multiplier(BuffType.DEFENSE) == 1.0
        assert self.participant.get_buff_multiplier(BuffType.SPEED) == 1.0
        
        # 処理を実行してもエラーにならない
        self.participant.process_status_effects_on_turn_start()
        self.participant.process_status_effects_on_turn_end()
        self.participant.process_buffs_on_turn_start()
        self.participant.process_buffs_on_turn_end()

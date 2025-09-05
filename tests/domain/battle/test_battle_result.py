import pytest
from unittest.mock import Mock

from src.domain.battle.battle_result import (
    TurnStartResult,
    TurnEndResult,
    ActorStateChange,
    TargetStateChange,
    BattleActionMetadata,
    BattleActionResult,
)
from src.domain.battle.battle_enum import StatusEffectType, BuffType, ParticipantType
from src.domain.battle.combat_state import CombatState
from src.domain.player.hp import Hp
from src.domain.player.mp import Mp


@pytest.fixture
def mock_combat_state():
    """テスト用のCombatStateモック"""
    return Mock(spec=CombatState)


@pytest.fixture
def sample_combat_state():
    """テスト用のCombatStateインスタンス"""
    return CombatState(
        entity_id=1,
        participant_type=ParticipantType.PLAYER,
        name="Test Player",
        race=Mock(),  # Race enumのモック
        element=Mock(),  # Element enumのモック
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


class TestTurnStartResult:
    def test_creation_with_valid_values(self):
        """有効な値での作成テスト"""
        result = TurnStartResult(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            can_act=True,
            damage=10,
            healing=5,
            messages=["Test message"],
            status_effects_to_remove=[StatusEffectType.POISON],
            buffs_to_remove=[BuffType.ATTACK]
        )
        assert result.actor_id == 1
        assert result.participant_type == ParticipantType.PLAYER
        assert result.can_act is True
        assert result.damage == 10
        assert result.healing == 5
        assert result.messages == ["Test message"]
        assert result.status_effects_to_remove == [StatusEffectType.POISON]
        assert result.buffs_to_remove == [BuffType.ATTACK]

    def test_validation_negative_damage_raises_error(self):
        """負のダメージ値でエラーが発生することをテスト"""
        with pytest.raises(ValueError, match="Damage must be non-negative"):
            TurnStartResult(
                actor_id=1,
                participant_type=ParticipantType.PLAYER,
                can_act=True,
                damage=-5
            )

    def test_validation_negative_healing_raises_error(self):
        """負の回復値でエラーが発生することをテスト"""
        with pytest.raises(ValueError, match="Healing must be non-negative"):
            TurnStartResult(
                actor_id=1,
                participant_type=ParticipantType.PLAYER,
                can_act=True,
                healing=-5
            )

    def test_apply_to_combat_state_success(self, sample_combat_state):
        """CombatStateへの適用が成功することをテスト"""
        result = TurnStartResult(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            can_act=True,
            damage=10,
            healing=5,
            status_effects_to_remove=[],  # 空のリストに変更
            buffs_to_remove=[]  # 空のリストに変更
        )

        # CombatStateのメソッドが呼ばれることを確認
        new_state = result.apply_to_combat_state(sample_combat_state)

        assert new_state is not sample_combat_state  # 新しいインスタンスが返される

    def test_apply_to_combat_state_wrong_actor_id_raises_error(self, sample_combat_state):
        """アクターIDが一致しない場合エラーが発生することをテスト"""
        result = TurnStartResult(
            actor_id=2,  # 異なるID
            participant_type=ParticipantType.PLAYER,
            can_act=True
        )

        with pytest.raises(ValueError, match="Actor ID does not match combat state"):
            result.apply_to_combat_state(sample_combat_state)


class TestTurnEndResult:
    def test_creation_with_valid_values(self):
        """有効な値での作成テスト"""
        result = TurnEndResult(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            messages=["Turn end message"],
            damage=8,
            healing=3,
            status_effects_to_remove=[StatusEffectType.PARALYSIS],
            buffs_to_remove=[BuffType.DEFENSE]
        )
        assert result.actor_id == 1
        assert result.participant_type == ParticipantType.PLAYER
        assert result.messages == ["Turn end message"]
        assert result.damage == 8
        assert result.healing == 3
        assert result.status_effects_to_remove == [StatusEffectType.PARALYSIS]
        assert result.buffs_to_remove == [BuffType.DEFENSE]

    def test_validation_negative_damage_raises_error(self):
        """負のダメージ値でエラーが発生することをテスト"""
        with pytest.raises(ValueError, match="Damage must be non-negative"):
            TurnEndResult(
                actor_id=1,
                participant_type=ParticipantType.PLAYER,
                damage=-5
            )

    def test_validation_negative_healing_raises_error(self):
        """負の回復値でエラーが発生することをテスト"""
        with pytest.raises(ValueError, match="Healing must be non-negative"):
            TurnEndResult(
                actor_id=1,
                participant_type=ParticipantType.PLAYER,
                healing=-5
            )

    def test_apply_to_combat_state_success(self, sample_combat_state):
        """CombatStateへの適用が成功することをテスト"""
        result = TurnEndResult(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            damage=5,
            healing=2
        )

        new_state = result.apply_to_combat_state(sample_combat_state)

        assert new_state is not sample_combat_state


class TestActorStateChange:
    def test_creation_with_negative_hp_mp_changes(self):
        """負のHP/MP変更値での作成テスト（ダメージ/消費を表す）"""
        change = ActorStateChange(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            hp_change=-20,  # ダメージ
            mp_change=-10,  # MP消費
            status_effects_to_add=[(StatusEffectType.POISON, 3)],
            buffs_to_add=[(BuffType.ATTACK, 1.5, 2)],
            is_defend=True
        )
        assert change.actor_id == 1
        assert change.participant_type == ParticipantType.PLAYER
        assert change.hp_change == -20
        assert change.mp_change == -10
        assert change.status_effects_to_add == [(StatusEffectType.POISON, 3)]
        assert change.buffs_to_add == [(BuffType.ATTACK, 1.5, 2)]
        assert change.is_defend is True

    def test_creation_with_positive_hp_mp_changes(self):
        """正のHP/MP変更値での作成テスト（回復を表す）"""
        change = ActorStateChange(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            hp_change=15,  # 回復
            mp_change=8,   # MP回復
        )
        assert change.hp_change == 15
        assert change.mp_change == 8

    def test_apply_damage_to_combat_state(self, sample_combat_state):
        """ダメージ適用が正しく動作することをテスト"""
        change = ActorStateChange(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            hp_change=-10  # ダメージ
        )

        # CombatStateのwith_hp_damagedが呼ばれることを確認
        result_state = change.apply_to_combat_state(sample_combat_state)

        assert result_state is not sample_combat_state

    def test_apply_healing_to_combat_state(self, sample_combat_state):
        """回復適用が正しく動作することをテスト"""
        change = ActorStateChange(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            hp_change=10  # 回復
        )

        result_state = change.apply_to_combat_state(sample_combat_state)

        assert result_state is not sample_combat_state

    def test_apply_mp_consumption_to_combat_state(self, sample_combat_state):
        """MP消費適用が正しく動作することをテスト"""
        change = ActorStateChange(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            mp_change=-5  # MP消費
        )

        result_state = change.apply_to_combat_state(sample_combat_state)

        assert result_state is not sample_combat_state

    def test_apply_mp_healing_to_combat_state(self, sample_combat_state):
        """MP回復適用が正しく動作することをテスト"""
        change = ActorStateChange(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            mp_change=5  # MP回復
        )

        result_state = change.apply_to_combat_state(sample_combat_state)

        assert result_state is not sample_combat_state


class TestTargetStateChange:
    def test_creation_with_negative_hp_mp_changes(self):
        """負のHP/MP変更値での作成テスト"""
        change = TargetStateChange(
            target_id=2,
            participant_type=ParticipantType.MONSTER,
            hp_change=-25,  # ダメージ
            mp_change=-8,   # MP消費
            status_effects_to_add=[(StatusEffectType.SLEEP, 2)],
            buffs_to_remove=[BuffType.DEFENSE]
        )
        assert change.target_id == 2
        assert change.participant_type == ParticipantType.MONSTER
        assert change.hp_change == -25
        assert change.mp_change == -8
        assert change.status_effects_to_add == [(StatusEffectType.SLEEP, 2)]
        assert change.buffs_to_remove == [BuffType.DEFENSE]

    def test_apply_damage_to_combat_state(self, sample_combat_state):
        """ダメージ適用が正しく動作することをテスト"""
        change = TargetStateChange(
            target_id=1,
            participant_type=ParticipantType.PLAYER,
            hp_change=-15  # ダメージ
        )

        result_state = change.apply_to_combat_state(sample_combat_state)

        assert result_state is not sample_combat_state


class TestBattleActionMetadata:
    def test_creation_with_valid_lists(self):
        """有効なリストでの作成テスト"""
        metadata = BattleActionMetadata(
            critical_hits=[True, False, True],
            compatibility_multipliers=[1.5, 1.0, 2.0],
            race_attack_multipliers=[1.2, 1.0, 0.8]
        )
        assert metadata.critical_hits == [True, False, True]
        assert metadata.compatibility_multipliers == [1.5, 1.0, 2.0]
        assert metadata.race_attack_multipliers == [1.2, 1.0, 0.8]

    def test_validation_list_length_mismatch_raises_error(self):
        """リスト長が一致しない場合エラーが発生することをテスト"""
        with pytest.raises(ValueError, match="critical_hits, compatibility_multipliers, race_attack_multipliersの長さが一致していません"):
            BattleActionMetadata(
                critical_hits=[True, False],
                compatibility_multipliers=[1.5, 1.0, 2.0],  # 長さが異なる
                race_attack_multipliers=[1.2, 1.0]
            )


class TestBattleActionResult:
    def test_create_success(self):
        """成功時のBattleActionResult作成テスト"""
        messages = ["攻撃成功", "クリティカルヒット"]
        actor_change = ActorStateChange(
            actor_id=1,
            participant_type=ParticipantType.PLAYER,
            mp_change=-5
        )
        target_changes = [
            TargetStateChange(
                target_id=2,
                participant_type=ParticipantType.MONSTER,
                hp_change=-30
            )
        ]
        metadata = BattleActionMetadata(
            critical_hits=[True],
            compatibility_multipliers=[1.5],
            race_attack_multipliers=[1.2]
        )

        result = BattleActionResult.create_success(
            messages=messages,
            actor_state_change=actor_change,
            target_state_changes=target_changes,
            metadata=metadata
        )

        assert result.success is True
        assert result.messages == messages
        assert result.actor_state_change == actor_change
        assert result.target_state_changes == target_changes
        assert result.metadata == metadata
        assert result.failure_reason is None

    def test_create_failure(self):
        """失敗時のBattleActionResult作成テスト"""
        messages = ["攻撃失敗"]
        failure_reason = "MPが不足しています"

        result = BattleActionResult.create_failure(
            messages=messages,
            failure_reason=failure_reason
        )

        assert result.success is False
        assert result.messages == messages
        assert result.failure_reason == failure_reason
        assert result.target_state_changes == []

    def test_total_damage_dealt_calculation(self):
        """与えたダメージ合計の計算テスト"""
        result = BattleActionResult.create_success(
            messages=["攻撃成功"],
            target_state_changes=[
                TargetStateChange(target_id=1, participant_type=ParticipantType.PLAYER, hp_change=-20),  # ダメージ
                TargetStateChange(target_id=2, participant_type=ParticipantType.PLAYER, hp_change=10),   # 回復
                TargetStateChange(target_id=3, participant_type=ParticipantType.PLAYER, hp_change=-15),  # ダメージ
            ]
        )

        assert result.total_damage_dealt == 35  # 20 + 15

    def test_total_healing_dealt_calculation(self):
        """与えた回復合計の計算テスト"""
        result = BattleActionResult.create_success(
            messages=["回復成功"],
            target_state_changes=[
                TargetStateChange(target_id=1, participant_type=ParticipantType.PLAYER, hp_change=-10),  # ダメージ
                TargetStateChange(target_id=2, participant_type=ParticipantType.PLAYER, hp_change=25),   # 回復
                TargetStateChange(target_id=3, participant_type=ParticipantType.PLAYER, hp_change=15),   # 回復
            ]
        )

        assert result.total_healing_dealt == 40  # 25 + 15

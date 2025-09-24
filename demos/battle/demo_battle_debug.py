#!/usr/bin/env python3
"""
戦闘システムのデバッグ用デモ

戦闘状態とダメージ計算を詳しく確認するためのデバッグツール
"""
import asyncio
from src.infrastructure.repository.in_memory_player_repository import InMemoryPlayerRepository
from src.infrastructure.repository.in_memory_monster_repository import InMemoryMonsterRepository
from src.infrastructure.repository.in_memory_action_repository import InMemoryActionRepository
from src.infrastructure.repository.in_memory_area_repository import InMemoryAreaRepository
from src.infrastructure.repository.in_memory_battle_repository import InMemoryBattleRepository
from src.domain.battle.battle import Battle
from src.domain.battle.battle_service import BattleLogicService
from src.domain.battle.combat_state import CombatState
from src.domain.battle.battle_enum import ParticipantType
from src.application.battle.contracts.dtos import PlayerActionDto


async def debug_battle_system():
    """戦闘システムのデバッグ"""
    print("🔍 戦闘システムデバッグ")
    print("=" * 40)
    
    # リポジトリの初期化
    player_repository = InMemoryPlayerRepository()
    monster_repository = InMemoryMonsterRepository()
    action_repository = InMemoryActionRepository()
    area_repository = InMemoryAreaRepository()
    battle_repository = InMemoryBattleRepository()
    
    # プレイヤーとモンスターを取得
    players = player_repository.find_by_spot_id(100)
    monsters = monster_repository.find_by_ids([101, 102])  # スライムとゴブリン
    
    if not players or not monsters:
        print("❌ プレイヤーまたはモンスターが見つかりません")
        return
    
    player = players[0]
    
    print(f"👤 プレイヤー: {player.name}")
    print(f"  - 攻撃力: {player._base_status.attack}")
    print(f"  - HP: {player._dynamic_status.hp.value}/{player._dynamic_status.hp.max_hp}")
    print(f"  - MP: {player._dynamic_status.mp.value}/{player._dynamic_status.mp.max_mp}")
    
    print(f"\n🐉 モンスター情報:")
    for monster in monsters:
        print(f"  - {monster.name}: HP {monster.max_hp}, 攻撃力 {monster.base_status.attack}")
    
    # 戦闘を作成
    battle = Battle(
        battle_id=1,
        spot_id=100,
        players=[player],
        monsters=monsters
    )
    battle.start_battle()
    
    print(f"\n⚔️ 戦闘開始")
    print(f"参加者数: プレイヤー {len(battle.get_player_ids())}, モンスター {len(battle.get_monster_type_ids())}")
    
    # 戦闘状態を確認
    print(f"\n📊 戦闘状態詳細:")
    combat_states = battle.get_combat_states()
    for (participant_type, entity_id), combat_state in combat_states.items():
        print(f"  {participant_type.value} {entity_id}:")
        print(f"    - HP: {combat_state.current_hp.value}/{combat_state.current_hp.max_hp}")
        print(f"    - MP: {combat_state.current_mp.value}/{combat_state.current_mp.max_mp}")
        print(f"    - 攻撃力: {combat_state.calculate_current_attack()}")
        print(f"    - 生存: {combat_state.is_alive()}")
    
    # アクションのダメージ計算をテスト
    print(f"\n🎯 アクションダメージ計算テスト:")
    
    battle_logic_service = BattleLogicService()
    player_combat_state = battle.get_combat_state(ParticipantType.PLAYER, player.player_id)
    monster_combat_state = battle.get_combat_state(ParticipantType.MONSTER, 1)
    
    # 各アクションのダメージを計算
    action_ids = [1, 2, 3, 6]  # 基本攻撃, 強攻撃, ファイアボール, 必殺技
    action_names = ["基本攻撃", "強攻撃", "ファイアボール", "必殺技"]
    
    for action_id, action_name in zip(action_ids, action_names):
        action = action_repository.find_by_id(action_id)
        if action and player_combat_state and monster_combat_state:
            try:
                damage_result = battle_logic_service.damage_calculator.calculate_damage(
                    player_combat_state, monster_combat_state, action
                )
                print(f"  {action_name} (倍率: {action.damage_multiplier}):")
                print(f"    - 計算ダメージ: {damage_result.damage}")
                print(f"    - クリティカル: {damage_result.is_critical}")
                print(f"    - モンスターHP: {monster_combat_state.current_hp.value}")
                print(f"    - 一撃で倒せる: {damage_result.damage >= monster_combat_state.current_hp.value}")
            except Exception as e:
                print(f"    ❌ ダメージ計算エラー: {e}")
    
    # 戦闘終了条件をテスト
    print(f"\n🏁 戦闘終了条件テスト:")
    battle_result = battle.check_battle_end_conditions()
    print(f"  現在の戦闘結果: {battle_result}")
    
    # モンスターを手動で倒してみる
    print(f"\n💀 モンスターを手動で倒してテスト:")
    for (participant_type, entity_id), combat_state in combat_states.items():
        if participant_type == ParticipantType.MONSTER:
            print(f"  モンスター {entity_id} HP: {combat_state.current_hp.value} -> 0")
            # 手動でHPを0にする
            damaged_state = combat_state.with_hp_damaged(combat_state.current_hp.value)
            battle._combat_states[(participant_type, entity_id)] = damaged_state
    
    # 戦闘終了条件を再チェック
    battle_result_after = battle.check_battle_end_conditions()
    print(f"  全モンスター撃破後の戦闘結果: {battle_result_after}")
    
    print(f"\n✅ デバッグ完了")


async def main():
    """メイン関数"""
    await debug_battle_system()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
シンプルな攻撃テスト

ダメージ計算と適用が正しく動作するかを確認する最小限のテスト
"""
import asyncio
from ai_rpg_world.infrastructure.repository.in_memory_player_repository import InMemoryPlayerRepository
from ai_rpg_world.infrastructure.repository.in_memory_monster_repository import InMemoryMonsterRepository
from ai_rpg_world.infrastructure.repository.in_memory_action_repository import InMemoryActionRepository
from ai_rpg_world.domain.battle.battle import Battle
from ai_rpg_world.domain.battle.battle_service import BattleLogicService
from ai_rpg_world.domain.battle.battle_enum import ParticipantType


async def test_simple_attack():
    """シンプルな攻撃テスト"""
    print("🗡️ シンプルな攻撃テスト")
    print("=" * 40)
    
    # リポジトリの初期化
    player_repository = InMemoryPlayerRepository()
    monster_repository = InMemoryMonsterRepository()
    action_repository = InMemoryActionRepository()
    
    # プレイヤーとモンスターを取得
    players = player_repository.find_by_spot_id(100)
    monsters = monster_repository.find_by_ids([101])  # スライムのみ
    
    if not players or not monsters:
        print("❌ プレイヤーまたはモンスターが見つかりません")
        return
    
    player = players[0]
    monster = monsters[0]
    
    print(f"👤 攻撃者: {player.name}")
    print(f"🐉 対象: {monster.name} (HP: {monster.max_hp})")
    
    # 戦闘を作成
    battle = Battle(
        battle_id=1,
        spot_id=100,
        players=[player],
        monsters=[monster]
    )
    battle.start_battle()
    
    # 戦闘状態を確認
    player_combat_state = battle.get_combat_state(ParticipantType.PLAYER, player.player_id)
    monster_combat_state = battle.get_combat_state(ParticipantType.MONSTER, 1)
    
    print(f"\n📊 戦闘前の状態:")
    print(f"  プレイヤー: HP {player_combat_state.current_hp.value}, 攻撃力 {player_combat_state.calculate_current_attack()}")
    print(f"  モンスター: HP {monster_combat_state.current_hp.value}")
    
    # 基本攻撃を取得
    basic_attack = action_repository.find_by_id(1)
    print(f"\n⚔️ 使用アクション: {basic_attack.name} (倍率: {basic_attack.damage_multiplier})")
    
    # BattleLogicServiceを作成
    battle_logic_service = BattleLogicService()
    
    # ダメージ計算
    damage_result = battle_logic_service.damage_calculator.calculate_damage(
        player_combat_state, monster_combat_state, basic_attack
    )
    print(f"\n💥 ダメージ計算結果:")
    print(f"  - ダメージ: {damage_result.damage}")
    print(f"  - クリティカル: {damage_result.is_critical}")
    print(f"  - 相性倍率: {damage_result.compatibility_multiplier}")
    print(f"  - 種族倍率: {damage_result.race_attack_multiplier}")
    
    # アクションを実行
    print(f"\n🎯 アクション実行:")
    try:
        all_participants = list(battle.get_combat_states().values())
        specified_targets = [monster_combat_state]
        
        battle_action_result = basic_attack.execute(
            actor=player_combat_state,
            specified_targets=specified_targets,
            context=battle_logic_service,
            all_participants=all_participants
        )
        
        print(f"  ✅ アクション実行成功")
        print(f"  - 成功: {battle_action_result.success}")
        print(f"  - メッセージ: {battle_action_result.messages}")
        
        # アクター状態変化
        actor_change = battle_action_result.actor_state_change
        print(f"  - アクター変化: HP{actor_change.hp_change}, MP{actor_change.mp_change}")
        
        # ターゲット状態変化
        for target_change in battle_action_result.target_state_changes:
            print(f"  - ターゲット{target_change.target_id}変化: HP{target_change.hp_change}, MP{target_change.mp_change}")
        
        # 結果を戦闘に適用
        print(f"\n🔄 結果を戦闘に適用:")
        battle.apply_battle_action_result(battle_action_result)
        
        # 適用後の状態を確認
        updated_monster_state = battle.get_combat_state(ParticipantType.MONSTER, 1)
        print(f"  適用後モンスターHP: {updated_monster_state.current_hp.value}")
        print(f"  モンスター生存: {updated_monster_state.is_alive()}")
        
        # 戦闘終了条件をチェック
        battle_result = battle.check_battle_end_conditions()
        print(f"  戦闘終了条件: {battle_result}")
        
    except Exception as e:
        print(f"  ❌ アクション実行エラー: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n✅ シンプル攻撃テスト完了")


async def main():
    """メイン関数"""
    await test_simple_attack()


if __name__ == "__main__":
    asyncio.run(main())

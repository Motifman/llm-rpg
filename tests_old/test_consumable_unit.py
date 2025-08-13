"""
消費可能アイテムシステムの単体テスト
個別機能を詳細にテストする
"""

from src_old.models.agent import Agent
from src_old.models.item import Item, ConsumableItem, ItemEffect
from src_old.models.action import ItemUsage
from src_old.systems.world import World


def test_item_effect_creation():
    """ItemEffectクラスのテスト"""
    print("🧪 ItemEffectクラステスト")
    
    # 基本的なItemEffect
    effect = ItemEffect(hp_change=30, mp_change=20)
    assert effect.hp_change == 30, "HP変化量が正しくありません"
    assert effect.mp_change == 20, "MP変化量が正しくありません"
    assert effect.attack_change == 0, "デフォルト値が正しくありません"
    print("✅ 基本的なItemEffect作成")
    
    # 複合効果のItemEffect
    complex_effect = ItemEffect(
        hp_change=50,
        mp_change=30,
        attack_change=5,
        defense_change=3,
        money_change=100,
        experience_change=25
    )
    assert complex_effect.hp_change == 50, "HP変化量が正しくありません"
    assert complex_effect.money_change == 100, "所持金変化量が正しくありません"
    print("✅ 複合効果ItemEffect作成")
    
    # 文字列表現のテスト
    effect_str = str(effect)
    assert "HP+30" in effect_str, "HP効果が文字列に含まれていません"
    assert "MP+20" in effect_str, "MP効果が文字列に含まれていません"
    print("✅ ItemEffect文字列表現")
    
    print("✅ ItemEffectクラステスト完了\n")


def test_consumable_item_creation():
    """ConsumableItemクラスのテスト"""
    print("🧪 ConsumableItemクラステスト")
    
    # 基本的なConsumableItem
    effect = ItemEffect(hp_change=30)
    potion = ConsumableItem(
        item_id="test_potion",
        description="テスト用ポーション",
        effect=effect,
        max_stack=5
    )
    
    assert potion.item_id == "test_potion", "アイテムIDが正しくありません"
    assert potion.effect.hp_change == 30, "効果が正しく設定されていません"
    assert potion.max_stack == 5, "最大スタック数が正しくありません"
    print("✅ 基本的なConsumableItem作成")
    
    # エージェントなしでのcan_consume（エラーになるはず）
    agent = Agent("test_agent", "テストエージェント")
    assert not potion.can_consume(agent), "アイテムを持っていないのにcan_consumeがTrueになりました"
    print("✅ can_consume（アイテムなし）")
    
    # アイテムを持たせてからのcan_consume
    agent.add_item(potion)
    assert potion.can_consume(agent), "アイテムを持っているのにcan_consumeがFalseになりました"
    print("✅ can_consume（アイテムあり）")
    
    print("✅ ConsumableItemクラステスト完了\n")


def test_agent_rpg_stats():
    """AgentのRPG統計機能のテスト"""
    print("🧪 AgentのRPG統計機能テスト")
    
    agent = Agent("test_agent", "テストエージェント")
    
    # 初期値の確認
    assert agent.current_hp == 100, "初期HPが正しくありません"
    assert agent.max_hp == 100, "最大HPが正しくありません"
    assert agent.current_mp == 50, "初期MPが正しくありません"
    assert agent.max_mp == 50, "最大MPが正しくありません"
    assert agent.attack == 10, "初期攻撃力が正しくありません"
    assert agent.defense == 5, "初期防御力が正しくありません"
    print("✅ 初期ステータス確認")
    
    # HP設定のテスト（上限・下限チェック）
    agent.set_hp(150)  # 上限を超える
    assert agent.current_hp == 100, "HP上限チェックが動作していません"
    
    agent.set_hp(-10)  # 下限を下回る
    assert agent.current_hp == 0, "HP下限チェックが動作していません"
    
    agent.set_hp(75)  # 正常値
    assert agent.current_hp == 75, "HP設定が正しくありません"
    print("✅ HP設定と上限・下限チェック")
    
    # MP設定のテスト
    agent.set_mp(100)  # 上限を超える
    assert agent.current_mp == 50, "MP上限チェックが動作していません"
    
    agent.set_mp(-5)  # 下限を下回る
    assert agent.current_mp == 0, "MP下限チェックが動作していません"
    
    agent.set_mp(30)  # 正常値
    assert agent.current_mp == 30, "MP設定が正しくありません"
    print("✅ MP設定と上限・下限チェック")
    
    # 攻撃力・防御力設定のテスト
    agent.set_attack(20)
    assert agent.attack == 20, "攻撃力設定が正しくありません"
    
    agent.set_attack(-5)  # 負の値
    assert agent.attack == 0, "攻撃力下限チェックが動作していません"
    
    agent.set_defense(15)
    assert agent.defense == 15, "防御力設定が正しくありません"
    
    agent.set_defense(-3)  # 負の値
    assert agent.defense == 0, "防御力下限チェックが動作していません"
    print("✅ 攻撃力・防御力設定")
    
    print("✅ AgentのRPG統計機能テスト完了\n")


def test_item_effect_application():
    """アイテム効果適用のテスト"""
    print("🧪 アイテム効果適用テスト")
    
    agent = Agent("test_agent", "テストエージェント")
    agent.set_hp(50)  # HPを半分に
    agent.set_mp(25)  # MPを半分に
    
    # 回復効果のテスト
    heal_effect = ItemEffect(hp_change=30, mp_change=20)
    agent.apply_item_effect(heal_effect)
    
    assert agent.current_hp == 80, "HP回復が正しく適用されていません"
    assert agent.current_mp == 45, "MP回復が正しく適用されていません"
    print("✅ 回復効果適用")
    
    # ステータス上昇効果のテスト
    buff_effect = ItemEffect(attack_change=5, defense_change=3)
    agent.apply_item_effect(buff_effect)
    
    assert agent.attack == 15, "攻撃力上昇が正しく適用されていません"
    assert agent.defense == 8, "防御力上昇が正しく適用されていません"
    print("✅ ステータス上昇効果適用")
    
    # 金銭・経験値効果のテスト
    money_effect = ItemEffect(money_change=100, experience_change=50)
    agent.apply_item_effect(money_effect)
    
    assert agent.money == 100, "所持金増加が正しく適用されていません"
    assert agent.experience_points == 50, "経験値増加が正しく適用されていません"
    print("✅ 金銭・経験値効果適用")
    
    # 上限を超える回復のテスト
    agent.set_hp(100)  # 満タンに
    agent.set_mp(50)   # 満タンに
    
    over_heal_effect = ItemEffect(hp_change=50, mp_change=30)
    agent.apply_item_effect(over_heal_effect)
    
    assert agent.current_hp == 100, "HP上限を超えて回復されました"
    assert agent.current_mp == 50, "MP上限を超えて回復されました"
    print("✅ 上限を超える回復の制限")
    
    print("✅ アイテム効果適用テスト完了\n")


def test_item_usage_action():
    """ItemUsage Actionのテスト"""
    print("🧪 ItemUsage Actionテスト")
    
    agent = Agent("test_agent", "テストエージェント")
    
    # アイテムを準備
    potion = ConsumableItem(
        item_id="test_potion",
        description="テスト用ポーション",
        effect=ItemEffect(hp_change=30)
    )
    agent.add_item(potion)
    agent.add_item(potion)  # 2個所持
    
    # 基本的なItemUsage
    usage = ItemUsage(
        description="テスト用ポーションを使用",
        item_id="test_potion",
        count=1
    )
    
    assert usage.is_valid(agent), "有効なアイテム使用がinvalidになりました"
    assert usage.get_required_item_count() == 1, "必要アイテム数が正しくありません"
    print("✅ 基本的なItemUsage")
    
    # 複数個使用のテスト
    multi_usage = ItemUsage(
        description="テスト用ポーションを2個使用",
        item_id="test_potion",
        count=2
    )
    
    assert multi_usage.is_valid(agent), "十分なアイテムがあるのにinvalidになりました"
    print("✅ 複数個使用（有効）")
    
    # 不足している場合のテスト
    over_usage = ItemUsage(
        description="テスト用ポーションを3個使用",
        item_id="test_potion",
        count=3
    )
    
    assert not over_usage.is_valid(agent), "不足しているアイテムがvalidになりました"
    print("✅ 複数個使用（不足）")
    
    # 存在しないアイテムのテスト
    fake_usage = ItemUsage(
        description="存在しないポーションを使用",
        item_id="fake_potion",
        count=1
    )
    
    assert not fake_usage.is_valid(agent), "存在しないアイテムがvalidになりました"
    print("✅ 存在しないアイテム")
    
    print("✅ ItemUsage Actionテスト完了\n")


def test_item_removal_safety():
    """アイテム削除の安全性テスト"""
    print("🧪 アイテム削除安全性テスト")
    
    agent = Agent("test_agent", "テストエージェント")
    
    # 同じアイテムを複数個追加
    potion = ConsumableItem(
        item_id="test_potion",
        description="テスト用ポーション",
        effect=ItemEffect(hp_change=30)
    )
    
    agent.add_item(potion)
    agent.add_item(potion)
    agent.add_item(potion)
    
    initial_count = agent.get_item_count("test_potion")
    assert initial_count == 3, "初期アイテム数が正しくありません"
    print(f"✅ 初期状態: {initial_count}個")
    
    # 1個削除
    removed = agent.remove_item_by_id("test_potion", 1)
    assert removed == 1, "削除個数が正しくありません"
    
    remaining_count = agent.get_item_count("test_potion")
    assert remaining_count == 2, "削除後のアイテム数が正しくありません"
    print(f"✅ 1個削除後: {remaining_count}個")
    
    # 2個削除
    removed = agent.remove_item_by_id("test_potion", 2)
    assert removed == 2, "削除個数が正しくありません"
    
    final_count = agent.get_item_count("test_potion")
    assert final_count == 0, "全削除後のアイテム数が正しくありません"
    print(f"✅ 2個削除後: {final_count}個")
    
    # 存在しないアイテムの削除
    removed = agent.remove_item_by_id("fake_potion", 1)
    assert removed == 0, "存在しないアイテムの削除で0以外が返されました"
    print("✅ 存在しないアイテム削除")
    
    print("✅ アイテム削除安全性テスト完了\n")


def test_world_item_usage_integration():
    """WorldクラスでのItemUsage統合テスト"""
    print("🧪 WorldクラスItemUsage統合テスト")
    
    world = World()
    agent = Agent("test_agent", "テストエージェント")
    agent.set_hp(50)  # HPを半分に
    world.add_agent(agent)
    
    # 消費可能アイテムを追加
    potion = ConsumableItem(
        item_id="heal_potion",
        description="回復ポーション",
        effect=ItemEffect(hp_change=30)
    )
    agent.add_item(potion)
    
    # ItemUsage実行
    usage = ItemUsage(
        description="回復ポーション使用",
        item_id="heal_potion"
    )
    
    world.execute_agent_item_usage("test_agent", usage)
    
    # 効果の確認
    assert agent.current_hp == 80, "HP回復が正しく適用されていません"
    assert agent.get_item_count("heal_potion") == 0, "アイテムが削除されていません"
    print("✅ World経由でのアイテム使用")
    
    # execute_actionでの統合テスト
    agent.add_item(potion)  # もう一度追加
    agent.set_hp(60)
    
    world.execute_action("test_agent", usage)
    
    assert agent.current_hp == 90, "execute_action経由での効果適用に失敗しました"
    assert agent.get_item_count("heal_potion") == 0, "execute_action経由でのアイテム削除に失敗しました"
    print("✅ execute_action経由でのアイテム使用")
    
    print("✅ WorldクラスItemUsage統合テスト完了\n")


def run_all_unit_tests():
    """全ての単体テストを実行"""
    print("🧪 消費可能アイテムシステム単体テスト開始")
    print("=" * 70)
    
    try:
        test_item_effect_creation()
        test_consumable_item_creation()
        test_agent_rpg_stats()
        test_item_effect_application()
        test_item_usage_action()
        test_item_removal_safety()
        test_world_item_usage_integration()
        
        print("=" * 70)
        print("🎉 全ての単体テストが成功しました！")
        print("✅ 消費可能アイテムシステムの個別機能が正しく実装されています")
        return True
        
    except AssertionError as e:
        print(f"❌ テスト失敗: {e}")
        return False
    except Exception as e:
        print(f"❌ エラー発生: {e}")
        return False


if __name__ == "__main__":
    run_all_unit_tests() 
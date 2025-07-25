#!/usr/bin/env python3
"""
家システムのデモンストレーション

このデモでは以下の家システムの機能を紹介します：
1. 家の作成と購入
2. 権限管理システム
3. 睡眠による体力回復
4. 日記システム
5. アイテム保管システム
6. 実際の使用シナリオ
"""

from src.systems.world import World
from src.models.agent import Agent
from src.models.item import Item
from src.models.action import WriteDiary, ReadDiary, Sleep, GrantHomePermission, StoreItem, RetrieveItem
from datetime import datetime, timedelta


def print_separator(title=""):
    """セクション区切り線を表示"""
    print("\n" + "="*80)
    if title:
        print(f" {title} ")
        print("="*80)


def print_agent_status(agent, home=None):
    """エージェントの状態を表示"""
    print(f"📊 {agent.name}の状態:")
    print(f"   HP: {agent.current_hp}/{agent.max_hp}")
    print(f"   MP: {agent.current_mp}/{agent.max_mp}")
    print(f"   所持金: {agent.money}円")
    print(f"   所持アイテム: {len(agent.items)}個")
    if agent.items:
        for item in agent.items[:3]:  # 最初の3個だけ表示
            print(f"     - {item.item_id}")
        if len(agent.items) > 3:
            print(f"     ... 他{len(agent.items) - 3}個")
    
    if home:
        permission = home.get_permission(agent.agent_id)
        print(f"   家への権限: {permission.value}")


def demo_home_creation_and_setup():
    """家の作成とセットアップのデモ"""
    print_separator("1. 家の作成とセットアップ")
    
    world = World()
    
    # エージェントを作成
    alice = Agent("alice", "アリス")
    alice.money = 2000  # 初期資金
    world.add_agent(alice)
    
    bob = Agent("bob", "ボブ")
    bob.money = 1500
    world.add_agent(bob)
    
    print("🏘️ 住宅地にやってきたアリスとボブ")
    print(f"アリスの所持金: {alice.money}円")
    print(f"ボブの所持金: {bob.money}円")
    
    # アリスの家を作成
    print("\n🏠 アリスが家を購入します...")
    alice_home = world.create_home(
        "alice_home", 
        "アリスのコテージ", 
        "花に囲まれた美しい小さなコテージ", 
        "alice"
    )
    
    print(f"✅ 家の購入完了!")
    print(f"   家の名前: {alice_home.name}")
    print(f"   価格: {alice_home.get_price()}円")
    print(f"   部屋数: {len(alice_home.get_child_spots())}部屋")
    
    # 寝室の確認
    bedroom_id = f"{alice_home.spot_id}_bedroom"
    bedroom = world.get_spot(bedroom_id)
    print(f"   自動作成された寝室: {bedroom.name}")
    
    interactables = bedroom.get_all_interactables()
    print(f"   設置された家具:")
    for interactable in interactables:
        print(f"     - {interactable.name}")
    
    return world, alice, bob, alice_home, bedroom


def demo_permission_system(world, alice, bob, alice_home, bedroom):
    """権限システムのデモ"""
    print_separator("2. 権限管理システム")
    
    print("🔐 家の権限システムをテストします")
    
    # 初期状態の表示
    print("\n初期の権限状態:")
    print_agent_status(alice, alice_home)
    print_agent_status(bob, alice_home)
    
    # ボブが家に入ろうとする（権限なし）
    print(f"\n🚪 ボブがアリスの家に入ろうとしています...")
    can_enter = alice_home.can_enter("bob")
    print(f"入室可否: {'可能' if can_enter else '不可能'}")
    
    if not can_enter:
        print("❌ ボブは権限がないため入れません")
    
    # アリスがボブに訪問者権限を付与
    print(f"\n🤝 アリスがボブに訪問者権限を付与します...")
    alice.set_current_spot_id(alice_home.spot_id)
    
    permission_action = GrantHomePermission(
        description="ボブに訪問者権限を付与",
        target_agent_id="bob",
        permission_level="visitor"
    )
    
    result = world.execute_agent_grant_home_permission("alice", permission_action)
    print(f"✅ {result['message']}")
    
    # 権限付与後の確認
    print(f"\n権限付与後:")
    print_agent_status(bob, alice_home)
    
    can_enter = alice_home.can_enter("bob")
    print(f"ボブの入室: {'可能' if can_enter else '不可能'}")
    
    return world, alice, bob, alice_home, bedroom


def demo_daily_life_scenario(world, alice, bob, alice_home, bedroom):
    """日常生活シナリオのデモ"""
    print_separator("3. 日常生活シナリオ")
    
    print("🌅 アリスの一日が始まります...")
    
    # アリスを疲れた状態にする
    alice.current_hp = 40
    alice.current_mp = 20
    print(f"\nアリスは昨日の冒険で疲れています...")
    print_agent_status(alice)
    
    # 寝室に移動
    alice.set_current_spot_id(bedroom.spot_id)
    print(f"\n🛏️ アリスは自分の寝室に向かいます...")
    
    # 睡眠で回復
    sleep_action = Sleep(description="ベッドでゆっくり休む", duration=8)
    result = world.execute_agent_sleep("alice", sleep_action)
    print(f"✅ {result['message']}")
    
    print(f"\n睡眠後のアリス:")
    print_agent_status(alice)
    
    # 日記を書く
    print(f"\n📝 アリスが今日の出来事を日記に書きます...")
    today = datetime.now().strftime("%Y-%m-%d")
    diary_content = "今日は新しい家での最初の朝。ボブに家の見学を許可した。とても良い一日だった。"
    
    write_action = WriteDiary(
        description="日記を書く",
        content=diary_content,
        date=today
    )
    
    result = world.execute_agent_write_diary("alice", write_action)
    print(f"✅ {result['message']}")
    
    # ボブが訪問
    print(f"\n🚪 ボブがアリスの家を訪問します...")
    bob.set_current_spot_id(bedroom.spot_id)
    
    # ボブが日記を読む（訪問者権限で可能）
    read_action = ReadDiary(description="日記を読む")
    result = world.execute_agent_read_diary("bob", read_action)
    print(f"📖 ボブの日記読取: {result['message']}")
    
    if result['success'] and result['entries']:
        print("   読んだ内容:")
        for entry in result['entries']:
            print(f"     [{entry['date']}] {entry['content']}")
    
    # ボブが日記を書こうとする（権限なし）
    bob_diary = WriteDiary(
        description="日記を書く",
        content="アリスの家はとても素敵だ",
        date=today
    )
    result = world.execute_agent_write_diary("bob", bob_diary)
    print(f"❌ ボブの日記記入試行: {result['message']}")
    
    return world, alice, bob, alice_home, bedroom


def demo_item_storage_system(world, alice, bob, alice_home, bedroom):
    """アイテム保管システムのデモ"""
    print_separator("4. アイテム保管システム")
    
    print("📦 アリスが冒険で手に入れたアイテムを整理します...")
    
    # アイテムを作成
    items = [
        Item("magic_sword", "魔法の剣 - 冒険で手に入れた強力な剣"),
        Item("ancient_scroll", "古代の巻物 - 謎の文字が書かれている"),
        Item("healing_potion", "回復薬 - 体力を回復する"),
        Item("rare_gem", "希少な宝石 - とても価値がある"),
        Item("travel_cloak", "旅人のマント - 普段使いには重い")
    ]
    
    for item in items:
        alice.add_item(item)
    
    print(f"\n冒険から帰ったアリスの荷物:")
    print_agent_status(alice)
    
    # アリスを寝室に移動
    alice.set_current_spot_id(bedroom.spot_id)
    
    # 重いアイテムや装飾品を家に保管
    items_to_store = ["magic_sword", "ancient_scroll", "rare_gem", "travel_cloak"]
    
    print(f"\n🏠 家に保管するアイテム:")
    for item_id in items_to_store:
        print(f"   - {item_id}")
    
    stored_count = 0
    for item_id in items_to_store:
        store_action = StoreItem(description=f"{item_id}を保管", item_id=item_id)
        result = world.execute_agent_store_item("alice", store_action)
        if result['success']:
            stored_count += 1
            print(f"✅ {item_id}を保管しました")
    
    print(f"\n保管完了! {stored_count}個のアイテムを家に置きました")
    print_agent_status(alice)
    
    stored_items = alice_home.get_stored_items("alice")
    print(f"\n🏠 家に保管されているアイテム: {len(stored_items)}個")
    for item in stored_items:
        print(f"   - {item.item_id}")
    
    # 必要なアイテムを取り出す
    print(f"\n⚔️ 明日の冒険のために魔法の剣を取り出します...")
    retrieve_action = RetrieveItem(description="魔法の剣を取得", item_id="magic_sword")
    result = world.execute_agent_retrieve_item("alice", retrieve_action)
    print(f"✅ {result['message']}")
    
    print(f"\n最終的なアリスの状態:")
    print_agent_status(alice)
    
    return world, alice, bob, alice_home, bedroom


def demo_extended_diary_system(world, alice, bob, alice_home, bedroom):
    """拡張日記システムのデモ"""
    print_separator("5. 拡張日記システム")
    
    print("📚 アリスが数日間日記を書き続けます...")
    
    alice.set_current_spot_id(bedroom.spot_id)
    
    # 複数日の日記エントリ
    diary_entries = [
        ("2024-01-01", "新年の始まり。今年は新しい家で過ごす最初の年だ。"),
        ("2024-01-02", "ボブが遊びに来た。家の権限システムがうまく動いている。"),
        ("2024-01-03", "冒険から帰還。たくさんのアイテムを手に入れた。"),
        ("2024-01-04", "アイテムを整理して家に保管した。とても便利だ。"),
        ("2024-01-05", "今日は静かな一日。日記を読み返すのも楽しい。")
    ]
    
    for date, content in diary_entries:
        write_action = WriteDiary(
            description="日記を書く",
            content=content,
            date=date
        )
        result = world.execute_agent_write_diary("alice", write_action)
        if result['success']:
            print(f"✅ {date}: 日記を記入")
    
    # 全ての日記を読む
    print(f"\n📖 アリスがこれまでの日記を読み返します...")
    read_action = ReadDiary(description="日記を読む")
    result = world.execute_agent_read_diary("alice", read_action)
    
    if result['success']:
        print(f"✅ {result['message']}")
        print(f"\n日記の内容:")
        for entry in result['entries']:
            print(f"   [{entry['date']}] {entry['content']}")
    
    # 特定の日付の日記を読む
    print(f"\n🔍 特定の日付（2024-01-03）の日記を読みます...")
    specific_read = ReadDiary(description="特定日の日記を読む", target_date="2024-01-03")
    result = world.execute_agent_read_diary("alice", specific_read)
    
    if result['success'] and result['entries']:
        print(f"✅ {result['message']}")
        for entry in result['entries']:
            print(f"   [{entry['date']}] {entry['content']}")
    
    return world, alice, bob, alice_home, bedroom


def demo_real_world_scenario():
    """リアルワールドシナリオのデモ"""
    print_separator("6. リアルワールドシナリオ - 冒険者の生活")
    
    print("🗺️ RPGワールドでの冒険者の典型的な一日...")
    
    world = World()
    
    # 冒険者アリス
    alice = Agent("alice", "冒険者アリス")
    alice.money = 5000
    alice.current_hp = 60  # 冒険で疲労
    alice.current_mp = 30
    world.add_agent(alice)
    
    # 商人ボブ
    bob = Agent("bob", "商人ボブ")
    bob.money = 3000
    world.add_agent(bob)
    
    # 街のスポットを作成
    from src.models.spot import Spot
    town_square = Spot("town_square", "街の中心部", "賑やかな街の中心部")
    world.add_spot(town_square)
    
    # アリスの家を作成
    alice_home = world.create_home(
        "alice_cottage",
        "冒険者の家",
        "街の郊外にある冒険者の家。装備や戦利品の保管に適している。",
        "alice"
    )
    bedroom = world.get_spot(f"{alice_home.spot_id}_bedroom")
    
    print(f"🏠 アリスが冒険者向けの家を構えました")
    print(f"   家の価格: {alice_home.get_price()}円")
    
    # 冒険の戦利品
    loot_items = [
        Item("dragon_scale", "ドラゴンの鱗 - 非常に価値がある"),
        Item("enchanted_armor", "魔法の鎧 - 防御力が高い"),
        Item("ancient_tome", "古代の書物 - 魔法の知識が記されている"),
        Item("gold_coins", "金貨の袋 - 重くて持ち歩くには不便"),
        Item("magic_crystal", "魔法のクリスタル - エネルギーを蓄えている")
    ]
    
    for item in loot_items:
        alice.add_item(item)
    
    print(f"\n⚔️ 長い冒険から帰還したアリス...")
    print_agent_status(alice)
    
    # 家に帰って休む
    alice.set_current_spot_id(bedroom.spot_id)
    print(f"\n🏠 アリスが家に帰ります...")
    
    # 睡眠で体力回復
    sleep_action = Sleep(description="冒険の疲れを癒す", duration=10)
    result = world.execute_agent_sleep("alice", sleep_action)
    print(f"✅ {result['message']}")
    
    # 今日の冒険を日記に記録
    today = datetime.now().strftime("%Y-%m-%d")
    adventure_log = "古代遺跡の探索完了。ドラゴンとの戦闘は厳しかったが、貴重な戦利品を多数入手。明日は街で売却予定。"
    
    write_action = WriteDiary(
        description="冒険日誌を記録",
        content=adventure_log,
        date=today
    )
    result = world.execute_agent_write_diary("alice", write_action)
    print(f"📝 {result['message']}")
    
    # 価値のあるアイテムを安全に保管
    valuable_items = ["dragon_scale", "ancient_tome", "magic_crystal"]
    
    print(f"\n💎 貴重なアイテムを家の金庫に保管...")
    for item_id in valuable_items:
        store_action = StoreItem(description=f"{item_id}を保管", item_id=item_id)
        result = world.execute_agent_store_item("alice", store_action)
        if result['success']:
            print(f"✅ {item_id}を安全に保管")
    
    # 商人ボブに訪問権限を付与（取引のため）
    print(f"\n🤝 取引のため商人ボブに訪問権限を付与...")
    permission_action = GrantHomePermission(
        description="商人ボブに訪問権限を付与",
        target_agent_id="bob",
        permission_level="visitor"
    )
    result = world.execute_agent_grant_home_permission("alice", permission_action)
    print(f"✅ {result['message']}")
    
    # ボブが訪問して在庫確認
    bob.set_current_spot_id(bedroom.spot_id)
    stored_items = alice_home.get_stored_items("bob")  # 訪問者権限で閲覧可能
    print(f"\n👁️ ボブが在庫を確認: {len(stored_items)}個のアイテムを確認")
    
    print(f"\n📊 最終状態:")
    print_agent_status(alice, alice_home)
    print_agent_status(bob, alice_home)
    
    stored_items = alice_home.get_stored_items("alice")
    print(f"\n🏠 家に保管されたアイテム: {len(stored_items)}個")
    for item in stored_items:
        print(f"   - {item.item_id}")


def main():
    """メインデモ実行"""
    print("🏠 家システム 総合デモンストレーション")
    print("=" * 80)
    print("本デモでは、RPGワールドでの家システムの")
    print("実用的な使用例を段階的に紹介します。")
    
    try:
        # 基本機能デモ
        world, alice, bob, alice_home, bedroom = demo_home_creation_and_setup()
        world, alice, bob, alice_home, bedroom = demo_permission_system(world, alice, bob, alice_home, bedroom)
        world, alice, bob, alice_home, bedroom = demo_daily_life_scenario(world, alice, bob, alice_home, bedroom)
        world, alice, bob, alice_home, bedroom = demo_item_storage_system(world, alice, bob, alice_home, bedroom)
        world, alice, bob, alice_home, bedroom = demo_extended_diary_system(world, alice, bob, alice_home, bedroom)
        
        # リアルワールドシナリオ
        demo_real_world_scenario()
        
        print_separator("✨ 家システムデモ完了")
        print("家システムにより、以下の機能が実現されました：")
        print("🏠 個人の家の所有と管理")
        print("🔐 細かい権限制御システム")
        print("😴 睡眠による体力回復")
        print("📝 プライベートな日記システム")
        print("📦 安全なアイテム保管")
        print("💰 部屋数に基づく価格設定")
        print("\nこれにより、RPGワールドでの生活感と")
        print("プライベート空間が実現されます！")
        
    except Exception as e:
        print(f"\n❌ デモ中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 
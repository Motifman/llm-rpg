#!/usr/bin/env python3
"""
家システムのテスト

このテストファイルでは以下の機能をテストします：
1. 家の作成と基本機能
2. 権限システム（所有者、訪問者、拒否）
3. ベッドでの睡眠機能
4. 机での日記機能
5. アイテム保管機能
6. エラーハンドリング
"""

from src_old.systems.world import World
from src_old.models.agent import Agent
from src_old.models.item import Item
from src_old.models.home import Home, HomePermission
from src_old.models.home_interactables import Bed, Desk
from src_old.models.action import WriteDiary, ReadDiary, Sleep, GrantHomePermission, StoreItem, RetrieveItem
from datetime import datetime


def test_home_creation():
    """家の作成とセットアップのテスト"""
    print("=== 家の作成テスト ===")
    
    world = World()
    
    # エージェント作成
    alice = Agent("alice", "アリス")
    world.add_agent(alice)
    
    # 家を作成
    home = world.create_home("alice_home", "アリスの家", "温かみのある小さな家", "alice")
    
    print(f"✅ 家作成成功: {home.name}")
    print(f"   所有者: {home.get_owner_id()}")
    print(f"   価格: {home.get_price()}円")
    print(f"   部屋数: {len(home.get_child_spots())}部屋")
    
    # 自動作成された寝室の確認
    bedroom_id = f"{home.spot_id}_bedroom"
    bedroom = world.get_spot(bedroom_id)
    print(f"✅ 寝室自動作成: {bedroom.name}")
    
    # ベッドと机の確認
    interactables = bedroom.get_all_interactables()
    print(f"✅ 家具設置確認: {len(interactables)}個の家具")
    for interactable in interactables:
        print(f"   - {interactable.name}: {type(interactable).__name__}")
    
    # 基本的なアサーションを追加
    assert home is not None
    assert home.get_owner_id() == "alice"
    assert bedroom is not None
    assert len(interactables) > 0


def test_permission_system():
    """権限システムのテスト"""
    print("\n=== 権限システムテスト ===")
    
    # 新しいワールドをセットアップ
    world = World()
    alice = Agent("alice", "アリス")
    world.add_agent(alice)
    home = world.create_home("alice_home", "アリスの家", "温かみのある小さな家", "alice")
    bedroom_id = f"{home.spot_id}_bedroom"
    bedroom = world.get_spot(bedroom_id)
    
    # 別のエージェントを作成
    bob = Agent("bob", "ボブ")
    charlie = Agent("charlie", "チャーリー")
    world.add_agent(bob)
    world.add_agent(charlie)
    
    # 初期権限の確認
    print("初期権限状態:")
    print(f"   アリス: {home.get_permission('alice').value}")
    print(f"   ボブ: {home.get_permission('bob').value}")
    print(f"   チャーリー: {home.get_permission('charlie').value}")
    
    # アリスがボブに訪問者権限を付与
    alice.set_current_spot_id(home.spot_id)
    permission_action = GrantHomePermission(
        description="ボブに訪問者権限を付与",
        target_agent_id="bob",
        permission_level="visitor"
    )
    result = world.execute_agent_grant_home_permission("alice", permission_action)
    print(f"✅ 権限付与結果: {result['message']}")
    
    # 更新後の権限確認
    print("権限付与後:")
    print(f"   ボブ: {home.get_permission('bob').value}")
    
    # 入室可否のテスト
    print("\n入室可否テスト:")
    print(f"   アリス: {'入室可能' if home.can_enter('alice') else '入室不可'}")
    print(f"   ボブ: {'入室可能' if home.can_enter('bob') else '入室不可'}")
    print(f"   チャーリー: {'入室可能' if home.can_enter('charlie') else '入室不可'}")
    
    # アサーションを追加
    assert home.can_enter('alice'), "所有者が入室できません"
    assert home.can_enter('bob'), "権限を付与されたボブが入室できません"
    assert not home.can_enter('charlie'), "権限のないチャーリーが入室できてしまいます"


def test_sleep_system():
    """睡眠システムのテスト"""
    print("\n=== 睡眠システムテスト ===")
    
    # 新しいワールドをセットアップ
    world = World()
    alice = Agent("alice", "アリス")
    bob = Agent("bob", "ボブ")
    world.add_agent(alice)
    world.add_agent(bob)
    home = world.create_home("alice_home", "アリスの家", "温かみのある小さな家", "alice")
    bedroom_id = f"{home.spot_id}_bedroom"
    bedroom = world.get_spot(bedroom_id)
    
    # ボブに訪問者権限を付与
    alice.set_current_spot_id(home.spot_id)
    permission_action = GrantHomePermission(
        description="ボブに訪問者権限を付与",
        target_agent_id="bob",
        permission_level="visitor"
    )
    world.execute_agent_grant_home_permission("alice", permission_action)
    
    # アリスの体力を減らす
    alice.current_hp = 30
    alice.current_mp = 10
    print(f"睡眠前のアリス - HP: {alice.current_hp}/{alice.max_hp}, MP: {alice.current_mp}/{alice.max_mp}")
    
    # アリスを寝室に移動
    alice.set_current_spot_id(bedroom.spot_id)
    
    # 睡眠実行
    sleep_action = Sleep(description="ベッドで休む", duration=8)
    result = world.execute_agent_sleep("alice", sleep_action)
    print(f"✅ 睡眠結果: {result['message']}")
    
    if result['success']:
        print(f"睡眠後のアリス - HP: {alice.current_hp}/{alice.max_hp}, MP: {alice.current_mp}/{alice.max_mp}")
    
    # ボブが睡眠を試行（権限なし）
    bob.set_current_spot_id(bedroom.spot_id)
    result = world.execute_agent_sleep("bob", sleep_action)
    print(f"❌ ボブの睡眠試行: {result['message']}")
    
    # アサーションを追加
    assert alice.current_hp > 30, "睡眠でHPが回復されていません"


def test_diary_system():
    """日記システムのテスト"""
    print("\n=== 日記システムテスト ===")
    
    # 新しいワールドをセットアップ
    world = World()
    alice = Agent("alice", "アリス")
    bob = Agent("bob", "ボブ")
    world.add_agent(alice)
    world.add_agent(bob)
    home = world.create_home("alice_home", "アリスの家", "温かみのある小さな家", "alice")
    bedroom_id = f"{home.spot_id}_bedroom"
    bedroom = world.get_spot(bedroom_id)
    
    # ボブに訪問者権限を付与
    alice.set_current_spot_id(home.spot_id)
    permission_action = GrantHomePermission(
        description="ボブに訪問者権限を付与",
        target_agent_id="bob",
        permission_level="visitor"
    )
    world.execute_agent_grant_home_permission("alice", permission_action)
    
    # 日記を書く
    today = datetime.now().strftime("%Y-%m-%d")
    diary_content = "今日は新しい家に引っ越した。とても快適で気に入っている。"
    
    write_action = WriteDiary(
        description="日記を書く",
        content=diary_content,
        date=today
    )
    
    alice.set_current_spot_id(bedroom.spot_id)
    result = world.execute_agent_write_diary("alice", write_action)
    print(f"✅ 日記記入結果: {result['message']}")
    
    # 日記を読む
    read_action = ReadDiary(description="日記を読む")
    result = world.execute_agent_read_diary("alice", read_action)
    print(f"✅ 日記読取結果: {result['message']}")
    
    if result['success'] and result['entries']:
        for entry in result['entries']:
            print(f"   [{entry['date']}] {entry['content']}")
    
    # ボブが日記を読む（訪問者権限で可能）
    bob.set_current_spot_id(bedroom.spot_id)
    result = world.execute_agent_read_diary("bob", read_action)
    print(f"✅ ボブの日記読取: {result['message']}")
    
    # ボブが日記を書こうとする（権限なし）
    result = world.execute_agent_write_diary("bob", write_action)
    print(f"❌ ボブの日記記入試行: {result['message']}")
    
    # アサーションを追加
    alice_result = world.execute_agent_read_diary("alice", read_action)
    assert alice_result['success'], "アリスが日記を読めません"
    assert len(alice_result['entries']) > 0, "日記エントリが保存されていません"


def test_item_storage_system():
    """アイテム保管システムのテスト"""
    print("\n=== アイテム保管システムテスト ===")
    
    # 新しいワールドをセットアップ
    world = World()
    alice = Agent("alice", "アリス")
    bob = Agent("bob", "ボブ")
    world.add_agent(alice)
    world.add_agent(bob)
    home = world.create_home("alice_home", "アリスの家", "温かみのある小さな家", "alice")
    bedroom_id = f"{home.spot_id}_bedroom"
    bedroom = world.get_spot(bedroom_id)
    
    # ボブに訪問者権限を付与
    alice.set_current_spot_id(home.spot_id)
    permission_action = GrantHomePermission(
        description="ボブに訪問者権限を付与",
        target_agent_id="bob",
        permission_level="visitor"
    )
    world.execute_agent_grant_home_permission("alice", permission_action)
    
    # アイテムを作成してアリスに追加
    sword = Item("iron_sword", "鉄の剣 - よく切れる剣")
    potion = Item("health_potion", "回復薬 - HPを回復する")
    
    alice.add_item(sword)
    alice.add_item(potion)
    
    print(f"保管前のアリスの所持品: {len(alice.items)}個")
    for item in alice.items:
        print(f"   - {item.item_id}")
    
    initial_item_count = len(alice.items)
    
    # アイテムを保管
    alice.set_current_spot_id(bedroom.spot_id)
    store_action = StoreItem(description="剣を保管", item_id="iron_sword")
    result = world.execute_agent_store_item("alice", store_action)
    print(f"✅ アイテム保管結果: {result['message']}")
    
    print(f"保管後のアリスの所持品: {len(alice.items)}個")
    stored_items = home.get_stored_items("alice")
    print(f"家に保管されたアイテム: {len(stored_items)}個")
    for item in stored_items:
        print(f"   - {item.item_id}")
    
    # アイテムを取得
    retrieve_action = RetrieveItem(description="剣を取得", item_id="iron_sword")
    result = world.execute_agent_retrieve_item("alice", retrieve_action)
    print(f"✅ アイテム取得結果: {result['message']}")
    
    print(f"取得後のアリスの所持品: {len(alice.items)}個")
    
    # ボブがアイテム保管を試行（権限なし）
    bob.set_current_spot_id(bedroom.spot_id)
    result = world.execute_agent_store_item("bob", store_action)
    print(f"❌ ボブの保管試行: {result['message']}")
    
    # アサーションを追加
    assert len(alice.items) == initial_item_count, "アイテムの保管・取得で数が変わりました"
    assert alice.has_item("iron_sword"), "アイテムが正常に取得されていません"


def test_error_handling():
    """エラーハンドリングのテスト"""
    print("\n=== エラーハンドリングテスト ===")
    
    # 新しいワールドをセットアップ
    world = World()
    alice = Agent("alice", "アリス")
    world.add_agent(alice)
    home = world.create_home("alice_home", "アリスの家", "温かみのある小さな家", "alice")
    bedroom_id = f"{home.spot_id}_bedroom"
    bedroom = world.get_spot(bedroom_id)
    
    # 家の外で日記を書こうとする
    town_square = world.spots.get("town_square")
    if not town_square:
        from src_old.models.spot import Spot
        town_square = Spot("town_square", "街の中心部", "賑やかな街の中心部")
        world.add_spot(town_square)
    
    alice.set_current_spot_id("town_square")
    
    write_action = WriteDiary(
        description="日記を書く",
        content="街の中心部にいます",
        date=datetime.now().strftime("%Y-%m-%d")
    )
    
    result = world.execute_agent_write_diary("alice", write_action)
    print(f"❌ 家の外での日記記入: {result['message']}")
    
    # 存在しないアイテムを保管しようとする
    alice.set_current_spot_id(bedroom.spot_id)
    store_action = StoreItem(description="存在しないアイテムを保管", item_id="nonexistent_item")
    result = world.execute_agent_store_item("alice", store_action)
    print(f"❌ 存在しないアイテム保管: {result['message']}")
    
    # 存在しないエージェントに権限を付与しようとする
    permission_action = GrantHomePermission(
        description="存在しないエージェントに権限付与",
        target_agent_id="nonexistent_agent",
        permission_level="visitor"
    )
    result = world.execute_agent_grant_home_permission("alice", permission_action)
    print(f"❌ 存在しないエージェントへの権限付与: {result['message']}")


def test_home_pricing():
    """家の価格システムのテスト"""
    print("\n=== 家の価格システムテスト ===")
    
    world = World()
    alice = Agent("alice", "アリス")
    world.add_agent(alice)
    
    # 基本的な家（1部屋）
    basic_home = world.create_home("basic_home", "基本の家", "シンプルな家", "alice")
    print(f"基本的な家の価格: {basic_home.get_price()}円")
    
    # 部屋を追加
    living_room = world.spots["basic_home_bedroom"]  # 寝室を取得
    from src_old.models.spot import Spot
    kitchen = Spot("basic_home_kitchen", "キッチン", "調理ができるキッチン", "basic_home")
    world.add_spot(kitchen)
    basic_home.add_child_spot("basic_home_kitchen")
    
    # 価格を更新
    basic_home.update_price()
    print(f"部屋追加後の価格: {basic_home.get_price()}円")


def main():
    """メインテスト実行"""
    print("🏠 家システム 総合テスト開始")
    print("=" * 50)
    
    try:
        # 基本機能テスト
        test_home_creation()
        test_permission_system()
        test_sleep_system()
        test_diary_system()
        test_item_storage_system()
        test_error_handling()
        test_home_pricing()
        
        print("\n🎉 すべてのテストが完了しました！")
        print("家システムが正常に動作しています。")
        
    except Exception as e:
        print(f"\n❌ テスト中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 
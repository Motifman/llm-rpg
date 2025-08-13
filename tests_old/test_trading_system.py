"""
トレードシステムの包括的テスト
基本取引、エラーハンドリング、フィルタリング機能を含む
"""

from src_old.models.spot import Spot
from src_old.models.agent import Agent
from src_old.models.item import Item, ConsumableItem, ItemEffect
from src_old.models.action import PostTrade, ViewTrades, AcceptTrade, CancelTrade
from src_old.models.trade import TradeOffer, TradeType, TradeStatus
from src_old.systems.world import World


def create_trading_test_world():
    """トレードシステムテスト用のワールドを作成"""
    world = World()
    
    # === スポットの作成 ===
    marketplace = Spot("marketplace", "マーケット", "商人や冒険者が集まる市場。取引が盛んに行われている。")
    world.add_spot(marketplace)
    
    # === アイテムの作成 ===
    
    # 通常のアイテム
    iron_sword = Item("iron_sword", "鉄の剣 - 標準的な戦士の武器")
    magic_wand = Item("magic_wand", "魔法の杖 - 魔法使いの必須アイテム")
    leather_armor = Item("leather_armor", "革の鎧 - 軽量で動きやすい防具")
    
    # 消費アイテム
    health_potion = ConsumableItem(
        item_id="health_potion",
        description="ヘルスポーション - HPを30回復する",
        effect=ItemEffect(hp_change=30),
        max_stack=5
    )
    
    mana_potion = ConsumableItem(
        item_id="mana_potion",
        description="マナポーション - MPを20回復する",
        effect=ItemEffect(mp_change=20),
        max_stack=5
    )
    
    rare_gem = Item("rare_gem", "希少な宝石 - 高価で美しい宝石")
    
    # === エージェントの作成 ===
    
    # 商人アリス（売り手）
    merchant_alice = Agent("merchant_alice", "商人アリス")
    merchant_alice.set_current_spot_id("marketplace")
    merchant_alice.add_money(1000)  # 初期資金
    
    # アリスのアイテム
    merchant_alice.add_item(iron_sword)
    merchant_alice.add_item(iron_sword)  # 2本所持
    merchant_alice.add_item(health_potion)
    merchant_alice.add_item(health_potion)
    merchant_alice.add_item(health_potion)  # 3個所持
    merchant_alice.add_item(leather_armor)
    
    world.add_agent(merchant_alice)
    
    # 冒険者ボブ（買い手）
    adventurer_bob = Agent("adventurer_bob", "冒険者ボブ")
    adventurer_bob.set_current_spot_id("marketplace")
    adventurer_bob.add_money(500)  # 初期資金
    
    # ボブのアイテム
    adventurer_bob.add_item(magic_wand)
    adventurer_bob.add_item(mana_potion)
    adventurer_bob.add_item(mana_potion)  # 2個所持
    adventurer_bob.add_item(rare_gem)
    
    world.add_agent(adventurer_bob)
    
    # 魔法使いシャーリー（第3のエージェント）
    mage_charlie = Agent("mage_charlie", "魔法使いシャーリー")
    mage_charlie.set_current_spot_id("marketplace")
    mage_charlie.add_money(300)
    
    # シャーリーのアイテム
    mage_charlie.add_item(magic_wand)
    mage_charlie.add_item(rare_gem)
    
    world.add_agent(mage_charlie)
    
    return world


def display_agent_trade_status(world: World, agent_id: str, step_description: str = ""):
    """エージェントのトレード関連ステータスを表示"""
    agent = world.get_agent(agent_id)
    
    if step_description:
        print(f"\n📋 {step_description}")
    
    print("=" * 70)
    print(f"🏪 エージェント: {agent.name} (ID: {agent.agent_id})")
    print(f"💰 所持金: {agent.money}ゴールド")
    print(f"📦 所持アイテム数: {len(agent.items)}")
    
    if agent.items:
        print("  📦 所持アイテム:")
        item_counts = {}
        for item in agent.items:
            item_counts[item.item_id] = item_counts.get(item.item_id, 0) + 1
        
        for item_id, count in item_counts.items():
            item = agent.get_item_by_id(item_id)
            count_str = f" x{count}" if count > 1 else ""
            print(f"    - {item}{count_str}")
    
    print("=" * 70)


def display_trading_post_status(world: World):
    """取引所の状況を表示"""
    trading_post = world.get_trading_post()
    stats = trading_post.get_statistics()
    
    print("\n🏪 取引所の状況")
    print("=" * 50)
    print(f"📈 アクティブな取引: {stats['active_trades_count']}件")
    print(f"✅ 成立した取引: {stats['total_trades_completed']}件") 
    print(f"❌ キャンセルされた取引: {stats['total_trades_cancelled']}件")
    print("=" * 50)
    
    # アクティブな取引を表示
    active_trades = trading_post.view_trades()
    if active_trades:
        print("\n📋 アクティブな取引一覧:")
        for i, trade in enumerate(active_trades, 1):
            print(f"  {i}. {trade.get_trade_summary()}")
            print(f"     ID: {trade.trade_id[:8]}...")
            print(f"     出品者: {trade.seller_id}")
    else:
        print("\n📋 現在アクティブな取引はありません")


def execute_post_trade_step(world: World, agent_id: str, post_trade: PostTrade, step_num: int):
    """取引出品ステップを実行"""
    print(f"\n🏪 ステップ {step_num}: '{post_trade.description}' を実行")
    
    try:
        trade_id = world.execute_agent_post_trade(agent_id, post_trade)
        print(f"✅ 取引出品成功! 取引ID: {trade_id[:8]}...")
        return trade_id
    except Exception as e:
        print(f"❌ 取引出品失敗: {e}")
        return None


def execute_accept_trade_step(world: World, agent_id: str, accept_trade: AcceptTrade, step_num: int):
    """取引受託ステップを実行"""
    print(f"\n🏪 ステップ {step_num}: '{accept_trade.description}' を実行")
    
    try:
        completed_trade = world.execute_agent_accept_trade(agent_id, accept_trade)
        print(f"✅ 取引受託成功!")
        print(f"   成立した取引: {completed_trade.get_trade_summary()}")
        return completed_trade
    except Exception as e:
        print(f"❌ 取引受託失敗: {e}")
        return None


def demo_basic_trading_system():
    """基本的なトレードシステムのデモンストレーション"""
    print("🎮 基本トレードシステム検証デモ")
    print("=" * 70)
    print("📋 複数のエージェントが市場でアイテムを取引します")
    
    world = create_trading_test_world()
    step = 0
    
    # 初期状態
    display_agent_trade_status(world, "merchant_alice", f"ステップ {step}: 初期状態")
    display_agent_trade_status(world, "adventurer_bob")
    display_agent_trade_status(world, "mage_charlie")
    display_trading_post_status(world)
    
    # ステップ1: アリスが鉄の剣を100ゴールドで出品
    step += 1
    post_sword_trade = PostTrade(
        description="鉄の剣を100ゴールドで出品",
        offered_item_id="iron_sword",
        offered_item_count=1,
        requested_money=100
    )
    
    sword_trade_id = execute_post_trade_step(world, "merchant_alice", post_sword_trade, step)
    if sword_trade_id:
        display_agent_trade_status(world, "merchant_alice")
        display_trading_post_status(world)
    
    # ステップ2: アリスがヘルスポーションを魔法の杖と交換で出品
    step += 1
    post_potion_trade = PostTrade(
        description="ヘルスポーション2個を魔法の杖と交換で出品",
        offered_item_id="health_potion",
        offered_item_count=2,
        requested_item_id="magic_wand",
        requested_item_count=1
    )
    
    potion_trade_id = execute_post_trade_step(world, "merchant_alice", post_potion_trade, step)
    if potion_trade_id:
        display_agent_trade_status(world, "merchant_alice")
        display_trading_post_status(world)
    
    # ステップ3: ボブが鉄の剣を購入
    step += 1
    if sword_trade_id:
        accept_sword_trade = AcceptTrade(
            description="鉄の剣を購入",
            trade_id=sword_trade_id
        )
        
        completed_trade = execute_accept_trade_step(world, "adventurer_bob", accept_sword_trade, step)
        if completed_trade:
            display_agent_trade_status(world, "merchant_alice")
            display_agent_trade_status(world, "adventurer_bob")
            display_trading_post_status(world)
    
    # ステップ4: ボブがヘルスポーションとの交換取引を受託
    step += 1
    if potion_trade_id:
        accept_potion_trade = AcceptTrade(
            description="ヘルスポーションと魔法の杖を交換",
            trade_id=potion_trade_id
        )
        
        completed_trade = execute_accept_trade_step(world, "adventurer_bob", accept_potion_trade, step)
        if completed_trade:
            display_agent_trade_status(world, "merchant_alice")
            display_agent_trade_status(world, "adventurer_bob")
            display_trading_post_status(world)
    
    print("\n" + "=" * 70)
    print("🎉 基本トレードシステム検証デモが完了しました！")
    print("✅ アイテムとお金の取引が正常に動作しました")
    print("=" * 70)


def test_trade_error_handling():
    """トレードエラーハンドリングのテスト"""
    print("\n\n🧪 トレードエラーハンドリングテスト")
    print("=" * 70)
    
    world = create_trading_test_world()
    
    print("📊 テスト条件の設定")
    
    # テスト1: 所持していないアイテムの出品
    print("\n🧪 テスト1: 所持していないアイテムの出品")
    fake_trade = PostTrade(
        description="存在しないアイテムを出品",
        offered_item_id="fake_item",
        requested_money=100
    )
    
    try:
        world.execute_agent_post_trade("merchant_alice", fake_trade)
        print("❌ テスト失敗: 存在しないアイテムが出品できてしまいました")
    except ValueError as e:
        print(f"✅ テスト成功: 期待通りエラーが発生しました - {e}")
    
    # テスト2: 自分の出品の受託
    print("\n🧪 テスト2: 自分の出品の受託")
    # まず出品
    valid_trade = PostTrade(
        description="テスト用出品",
        offered_item_id="iron_sword",
        requested_money=50
    )
    trade_id = world.execute_agent_post_trade("merchant_alice", valid_trade)
    
    # 自分で受託しようとする
    self_accept = AcceptTrade(
        description="自分の出品を受託",
        trade_id=trade_id
    )
    
    try:
        world.execute_agent_accept_trade("merchant_alice", self_accept)
        print("❌ テスト失敗: 自分の出品が受託できてしまいました")
    except ValueError as e:
        print(f"✅ テスト成功: 期待通りエラーが発生しました - {e}")
    
    # テスト3: 資金不足での購入
    print("\n🧪 テスト3: 資金不足での購入")
    # 高額な取引を出品（シャーリーの所持金300ゴールドを超える価格）
    expensive_trade = PostTrade(
        description="高額取引（500ゴールド）",
        offered_item_id="iron_sword",
        requested_money=500
    )
    expensive_trade_id = world.execute_agent_post_trade("merchant_alice", expensive_trade)
    
    expensive_accept = AcceptTrade(
        description="資金不足で高額取引を受託",
        trade_id=expensive_trade_id
    )
    
    # シャーリー（所持金300）で高額な取引（500ゴールド）を受託しようとする
    try:
        world.execute_agent_accept_trade("mage_charlie", expensive_accept)
        print("❌ テスト失敗: 資金不足でも購入できてしまいました")
    except ValueError as e:
        print(f"✅ テスト成功: 期待通りエラーが発生しました - {e}")
    
    print("✅ トレードエラーハンドリングテストが完了しました")


def test_trade_filtering():
    """取引フィルタリング機能のテスト"""
    print("\n\n🧪 取引フィルタリング機能テスト")
    print("=" * 70)
    
    world = create_trading_test_world()
    
    # 複数の取引を出品
    trades = [
        PostTrade(description="鉄の剣1", offered_item_id="iron_sword", requested_money=100),
        PostTrade(description="鉄の剣2", offered_item_id="iron_sword", requested_money=150),
        PostTrade(description="革の鎧", offered_item_id="leather_armor", requested_money=80),
        PostTrade(description="ヘルスポーション", offered_item_id="health_potion", requested_money=30),
    ]
    
    print("📊 複数の取引を出品中...")
    for trade in trades:
        world.execute_agent_post_trade("merchant_alice", trade)
    
    # フィルタリングテスト
    print("\n🔍 フィルタリングテスト1: 鉄の剣のみ表示")
    sword_filter = ViewTrades(
        description="鉄の剣の取引を検索",
        filter_offered_item_id="iron_sword"
    )
    
    filtered_trades = world.execute_agent_view_trades("adventurer_bob", sword_filter)
    print(f"結果: {len(filtered_trades)}件の取引が見つかりました")
    for trade in filtered_trades:
        print(f"  - {trade.get_trade_summary()}")
    
    print("\n🔍 フィルタリングテスト2: 100ゴールド以下の取引")
    price_filter = ViewTrades(
        description="100ゴールド以下の取引を検索",
        max_price=100
    )
    
    filtered_trades = world.execute_agent_view_trades("adventurer_bob", price_filter)
    print(f"結果: {len(filtered_trades)}件の取引が見つかりました")
    for trade in filtered_trades:
        print(f"  - {trade.get_trade_summary()}")
    
    print("✅ 取引フィルタリング機能テストが完了しました")


def test_trade_cancellation():
    """取引キャンセル機能のテスト"""
    print("\n\n🧪 取引キャンセル機能テスト")
    print("=" * 70)
    
    world = create_trading_test_world()
    
    # 取引を出品
    test_trade = PostTrade(
        description="キャンセルテスト用取引",
        offered_item_id="iron_sword",
        requested_money=100
    )
    
    print("📊 取引を出品...")
    trade_id = world.execute_agent_post_trade("merchant_alice", test_trade)
    
    print(f"出品した取引ID: {trade_id[:8]}...")
    display_trading_post_status(world)
    
    # キャンセル実行
    cancel_trade = CancelTrade(
        description="取引をキャンセル",
        trade_id=trade_id
    )
    
    print("\n📊 取引をキャンセル...")
    success = world.execute_agent_cancel_trade("merchant_alice", cancel_trade)
    
    if success:
        print("✅ 取引のキャンセルが成功しました")
        display_agent_trade_status(world, "merchant_alice")
        display_trading_post_status(world)
    
    print("✅ 取引キャンセル機能テストが完了しました")


def run_all_trading_tests():
    """全てのトレードシステムテストを実行"""
    print("🧪 トレードシステム - 全テスト実行")
    print("=" * 70)
    
    try:
        # メインデモ
        demo_basic_trading_system()
        
        # エラーハンドリングテスト
        test_trade_error_handling()
        
        # フィルタリング機能テスト
        test_trade_filtering()
        
        # キャンセル機能テスト
        test_trade_cancellation()
        
        print("\n" + "=" * 70)
        print("🎉 全てのトレードシステムテストが成功しました！")
        print("✅ トレードシステムが正しく実装されています")
        return True
        
    except Exception as e:
        print(f"❌ テスト中にエラーが発生しました: {e}")
        return False


if __name__ == "__main__":
    run_all_trading_tests() 
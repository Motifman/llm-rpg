"""
バトルシステムのテストケース

- モンスターの作成と配置
- 探索によるモンスター発見
- 戦闘の開始と進行
- 複数エージェントでの戦闘
- 戦闘結果と報酬配布
- 攻撃的なモンスターとの強制戦闘
"""

from src.systems.world import World
from src.models.spot import Spot
from src.models.agent import Agent
from src.models.monster import Monster, MonsterType, MonsterDropReward
from src.models.item import Item
from src.models.action import Exploration, Movement, StartBattle, JoinBattle, AttackMonster, DefendBattle, EscapeBattle


def create_battle_test_world():
    """バトルテスト用のワールドを作成"""
    world = World()
    
    # === スポットの作成 ===
    
    # 1. 街の広場（出発地点）
    town_square = Spot("town_square", "街の広場", "平和な街の中心地")
    world.add_spot(town_square)
    
    # 2. 森の入り口（受動的なモンスター）
    forest_entrance = Spot("forest_entrance", "森の入り口", "薄暗い森への入り口")
    world.add_spot(forest_entrance)
    
    # 3. 洞窟（攻撃的なモンスター）
    cave = Spot("cave", "洞窟", "危険な雰囲気の洞窟")
    world.add_spot(cave)
    
    # 4. 草原（隠れているモンスター）
    grassland = Spot("grassland", "草原", "草が生い茂る静かな場所")
    world.add_spot(grassland)
    
    # === 移動の設定 ===
    
    town_square.add_movement(Movement("北へ移動", "北", "forest_entrance"))
    town_square.add_movement(Movement("東へ移動", "東", "cave"))
    town_square.add_movement(Movement("南へ移動", "南", "grassland"))
    
    forest_entrance.add_movement(Movement("南へ戻る", "南", "town_square"))
    cave.add_movement(Movement("西へ戻る", "西", "town_square"))
    grassland.add_movement(Movement("北へ戻る", "北", "town_square"))
    
    # === モンスターの作成 ===
    
    # 1. 受動的なモンスター（森のスライム）
    forest_slime_reward = MonsterDropReward(
        items=[Item("slime_gel", "スライムのゲル")],
        money=20,
        experience=15,
        information=["スライムは水分を好む生物だということがわかった"]
    )
    forest_slime = Monster(
        monster_id="forest_slime",
        name="森のスライム",
        description="緑色の愛らしいスライム",
        monster_type=MonsterType.PASSIVE,
        max_hp=30,
        attack=5,
        defense=2,
        speed=3,
        drop_reward=forest_slime_reward
    )
    
    # 2. 攻撃的なモンスター（洞窟のゴブリン）
    cave_goblin_reward = MonsterDropReward(
        items=[Item("rusty_sword", "錆びた剣")],
        money=50,
        experience=30,
        information=["ゴブリンは集団で行動することが多い"]
    )
    cave_goblin = Monster(
        monster_id="cave_goblin",
        name="洞窟のゴブリン",
        description="凶暴な緑色の小鬼",
        monster_type=MonsterType.AGGRESSIVE,
        max_hp=40,
        attack=12,
        defense=4,
        speed=6,
        drop_reward=cave_goblin_reward
    )
    
    # 3. 隠れているモンスター（草原のウサギ）
    grassland_rabbit_reward = MonsterDropReward(
        items=[Item("rabbit_foot", "ウサギの足")],
        money=10,
        experience=8,
        information=["このウサギは珍しい種類のようだ"]
    )
    grassland_rabbit = Monster(
        monster_id="grassland_rabbit",
        name="草原のウサギ",
        description="ふわふわした白いウサギ",
        monster_type=MonsterType.HIDDEN,
        max_hp=15,
        attack=3,
        defense=1,
        speed=10,
        drop_reward=grassland_rabbit_reward
    )
    
    # === モンスターを配置 ===
    
    world.add_monster(forest_slime, "forest_entrance")
    world.add_monster(cave_goblin, "cave")
    world.add_monster(grassland_rabbit, "grassland")
    
    # === 探索行動の設定 ===
    
    # 草原の探索（隠れているモンスターを発見する可能性）
    grassland_exploration = Exploration(
        description="草むらを探索する",
        discovered_info="草原を詳しく調べてみた"
    )
    grassland.add_exploration(grassland_exploration)
    
    # === エージェントの作成 ===
    
    # 戦士エージェント
    warrior = Agent("warrior_001", "戦士アルバート")
    warrior.set_current_spot_id("town_square")
    warrior.set_attack(15)  # 強い攻撃力
    warrior.set_defense(8)  # 高い防御力
    warrior.set_speed(5)    # 普通の速度
    world.add_agent(warrior)
    
    # 盗賊エージェント
    rogue = Agent("rogue_001", "盗賊ベラ")
    rogue.set_current_spot_id("town_square")
    rogue.set_attack(10)    # 普通の攻撃力
    rogue.set_defense(4)    # 低い防御力
    rogue.set_speed(12)     # 高い速度
    world.add_agent(rogue)
    
    return world


def test_basic_monster_creation():
    """基本的なモンスター作成のテスト"""
    print("🧪 基本的なモンスター作成のテスト")
    print("=" * 50)
    
    world = create_battle_test_world()
    
    # モンスターが正しく作成されていることを確認
    forest_slime = world.get_monster("forest_slime")
    cave_goblin = world.get_monster("cave_goblin")
    grassland_rabbit = world.get_monster("grassland_rabbit")
    
    print(f"✅ 森のスライム: {forest_slime}")
    print(f"✅ 洞窟のゴブリン: {cave_goblin}")
    print(f"✅ 草原のウサギ: {grassland_rabbit}")
    
    # モンスターがスポットに正しく配置されていることを確認
    forest_entrance = world.get_spot("forest_entrance")
    cave = world.get_spot("cave")
    grassland = world.get_spot("grassland")
    
    assert len(forest_entrance.get_visible_monsters()) == 1
    assert len(cave.get_visible_monsters()) == 1
    assert len(grassland.get_visible_monsters()) == 0  # 隠れているため見えない
    assert len(grassland.hidden_monsters) == 1
    
    print("✅ モンスターの作成と配置が正常に完了")


def test_exploration_monster_discovery():
    """探索によるモンスター発見のテスト"""
    print("\n🧪 探索によるモンスター発見のテスト")
    print("=" * 50)
    
    world = create_battle_test_world()
    warrior = world.get_agent("warrior_001")
    
    # 草原に移動
    move_to_grassland = Movement("南へ移動", "南", "grassland")
    world.execute_action("warrior_001", move_to_grassland)
    
    grassland = world.get_spot("grassland")
    print(f"移動前 - 見えるモンスター数: {len(grassland.get_visible_monsters())}")
    print(f"移動前 - 隠れているモンスター数: {len(grassland.hidden_monsters)}")
    
    # 探索を繰り返してモンスターを発見
    exploration_action = Exploration(
        description="草むらを探索する",
        discovered_info="草原を詳しく調べてみた"
    )
    
    discovered = False
    for i in range(10):  # 最大10回まで探索
        old_info_count = len(warrior.get_discovered_info())
        world.execute_action("warrior_001", exploration_action)
        new_info_count = len(warrior.get_discovered_info())
        
        # 新しい情報が追加されているかチェック
        if new_info_count > old_info_count:
            recent_info = warrior.get_discovered_info()[-1]
            print(f"探索 {i+1}: {recent_info}")
            
            # モンスター発見の確認
            if "発見した" in recent_info:
                discovered = True
                break
        else:
            print(f"探索 {i+1}: 何も見つからなかった")
    
    print(f"探索後 - 見えるモンスター数: {len(grassland.get_visible_monsters())}")
    print(f"探索後 - 隠れているモンスター数: {len(grassland.hidden_monsters)}")
    
    if discovered:
        print("✅ 隠れているモンスターの発見に成功")
    else:
        print("⚠️ 隠れているモンスターを発見できませんでした（確率の問題）")


def test_single_agent_battle():
    """単一エージェントでの戦闘テスト"""
    print("\n🧪 単一エージェントでの戦闘テスト")
    print("=" * 50)
    
    world = create_battle_test_world()
    warrior = world.get_agent("warrior_001")
    
    # 森の入り口に移動
    move_to_forest = Movement("北へ移動", "北", "forest_entrance")
    world.execute_action("warrior_001", move_to_forest)
    
    print(f"戦闘前のウォリアーステータス: {warrior.get_status_summary()}")
    
    # 戦闘を開始
    start_battle_action = StartBattle(
        description="森のスライムとの戦闘を開始",
        monster_id="forest_slime"
    )
    battle_id = world.execute_action("warrior_001", start_battle_action)
    print(f"戦闘開始: バトルID = {battle_id}")
    
    # 戦闘を進行
    battle = world.get_battle_manager().get_battle(battle_id)
    print(f"戦闘状況:\n{battle.get_battle_status()}")
    
    turn_count = 0
    while not battle.is_battle_finished() and turn_count < 20:  # 無限ループ防止
        turn_count += 1
        print(f"\n--- ターン {turn_count} ---")
        
        if battle.is_agent_turn():
            current_actor = battle.get_current_actor()
            print(f"{current_actor} のターン")
            
            # 攻撃行動を実行
            attack_action = AttackMonster(
                description="スライムを攻撃",
                monster_id="forest_slime"
            )
            result = world.execute_action(current_actor, attack_action)
            print(f"行動結果: {result}")
        
        print(f"現在のモンスターHP: {battle.monster.current_hp}/{battle.monster.max_hp}")
        print(f"現在のウォリアーHP: {warrior.current_hp}/{warrior.max_hp}")
    
    print(f"\n戦闘後のウォリアーステータス: {warrior.get_status_summary()}")
    print(f"戦闘ログ:")
    for log in battle.battle_log:
        print(f"  {log}")
    
    # 戦闘結果の確認
    if battle.is_battle_finished():
        print("✅ 戦闘が正常に終了")
    else:
        print("❌ 戦闘が終了しませんでした")


def test_multi_agent_battle():
    """複数エージェントでの戦闘テスト"""
    print("\n🧪 複数エージェントでの戦闘テスト")
    print("=" * 50)
    
    world = create_battle_test_world()
    warrior = world.get_agent("warrior_001")
    rogue = world.get_agent("rogue_001")
    
    # 両エージェントを森の入り口に移動
    move_to_forest = Movement("北へ移動", "北", "forest_entrance")
    world.execute_action("warrior_001", move_to_forest)
    world.execute_action("rogue_001", move_to_forest)
    
    print(f"戦闘前:")
    print(f"  ウォリアー: {warrior.get_status_summary()}")
    print(f"  ローグ: {rogue.get_status_summary()}")
    
    # 戦士が戦闘を開始
    start_battle_action = StartBattle(
        description="森のスライムとの戦闘を開始",
        monster_id="forest_slime"
    )
    battle_id = world.execute_action("warrior_001", start_battle_action)
    print(f"戦闘開始: バトルID = {battle_id}")
    
    # 盗賊が戦闘に参加
    join_battle_action = JoinBattle(
        description="戦闘に参加",
        battle_id=battle_id
    )
    world.execute_action("rogue_001", join_battle_action)
    print("盗賊が戦闘に参加")
    
    # 戦闘を進行
    battle = world.get_battle_manager().get_battle(battle_id)
    print(f"戦闘状況:\n{battle.get_battle_status()}")
    
    turn_count = 0
    while not battle.is_battle_finished() and turn_count < 15:  # 無限ループ防止
        turn_count += 1
        print(f"\n--- ターン {turn_count} ---")
        
        if battle.is_agent_turn():
            current_actor = battle.get_current_actor()
            current_agent = world.get_agent(current_actor)
            print(f"{current_agent.name} のターン")
            
            # 攻撃行動を実行
            attack_action = AttackMonster(
                description="スライムを攻撃",
                monster_id="forest_slime"
            )
            result = world.execute_action(current_actor, attack_action)
            print(f"行動結果: {result}")
        
        print(f"現在のモンスターHP: {battle.monster.current_hp}/{battle.monster.max_hp}")
    
    print(f"\n戦闘後:")
    print(f"  ウォリアー: {warrior.get_status_summary()}")
    print(f"  ローグ: {rogue.get_status_summary()}")
    
    # 戦闘結果の確認
    if battle.is_battle_finished():
        print("✅ 複数エージェント戦闘が正常に終了")
    else:
        print("❌ 戦闘が終了しませんでした")


def test_aggressive_monster_encounter():
    """攻撃的なモンスターとの強制戦闘テスト"""
    print("\n🧪 攻撃的なモンスターとの強制戦闘テスト")
    print("=" * 50)
    
    world = create_battle_test_world()
    warrior = world.get_agent("warrior_001")
    
    print(f"移動前のウォリアーステータス: {warrior.get_status_summary()}")
    print("洞窟に移動します...")
    
    # 洞窟に移動（攻撃的なモンスターがいる）
    move_to_cave = Movement("東へ移動", "東", "cave")
    world.execute_action("warrior_001", move_to_cave)
    
    # 強制戦闘が発生しているかチェック
    current_battle = world.get_battle_manager().get_battle_by_spot("cave")
    
    if current_battle:
        print("✅ 攻撃的なモンスターによる強制戦闘が発生")
        print(f"戦闘状況:\n{current_battle.get_battle_status()}")
        
        # 数ターン戦闘を進行
        turn_count = 0
        while not current_battle.is_battle_finished() and turn_count < 10:
            turn_count += 1
            print(f"\n--- ターン {turn_count} ---")
            
            if current_battle.is_agent_turn():
                current_actor = current_battle.get_current_actor()
                print(f"{current_actor} のターン")
                
                # 攻撃行動を実行
                attack_action = AttackMonster(
                    description="ゴブリンを攻撃",
                    monster_id="cave_goblin"
                )
                result = world.execute_action(current_actor, attack_action)
                print(f"行動結果: {result}")
            
            print(f"モンスターHP: {current_battle.monster.current_hp}/{current_battle.monster.max_hp}")
            print(f"ウォリアーHP: {warrior.current_hp}/{warrior.max_hp}")
        
        print(f"戦闘後のウォリアーステータス: {warrior.get_status_summary()}")
    else:
        print("❌ 攻撃的なモンスターとの強制戦闘が発生しませんでした")


def test_escape_from_battle():
    """戦闘からの逃走テスト"""
    print("\n🧪 戦闘からの逃走テスト")
    print("=" * 50)
    
    world = create_battle_test_world()
    rogue = world.get_agent("rogue_001")
    
    # 森の入り口に移動
    move_to_forest = Movement("北へ移動", "北", "forest_entrance")
    world.execute_action("rogue_001", move_to_forest)
    
    print(f"戦闘前のローグステータス: {rogue.get_status_summary()}")
    
    # 戦闘を開始
    start_battle_action = StartBattle(
        description="森のスライムとの戦闘を開始",
        monster_id="forest_slime"
    )
    battle_id = world.execute_action("rogue_001", start_battle_action)
    print(f"戦闘開始: バトルID = {battle_id}")
    
    # 戦闘を進行（逃走を試行）
    battle = world.get_battle_manager().get_battle(battle_id)
    
    for attempt in range(5):  # 最大5回逃走を試行
        print(f"\n--- 逃走試行 {attempt + 1} ---")
        
        if battle.is_battle_finished():
            break
            
        if battle.is_agent_turn() and battle.get_current_actor() == "rogue_001":
            # 逃走行動を実行
            escape_action = EscapeBattle(description="戦闘から逃走")
            result = world.execute_action("rogue_001", escape_action)
            print(f"逃走結果: {result}")
            
            # 逃走に成功した場合、戦闘参加者から除外されているかチェック
            if "rogue_001" not in battle.participants:
                print("✅ 逃走に成功しました")
                break
        else:
            # 他のターンをスキップするために攻撃
            if battle.is_agent_turn():
                attack_action = AttackMonster(
                    description="スライムを攻撃",
                    monster_id="forest_slime"
                )
                world.execute_action("rogue_001", attack_action)
    
    print(f"戦闘後のローグステータス: {rogue.get_status_summary()}")


def run_all_battle_tests():
    """すべてのバトルテストを実行"""
    print("🎮 バトルシステム総合テスト")
    print("=" * 80)
    
    test_basic_monster_creation()
    test_exploration_monster_discovery()
    test_single_agent_battle()
    test_multi_agent_battle()
    test_aggressive_monster_encounter()
    test_escape_from_battle()
    
    print("\n" + "=" * 80)
    print("✅ すべてのバトルテストが完了しました")


if __name__ == "__main__":
    run_all_battle_tests() 
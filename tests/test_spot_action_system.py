"""
SpotActionシステムのテストケース

新しく実装したSpot行動システムの動作を検証
"""

import pytest
from src.models.spot import Spot
from src.models.agent import Agent
from src.models.item import Item
from src.models.action import Movement
from src.models.spot_action import (
    Role, Permission, SpotAction, ActionResult, ActionWarning,
    MovementSpotAction, ExplorationSpotAction
)
from src.systems.world import World


def create_test_world_with_spot_actions():
    """SpotActionテスト用のワールドを作成"""
    world = World()
    
    # スポットを作成
    town_square = Spot("town_square", "街の広場", "賑やかな街の中心地")
    forest = Spot("forest", "森", "静かな森")
    
    # 移動設定
    town_square.add_movement(Movement("北に移動", "北", "forest"))
    forest.add_movement(Movement("南に移動", "南", "town_square"))
    
    # アイテムを配置
    herb = Item("herb", "薬草")
    forest.add_item(herb)
    
    world.add_spot(town_square)
    world.add_spot(forest)
    
    return world


def test_role_system():
    """役職システムのテスト"""
    # 一般市民エージェント
    citizen = Agent("citizen1", "市民太郎", Role.CITIZEN)
    assert citizen.get_role() == Role.CITIZEN
    assert citizen.is_role(Role.CITIZEN)
    assert not citizen.is_role(Role.MERCHANT)
    
    # 商人エージェント
    merchant = Agent("merchant1", "商人花子", Role.MERCHANT)
    assert merchant.get_role() == Role.MERCHANT
    
    # 役職変更
    citizen.set_role(Role.ADVENTURER)
    assert citizen.get_role() == Role.ADVENTURER


def test_permission_system():
    """権限システムのテスト"""
    from src.models.spot_action import ActionPermissionChecker
    
    checker = ActionPermissionChecker("test_spot")
    
    # デフォルト権限
    citizen = Agent("citizen1", "市民太郎", Role.CITIZEN)
    assert checker.get_agent_permission(citizen) == Permission.CUSTOMER
    
    # 役職権限設定
    checker.set_role_permission(Role.MERCHANT, Permission.EMPLOYEE)
    merchant = Agent("merchant1", "商人花子", Role.MERCHANT)
    assert checker.get_agent_permission(merchant) == Permission.EMPLOYEE
    
    # 個別権限設定（役職権限より優先）
    checker.set_agent_permission("citizen1", Permission.OWNER)
    assert checker.get_agent_permission(citizen) == Permission.OWNER
    
    # 権限チェック
    assert checker.check_permission(citizen, Permission.CUSTOMER)  # OWNER >= CUSTOMER
    assert checker.check_permission(citizen, Permission.OWNER)     # OWNER >= OWNER
    assert not checker.check_permission(merchant, Permission.OWNER)  # EMPLOYEE < OWNER


def test_movement_spot_action():
    """移動SpotActionのテスト"""
    world = create_test_world_with_spot_actions()
    
    agent = Agent("test_agent", "テストエージェント")
    agent.set_current_spot_id("town_square")
    world.add_agent(agent)
    
    town_square = world.get_spot("town_square")
    
    # 移動行動の作成
    move_action = MovementSpotAction("move_north", "北", "forest")
    
    # 実行可能性チェック
    warnings = move_action.can_execute(agent, town_square, world)
    assert len(warnings) == 0  # 警告なし
    
    # 移動実行
    result = move_action.execute(agent, town_square, world)
    assert result.success
    assert agent.get_current_spot_id() == "forest"
    assert "移動しました" in result.message
    
    # 存在しない移動先への移動
    invalid_move = MovementSpotAction("move_invalid", "無効", "invalid_spot")
    warnings = invalid_move.can_execute(agent, town_square, world)
    assert any(w.is_blocking for w in warnings)  # ブロッキング警告あり


def test_exploration_spot_action():
    """探索SpotActionのテスト"""
    world = create_test_world_with_spot_actions()
    
    agent = Agent("test_agent", "テストエージェント")
    agent.set_current_spot_id("forest")
    world.add_agent(agent)
    
    forest = world.get_spot("forest")
    
    # 探索行動の作成
    explore_action = ExplorationSpotAction("explore_general", "general")
    
    # 実行可能性チェック
    warnings = explore_action.can_execute(agent, forest, world)
    assert len(warnings) == 0  # アイテムがあるので警告なし
    
    # 探索実行
    initial_items = len(agent.get_items())
    initial_exp = agent.experience_points
    
    result = explore_action.execute(agent, forest, world)
    assert result.success
    assert len(agent.get_items()) > initial_items  # アイテム獲得
    assert agent.experience_points > initial_exp   # 経験値獲得
    assert "探索を行いました" in result.message


def test_spot_action_integration():
    """SpotとSpotActionの統合テスト"""
    world = create_test_world_with_spot_actions()
    
    agent = Agent("test_agent", "テストエージェント", Role.ADVENTURER)
    agent.set_current_spot_id("town_square")
    world.add_agent(agent)
    
    town_square = world.get_spot("town_square")
    
    # 利用可能な行動を取得
    available_actions = town_square.get_available_spot_actions(agent, world)
    
    # 移動行動（北）と探索行動が含まれているはず
    action_names = [action_data["action"].name for action_data in available_actions]
    assert "北に移動" in action_names
    assert "探索" in action_names
    
    # 移動行動を実行
    result = town_square.execute_spot_action("movement_北", agent, world)
    assert result.success
    assert agent.get_current_spot_id() == "forest"


def test_world_spot_action_integration():
    """WorldクラスとSpotActionの統合テスト"""
    world = create_test_world_with_spot_actions()
    
    agent = Agent("test_agent", "テストエージェント", Role.ADVENTURER)
    agent.set_current_spot_id("town_square")
    world.add_agent(agent)
    
    # エージェントの利用可能行動を取得
    actions_info = world.get_available_actions_for_agent("test_agent")
    
    assert actions_info["agent_id"] == "test_agent"
    assert actions_info["current_spot"]["spot_id"] == "town_square"
    assert actions_info["total_actions"] >= 2  # 移動と探索
    
    # World経由でSpotAction実行
    result = world.execute_spot_action("test_agent", "movement_北")
    assert result.success
    assert agent.get_current_spot_id() == "forest"


def test_permission_warnings():
    """権限警告のテスト"""
    world = create_test_world_with_spot_actions()
    
    # アクセス拒否エージェント
    denied_agent = Agent("denied_agent", "拒否エージェント", Role.CITIZEN)
    denied_agent.set_current_spot_id("town_square")
    world.add_agent(denied_agent)
    
    town_square = world.get_spot("town_square")
    
    # 市民にはアクセス拒否権限を設定
    town_square.set_role_permission(Role.CITIZEN, Permission.DENIED)
    
    # 移動行動を実行（権限不足でエラーになるはず）
    result = town_square.execute_spot_action("movement_北", denied_agent, world)
    assert not result.success  # 失敗
    assert len(result.warnings) > 0  # 警告あり
    assert any("権限不足" in w.message for w in result.warnings)


if __name__ == "__main__":
    # 基本テストを実行
    print("🧪 SpotActionシステムのテスト開始")
    
    test_role_system()
    print("✅ 役職システムテスト完了")
    
    test_permission_system()
    print("✅ 権限システムテスト完了")
    
    test_movement_spot_action()
    print("✅ 移動SpotActionテスト完了")
    
    test_exploration_spot_action()
    print("✅ 探索SpotActionテスト完了")
    
    test_spot_action_integration()
    print("✅ Spot統合テスト完了")
    
    test_world_spot_action_integration()
    print("✅ World統合テスト完了")
    
    test_permission_warnings()
    print("✅ 権限警告テスト完了")
    
    print("🎉 すべてのテストが完了しました！") 
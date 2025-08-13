"""
ドア・移動システム連携の単体テスト
基本的な機能を個別にテストする
"""

from src_old.models.spot import Spot
from src_old.models.agent import Agent
from src_old.models.item import Item
from src_old.models.action import Interaction, InteractionType
from src_old.models.interactable import Door
from src_old.systems.world import World


def test_door_creates_movement():
    """ドアがMovementを正しく生成するかのテスト"""
    print("🧪 ドアMovement生成テスト")
    
    door = Door(
        object_id="test_door",
        name="テストドア",
        description="テスト用のドア",
        target_spot_id="target_room"
    )
    
    # 最初は閉じているのでMovementは生成されない
    movement = door.creates_movement_when_opened()
    assert movement is None, "閉じているドアはMovementを生成してはいけません"
    print("✅ 閉じたドア: Movement生成なし")
    
    # ドアを開く
    door.set_state("is_open", True)
    movement = door.creates_movement_when_opened()
    assert movement is not None, "開いているドアはMovementを生成すべきです"
    assert movement.target_spot_id == "target_room", "target_spot_idが正しくありません"
    assert "テストドアを通る" in movement.direction, "移動方向の記述が正しくありません"
    print("✅ 開いたドア: Movement生成あり")
    
    print("✅ ドアMovement生成テスト完了\n")


def test_spot_dynamic_movement():
    """SpotのDynamicMovement機能のテスト"""
    print("🧪 Spot動的Movement管理テスト")
    
    spot = Spot("test_spot", "テストスポット", "テスト用のスポット")
    
    # 初期状態
    movements = spot.get_available_movements()
    assert len(movements) == 0, "初期状態では移動先がないはずです"
    print("✅ 初期状態: 移動先0個")
    
    # 動的Movementを追加
    from src_old.models.action import Movement
    test_movement = Movement(
        description="テスト移動",
        direction="テスト方向",
        target_spot_id="test_target"
    )
    spot.add_dynamic_movement(test_movement)
    
    movements = spot.get_available_movements()
    assert len(movements) == 1, "動的移動追加後は移動先が1個あるはずです"
    assert movements[0].target_spot_id == "test_target", "追加した移動先が正しくありません"
    print("✅ 動的Movement追加: 移動先1個")
    
    # 重複追加のテスト
    spot.add_dynamic_movement(test_movement)  # 同じMovementを再度追加
    movements = spot.get_available_movements()
    assert len(movements) == 1, "重複追加は阻止されるべきです"
    print("✅ 重複阻止: 移動先1個のまま")
    
    # 削除のテスト
    spot.remove_dynamic_movement("test_target", "テスト方向")
    movements = spot.get_available_movements()
    assert len(movements) == 0, "削除後は移動先がないはずです"
    print("✅ 動的Movement削除: 移動先0個")
    
    print("✅ Spot動的Movement管理テスト完了\n")


def test_door_bidirectional_integration():
    """ドア開放時の双方向移動統合テスト"""
    print("🧪 ドア双方向移動統合テスト")
    
    world = World()
    
    # スポットを作成
    room_a = Spot("room_a", "部屋A", "部屋Aの説明")
    room_b = Spot("room_b", "部屋B", "部屋Bの説明")
    world.add_spot(room_a)
    world.add_spot(room_b)
    
    # ドアを作成
    door = Door(
        object_id="connecting_door",
        name="連結ドア",
        description="部屋を繋ぐドア",
        target_spot_id="room_b"
    )
    room_a.add_interactable(door)
    
    # エージェントを作成
    agent = Agent("test_agent", "テストエージェント")
    agent.set_current_spot_id("room_a")
    world.add_agent(agent)
    
    # 初期状態の確認
    movements_a = room_a.get_available_movements()
    movements_b = room_b.get_available_movements()
    assert len(movements_a) == 0, "初期状態で部屋Aには移動先がないはずです"
    assert len(movements_b) == 0, "初期状態で部屋Bには移動先がないはずです"
    print("✅ 初期状態: 両方の部屋に移動先なし")
    
    # ドアを開ける
    open_interaction = Interaction(
        description="連結ドアを開ける",
        object_id="connecting_door",
        interaction_type=InteractionType.OPEN,
        state_changes={"is_open": True}
    )
    
    world.execute_agent_interaction("test_agent", open_interaction)
    
    # ドア開放後の確認
    movements_a = room_a.get_available_movements()
    movements_b = room_b.get_available_movements()
    assert len(movements_a) == 1, "ドア開放後、部屋Aには1つの移動先があるはずです"
    assert len(movements_b) == 1, "ドア開放後、部屋Bにも1つの移動先があるはずです"
    assert movements_a[0].target_spot_id == "room_b", "部屋Aから部屋Bへの移動があるはずです"
    assert movements_b[0].target_spot_id == "room_a", "部屋Bから部屋Aへの移動があるはずです"
    print("✅ ドア開放後: 双方向移動が追加された")
    
    print("✅ ドア双方向移動統合テスト完了\n")


def test_key_required_door():
    """鍵が必要なドアのテスト"""
    print("🧪 鍵付きドアテスト")
    
    world = World()
    
    # スポットとアイテム
    room = Spot("room", "部屋", "テスト部屋")
    secret_room = Spot("secret_room", "秘密の部屋", "隠された部屋")
    world.add_spot(room)
    world.add_spot(secret_room)
    key = Item("door_key", "ドアの鍵 - テスト用の鍵")
    
    # 鍵付きドア
    door = Door(
        object_id="locked_door",
        name="鍵付きドア",
        description="鍵が必要なドア",
        target_spot_id="secret_room",
        key_item_id="door_key"
    )
    room.add_interactable(door)
    
    # エージェント（鍵なし）
    agent = Agent("test_agent", "テストエージェント")
    agent.set_current_spot_id("room")
    world.add_agent(agent)
    
    # 鍵なしでドアを開けようとする
    open_interaction = Interaction(
        description="鍵付きドアを開ける",
        object_id="locked_door",
        interaction_type=InteractionType.OPEN,
        required_item_id="door_key",
        state_changes={"is_open": True}
    )
    
    try:
        world.execute_agent_interaction("test_agent", open_interaction)
        assert False, "鍵なしでドアが開いてしまいました"
    except ValueError as e:
        assert "door_key" in str(e), "エラーメッセージに鍵の情報が含まれていません"
        print("✅ 鍵なし: 適切にエラーが発生")
    
    # 鍵を持たせる
    agent.add_item(key)
    
    # 鍵ありでドアを開ける
    try:
        world.execute_agent_interaction("test_agent", open_interaction)
        print("✅ 鍵あり: ドアが正常に開いた")
    except Exception as e:
        assert False, f"鍵ありでドアが開かなかった: {e}"
    
    print("✅ 鍵付きドアテスト完了\n")


def run_all_unit_tests():
    """全ての単体テストを実行"""
    print("🧪 ドア・移動システム単体テスト開始")
    print("=" * 60)
    
    try:
        test_door_creates_movement()
        test_spot_dynamic_movement()
        test_door_bidirectional_integration()
        test_key_required_door()
        
        print("=" * 60)
        print("🎉 全ての単体テストが成功しました！")
        print("✅ ドア・移動システム連携が正しく実装されています")
        return True
        
    except AssertionError as e:
        print(f"❌ テスト失敗: {e}")
        return False
    except Exception as e:
        print(f"❌ エラー発生: {e}")
        return False


if __name__ == "__main__":
    run_all_unit_tests() 
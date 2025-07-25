"""
会話システムのテストケース

- 基本的な会話機能
- スポット限定メッセージ配信
- 複数エージェント間の会話
- 特定エージェント宛てメッセージ
- ConversationManagerの動作確認
"""

from src.systems.world import World
from src.models.spot import Spot
from src.models.agent import Agent
from src.models.action import Conversation
from src.systems.message import LocationChatMessage
from src.systems.conversation import ConversationManager


def setup_test_world():
    """テスト用のWorldを作成"""
    world = World()
    
    # スポットを作成
    spot1 = Spot("spot1", "広場", "中央の広場")
    spot2 = Spot("spot2", "図書館", "静かな図書館")
    world.add_spot(spot1)
    world.add_spot(spot2)
    
    # エージェントを作成
    agent1 = Agent("agent1", "アリス")
    agent2 = Agent("agent2", "ボブ")
    agent3 = Agent("agent3", "チャーリー")
    
    # エージェントをspotに配置
    agent1.set_current_spot_id("spot1")
    agent2.set_current_spot_id("spot1")
    agent3.set_current_spot_id("spot2")
    
    world.add_agent(agent1)
    world.add_agent(agent2)
    world.add_agent(agent3)
    
    return world


def test_basic_conversation():
    """基本的な会話機能のテスト"""
    print("\n=== 基本的な会話機能のテスト ===")
    
    world = setup_test_world()
    
    # エージェント1が会話を開始
    conversation = Conversation(
        description="挨拶をする",
        content="こんにちは、みなさん！"
    )
    
    # 会話実行前の状態確認
    agent1 = world.get_agent("agent1")
    agent2 = world.get_agent("agent2")
    agent3 = world.get_agent("agent3")
    
    print(f"実行前:")
    print(f"  agent1 未読メッセージ: {len(agent1.get_received_messages())}")
    print(f"  agent2 未読メッセージ: {len(agent2.get_received_messages())}")
    print(f"  agent3 未読メッセージ: {len(agent3.get_received_messages())}")
    
    # 会話を実行
    message = world.execute_action("agent1", conversation)
    
    print(f"\n会話実行: {conversation.content}")
    print(f"送信されたメッセージID: {message.message_id[:8]}...")
    
    # 結果確認
    print(f"\n実行後:")
    print(f"  agent1 未読メッセージ: {len(agent1.get_received_messages())}")
    print(f"  agent2 未読メッセージ: {len(agent2.get_received_messages())}")
    print(f"  agent3 未読メッセージ: {len(agent3.get_received_messages())}")
    
    # 同じスポット(spot1)にいるagent2はメッセージを受信
    assert len(agent2.get_received_messages()) == 1
    received_msg = agent2.get_received_messages()[0]
    assert received_msg.content == "こんにちは、みなさん！"
    assert received_msg.sender_id == "agent1"
    assert received_msg.spot_id == "spot1"
    
    # 異なるスポット(spot2)にいるagent3はメッセージを受信しない
    assert len(agent3.get_received_messages()) == 0
    
    # 送信者agent1は自分では受信しないが、履歴には残る
    assert len(agent1.get_received_messages()) == 0
    assert len(agent1.get_conversation_history()) == 1
    
    print("✅ 基本的な会話機能テスト完了")


def test_targeted_conversation():
    """特定エージェント宛て会話のテスト"""
    print("\n=== 特定エージェント宛て会話のテスト ===")
    
    world = setup_test_world()
    
    # agent1がagent2に特定のメッセージを送信
    targeted_conversation = Conversation(
        description="ボブに話しかける",
        content="ボブ、元気ですか？",
        target_agent_id="agent2"
    )
    
    message = world.execute_action("agent1", targeted_conversation)
    
    agent1 = world.get_agent("agent1")
    agent2 = world.get_agent("agent2")
    agent3 = world.get_agent("agent3")
    
    print(f"特定メッセージ送信: '{targeted_conversation.content}' (agent1 → agent2)")
    
    # agent2のみがメッセージを受信
    assert len(agent2.get_received_messages()) == 1
    received_msg = agent2.get_received_messages()[0]
    assert received_msg.content == "ボブ、元気ですか？"
    assert received_msg.target_agent_id == "agent2"
    assert received_msg.is_targeted() == True
    
    # 同じスポットにいてもagent3は対象外なので受信しない
    # (現在agent3はspot2にいるため、実際は関係ない)
    
    print(f"agent2が受信したメッセージ: '{received_msg.content}'")
    print("✅ 特定エージェント宛て会話テスト完了")


def test_multi_agent_conversation():
    """複数エージェント間の会話のテスト"""
    print("\n=== 複数エージェント間会話のテスト ===")
    
    world = setup_test_world()
    
    # agent3をspot1に移動させて3人での会話をテスト
    agent3 = world.get_agent("agent3")
    agent3.set_current_spot_id("spot1")
    
    conversations = [
        ("agent1", "こんにちは、みなさん！"),
        ("agent2", "こんにちは、アリス！"),
        ("agent3", "お疲れ様です！"),
        ("agent1", "今日はいい天気ですね"),
    ]
    
    for sender_id, content in conversations:
        conversation = Conversation(
            description=f"{sender_id}が発言",
            content=content
        )
        world.execute_action(sender_id, conversation)
        print(f"{sender_id}: {content}")
    
    # 各エージェントの受信状況を確認
    agent1 = world.get_agent("agent1")
    agent2 = world.get_agent("agent2")
    agent3 = world.get_agent("agent3")
    
    print(f"\n会話後の状況:")
    print(f"  agent1 受信: {len(agent1.get_received_messages())}件")
    print(f"  agent2 受信: {len(agent2.get_received_messages())}件")
    print(f"  agent3 受信: {len(agent3.get_received_messages())}件")
    
    # agent1は自分の2回の発言以外（agent2とagent3の発言）を受信
    assert len(agent1.get_received_messages()) == 2
    
    # agent2は自分の1回の発言以外（agent1とagent3の発言）を受信
    assert len(agent2.get_received_messages()) == 3
    
    # agent3は自分の1回の発言以外（agent1とagent2の発言）を受信
    assert len(agent3.get_received_messages()) == 3
    
    # 会話履歴の確認（自分の発言も含む）
    assert len(agent1.get_conversation_history()) == 4
    assert len(agent2.get_conversation_history()) == 4
    assert len(agent3.get_conversation_history()) == 4
    
    print("✅ 複数エージェント間会話テスト完了")


def test_spot_isolation():
    """スポット間の会話隔離のテスト"""
    print("\n=== スポット間会話隔離のテスト ===")
    
    world = setup_test_world()
    
    # spot1での会話
    conversation1 = Conversation(
        description="spot1で会話",
        content="spot1での秘密の話"
    )
    world.execute_action("agent1", conversation1)
    
    # spot2での会話
    conversation2 = Conversation(
        description="spot2で会話", 
        content="spot2での独り言"
    )
    world.execute_action("agent3", conversation2)
    
    agent1 = world.get_agent("agent1")
    agent2 = world.get_agent("agent2")
    agent3 = world.get_agent("agent3")
    
    print(f"spot1での会話: '{conversation1.content}'")
    print(f"spot2での会話: '{conversation2.content}'")
    
    # spot1の会話はspot1のエージェントのみが受信
    assert len(agent2.get_received_messages()) == 1  # agent2はspot1にいる
    assert agent2.get_received_messages()[0].content == "spot1での秘密の話"
    
    # spot2の会話はspot2のエージェントのみが対象（agent3は送信者なので受信しない）
    assert len(agent3.get_received_messages()) == 0
    
    # agent1とagent3は互いの会話を受信しない
    assert len(agent1.get_received_messages()) == 0
    
    print("✅ スポット間会話隔離テスト完了")


def test_conversation_manager():
    """ConversationManagerのテスト"""
    print("\n=== ConversationManagerのテスト ===")
    
    manager = ConversationManager()
    
    # セッション作成
    session_id = manager.start_conversation_session("spot1", "agent1")
    print(f"会話セッション作成: {session_id}")
    
    # 参加者追加
    manager.join_conversation("agent2", "spot1")
    
    # セッション情報確認
    session = manager.get_active_session_for_spot("spot1")
    assert session is not None
    assert session.spot_id == "spot1"
    assert "agent1" in session.participants
    assert "agent2" in session.participants
    
    print(f"セッション参加者: {session.participants}")
    
    # メッセージ記録
    message = LocationChatMessage("agent1", "spot1", "テストメッセージ")
    recorded_session_id = manager.record_message(message)
    assert recorded_session_id == session_id
    
    # 統計情報
    stats = manager.get_conversation_stats()
    print(f"会話統計: {stats}")
    assert stats["active_sessions"] == 1
    assert stats["total_participants"] == 2
    
    # エージェント離脱
    manager.leave_conversation("agent1")
    manager.leave_conversation("agent2")
    
    # セッション終了確認
    session_after_leave = manager.get_active_session_for_spot("spot1")
    assert session_after_leave is None
    
    print("✅ ConversationManagerテスト完了")


def test_conversation_context():
    """会話コンテキスト取得のテスト"""
    print("\n=== 会話コンテキスト取得のテスト ===")
    
    world = setup_test_world()
    
    # 複数の会話を実行
    conversations = [
        Conversation(description="挨拶", content="こんにちは"),
        Conversation(description="質問", content="調子はどうですか？"),
        Conversation(description="返答", content="ありがとう、元気です")
    ]
    
    for conversation in conversations:
        world.execute_action("agent1", conversation)
    
    agent1 = world.get_agent("agent1")
    context = agent1.get_recent_conversation_context(max_messages=5)
    
    print(f"取得したコンテキスト:")
    print(f"  エージェント: {context['agent_name']}")
    print(f"  現在位置: {context['current_spot_id']}")
    print(f"  最近のメッセージ数: {len(context['recent_messages'])}")
    
    assert context["agent_id"] == "agent1"
    assert context["agent_name"] == "アリス"
    assert context["current_spot_id"] == "spot1"
    assert len(context["recent_messages"]) == 3
    
    print("✅ 会話コンテキスト取得テスト完了")


def run_all_conversation_tests():
    """全ての会話システムテストを実行"""
    print("🎯 会話システム総合テスト開始")
    print("=" * 50)
    
    try:
        test_basic_conversation()
        test_targeted_conversation()
        test_multi_agent_conversation()
        test_spot_isolation()
        test_conversation_manager()
        test_conversation_context()
        
        print("\n" + "=" * 50)
        print("🎉 全ての会話システムテストが成功しました！")
        
    except Exception as e:
        print(f"\n❌ テストエラー: {e}")
        raise


if __name__ == "__main__":
    run_all_conversation_tests() 
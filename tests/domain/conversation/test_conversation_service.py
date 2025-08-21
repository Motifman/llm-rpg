import pytest
from datetime import datetime

from src.domain.player.base_status import BaseStatus
from src.domain.player.dynamic_status import DynamicStatus
from src.domain.player.inventory import Inventory
from src.domain.player.equipment_set import EquipmentSet
from src.domain.player.player_enum import Role
from src.domain.player.player import Player
from src.domain.conversation.conversation_service import ConversationService
from src.domain.conversation.message_box import MessageBox


def make_player(player_id: int, name: str, current_spot_id: int):
    """テスト用のPlayerオブジェクトを作成"""
    base = BaseStatus(attack=10, defense=5, speed=7, critical_rate=0.1, evasion_rate=0.05)
    dyn = DynamicStatus.new_game(max_hp=20, max_mp=10, max_exp=1000, initial_level=1)
    inventory = Inventory.create_empty(20)
    equipment_set = EquipmentSet()
    message_box = MessageBox()
    return Player(
        player_id=player_id,
        name=name,
        role=Role.ADVENTURER,
        current_spot_id=current_spot_id,
        base_status=base,
        dynamic_status=dyn,
        inventory=inventory,
        equipment_set=equipment_set,
        message_box=message_box
    )


class TestConversationService:
    """ConversationServiceクラスのテスト"""
    
    def test_send_message_to_player_success(self):
        """プレイヤー間の正常なメッセージ送信をテスト"""
        # テストデータ
        service = ConversationService()
        sender = make_player(1, "Alice", 100)
        recipient = make_player(2, "Bob", 100)  # 同じスポット
        content = "Hello, Bob!"
        timestamp = datetime.now()
        
        # メッセージ送信
        service.send_message_to_player(sender, recipient, content, timestamp)
        
        # 受信者がメッセージを受け取ったことを確認
        messages = recipient.read_messages()
        expected_display = "Alice: Hello, Bob!"
        assert messages == expected_display
    
    def test_send_message_to_player_same_player_error(self):
        """自分自身にメッセージを送信しようとしてエラーになることをテスト"""
        # テストデータ
        service = ConversationService()
        player = make_player(1, "Alice", 100)
        content = "Hello, myself!"
        timestamp = datetime.now()
        
        # 自分自身にメッセージを送信してエラーになることを確認
        with pytest.raises(ValueError, match="Sender and recipient cannot be the same player"):
            service.send_message_to_player(player, player, content, timestamp)
    
    def test_send_message_to_player_different_spot_error(self):
        """異なるスポットのプレイヤーにメッセージを送信してエラーになることをテスト"""
        # テストデータ
        service = ConversationService()
        sender = make_player(1, "Alice", 100)
        recipient = make_player(2, "Bob", 200)  # 異なるスポット
        content = "Hello, Bob!"
        timestamp = datetime.now()
        
        # 異なるスポットのプレイヤーにメッセージを送信してエラーになることを確認
        with pytest.raises(ValueError, match="Sender and recipient must be in the same spot"):
            service.send_message_to_player(sender, recipient, content, timestamp)
    
    def test_send_message_to_spot_success(self):
        """スポット内の複数プレイヤーへの正常なメッセージ送信をテスト"""
        # テストデータ
        service = ConversationService()
        sender = make_player(1, "Alice", 100)
        recipient1 = make_player(2, "Bob", 100)
        recipient2 = make_player(3, "Charlie", 100)
        recipients = [recipient1, recipient2]
        content = "Hello, everyone!"
        timestamp = datetime.now()
        
        # メッセージ送信
        service.send_message_to_spot(sender, recipients, content, timestamp)
        
        # 全受信者がメッセージを受け取ったことを確認
        messages1 = recipient1.read_messages()
        messages2 = recipient2.read_messages()
        expected_display = "Alice: Hello, everyone!"
        assert messages1 == expected_display
        assert messages2 == expected_display
    
    def test_send_message_to_spot_with_sender_in_recipients(self):
        """送信者が受信者リストに含まれている場合のエラーをテスト"""
        # テストデータ
        service = ConversationService()
        sender = make_player(1, "Alice", 100)
        recipient = make_player(2, "Bob", 100)
        recipients = [sender, recipient]  # 送信者も受信者リストに含む
        content = "Hello, everyone!"
        timestamp = datetime.now()
        
        # 送信者が受信者リストに含まれているとエラーになることを確認
        with pytest.raises(ValueError, match="Sender and recipient cannot be the same player"):
            service.send_message_to_spot(sender, recipients, content, timestamp)
    
    def test_send_message_to_spot_with_different_spot_recipient(self):
        """受信者リストに異なるスポットのプレイヤーが含まれている場合のエラーをテスト"""
        # テストデータ
        service = ConversationService()
        sender = make_player(1, "Alice", 100)
        recipient1 = make_player(2, "Bob", 100)    # 同じスポット
        recipient2 = make_player(3, "Charlie", 200)  # 異なるスポット
        recipients = [recipient1, recipient2]
        content = "Hello, everyone!"
        timestamp = datetime.now()
        
        # 異なるスポットの受信者が含まれているとエラーになることを確認
        with pytest.raises(ValueError, match="Sender and recipient must be in the same spot"):
            service.send_message_to_spot(sender, recipients, content, timestamp)
    
    def test_send_message_to_spot_empty_recipients(self):
        """空の受信者リストでの動作をテスト"""
        # テストデータ
        service = ConversationService()
        sender = make_player(1, "Alice", 100)
        recipients = []  # 空のリスト
        content = "Hello, everyone!"
        timestamp = datetime.now()
        
        # 空のリストでもエラーにならないことを確認（何も起こらない）
        service.send_message_to_spot(sender, recipients, content, timestamp)
        
        # 送信者にメッセージが来ていないことを確認
        messages = sender.read_messages()
        assert messages == ""
    
    def test_send_message_to_spot_single_recipient(self):
        """単一受信者へのスポットメッセージ送信をテスト"""
        # テストデータ
        service = ConversationService()
        sender = make_player(1, "Alice", 100)
        recipient = make_player(2, "Bob", 100)
        recipients = [recipient]
        content = "Hello, Bob!"
        timestamp = datetime.now()
        
        # メッセージ送信
        service.send_message_to_spot(sender, recipients, content, timestamp)
        
        # 受信者がメッセージを受け取ったことを確認
        messages = recipient.read_messages()
        expected_display = "Alice: Hello, Bob!"
        assert messages == expected_display
    
    def test_multiple_messages_to_same_player(self):
        """同じプレイヤーへの複数メッセージ送信をテスト"""
        # テストデータ
        service = ConversationService()
        sender = make_player(1, "Alice", 100)
        recipient = make_player(2, "Bob", 100)
        timestamp = datetime.now()
        
        # 複数のメッセージを送信
        service.send_message_to_player(sender, recipient, "Message 1", timestamp)
        service.send_message_to_player(sender, recipient, "Message 2", timestamp)
        service.send_message_to_player(sender, recipient, "Message 3", timestamp)
        
        # 全メッセージが受信されることを確認
        messages = recipient.read_messages()
        expected_lines = [
            "Alice: Message 1",
            "Alice: Message 2",
            "Alice: Message 3"
        ]
        assert messages == "\n".join(expected_lines)
    
    def test_bidirectional_messaging(self):
        """双方向メッセージ送信をテスト"""
        # テストデータ
        service = ConversationService()
        alice = make_player(1, "Alice", 100)
        bob = make_player(2, "Bob", 100)
        timestamp = datetime.now()
        
        # AliceからBobへ
        service.send_message_to_player(alice, bob, "Hi Bob!", timestamp)
        
        # BobからAliceへ
        service.send_message_to_player(bob, alice, "Hi Alice!", timestamp)
        
        # それぞれがメッセージを受信していることを確認
        alice_messages = alice.read_messages()
        bob_messages = bob.read_messages()
        
        assert alice_messages == "Bob: Hi Alice!"
        assert bob_messages == "Alice: Hi Bob!"
    
    def test_message_ordering_preservation(self):
        """メッセージの順序が保持されることをテスト"""
        # テストデータ
        service = ConversationService()
        sender1 = make_player(1, "Alice", 100)
        sender2 = make_player(2, "Bob", 100)
        recipient = make_player(3, "Charlie", 100)
        timestamp = datetime.now()
        
        # 異なる送信者から順番にメッセージを送信
        service.send_message_to_player(sender1, recipient, "First message", timestamp)
        service.send_message_to_player(sender2, recipient, "Second message", timestamp)
        service.send_message_to_player(sender1, recipient, "Third message", timestamp)
        
        # メッセージの順序が保持されることを確認
        messages = recipient.read_messages()
        expected_lines = [
            "Alice: First message",
            "Bob: Second message",
            "Alice: Third message"
        ]
        assert messages == "\n".join(expected_lines)

import pytest
import uuid
from datetime import datetime
from src.domain.player.message import Message


class TestMessage:
    """Messageクラスのテスト"""
    
    def test_create_message_success(self):
        """メッセージの正常な作成をテスト"""
        # テストデータ
        sender_id = 1
        sender_name = "Alice"
        recipient_id = 2
        content = "Hello, World!"
        timestamp = datetime.now()
        
        # メッセージ作成
        message = Message.create(
            sender_id=sender_id,
            sender_name=sender_name,
            recipient_id=recipient_id,
            content=content,
            timestamp=timestamp
        )
        
        # アサーション
        assert message.sender_id == sender_id
        assert message.sender_name == sender_name
        assert message.recipient_id == recipient_id
        assert message.content == content
        assert message.timestamp == timestamp
        assert isinstance(message.message_id, uuid.UUID)
    
    def test_create_message_empty_content(self):
        """空のメッセージ内容でエラーが発生することをテスト"""
        # テストデータ
        sender_id = 1
        sender_name = "Alice"
        recipient_id = 2
        content = ""  # 空のコンテンツ
        timestamp = datetime.now()
        
        # エラーが発生することを確認
        with pytest.raises(ValueError, match="メッセージ内容は空にできません。"):
            Message.create(
                sender_id=sender_id,
                sender_name=sender_name,
                recipient_id=recipient_id,
                content=content,
                timestamp=timestamp
            )
    
    def test_create_message_none_content(self):
        """Noneのメッセージ内容でエラーが発生することをテスト"""
        # テストデータ
        sender_id = 1
        sender_name = "Alice"
        recipient_id = 2
        content = None  # Noneのコンテンツ
        timestamp = datetime.now()
        
        # エラーが発生することを確認
        with pytest.raises(ValueError, match="メッセージ内容は空にできません。"):
            Message.create(
                sender_id=sender_id,
                sender_name=sender_name,
                recipient_id=recipient_id,
                content=content,
                timestamp=timestamp
            )
    
    def test_display_message(self):
        """メッセージ表示のテスト"""
        # テストデータ
        sender_id = 1
        sender_name = "Alice"
        recipient_id = 2
        content = "Hello, World!"
        timestamp = datetime.now()
        
        # メッセージ作成
        message = Message.create(
            sender_id=sender_id,
            sender_name=sender_name,
            recipient_id=recipient_id,
            content=content,
            timestamp=timestamp
        )
        
        # 表示確認
        expected_display = f"{sender_name}: {content}"
        assert message.display() == expected_display
    
    def test_message_immutability(self):
        """メッセージが不変であることをテスト"""
        # テストデータ
        sender_id = 1
        sender_name = "Alice"
        recipient_id = 2
        content = "Hello, World!"
        timestamp = datetime.now()
        
        # メッセージ作成
        message = Message.create(
            sender_id=sender_id,
            sender_name=sender_name,
            recipient_id=recipient_id,
            content=content,
            timestamp=timestamp
        )
        
        # 属性の変更を試行してエラーになることを確認
        with pytest.raises(Exception):  # frozenデータクラスなので変更不可
            message.content = "Modified content"
    
    def test_create_message_with_different_ids(self):
        """異なるIDでメッセージを作成できることをテスト"""
        # テストデータ
        sender_id = 10
        sender_name = "Bob"
        recipient_id = 20
        content = "Test message"
        timestamp = datetime.now()
        
        # メッセージ作成
        message = Message.create(
            sender_id=sender_id,
            sender_name=sender_name,
            recipient_id=recipient_id,
            content=content,
            timestamp=timestamp
        )
        
        # アサーション
        assert message.sender_id == 10
        assert message.recipient_id == 20
        assert message.sender_name == "Bob"
        assert message.content == "Test message"
    
    def test_message_id_uniqueness(self):
        """複数のメッセージで異なるIDが生成されることをテスト"""
        # テストデータ
        timestamp = datetime.now()
        
        # 複数のメッセージを作成
        message1 = Message.create(1, "Alice", 2, "Message 1", timestamp)
        message2 = Message.create(1, "Alice", 2, "Message 2", timestamp)
        
        # IDが異なることを確認
        assert message1.message_id != message2.message_id

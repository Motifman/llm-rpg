import pytest
from datetime import datetime
from src.domain.conversation.message_box import MessageBox
from src.domain.conversation.message import Message


class TestMessageBox:
    """MessageBoxクラスのテスト"""
    
    def test_create_empty_message_box(self):
        """空のメッセージボックスの作成をテスト"""
        message_box = MessageBox()
        
        # 初期状態は空であることを確認
        assert len(message_box.messages) == 0
    
    def test_append_single_message(self):
        """単一メッセージの追加をテスト"""
        # テストデータ
        message_box = MessageBox()
        timestamp = datetime.now()
        message = Message.create(1, "Alice", 2, "Hello", timestamp)
        
        # メッセージを追加
        message_box.append(message)
        
        # アサーション
        assert len(message_box.messages) == 1
        assert message_box.messages[0] == message
    
    def test_append_multiple_messages(self):
        """複数メッセージの追加をテスト"""
        # テストデータ
        message_box = MessageBox()
        timestamp = datetime.now()
        message1 = Message.create(1, "Alice", 2, "Hello", timestamp)
        message2 = Message.create(2, "Bob", 1, "Hi there", timestamp)
        message3 = Message.create(1, "Alice", 2, "How are you?", timestamp)
        
        # メッセージを追加
        message_box.append(message1)
        message_box.append(message2)
        message_box.append(message3)
        
        # アサーション
        assert len(message_box.messages) == 3
        assert message_box.messages[0] == message1
        assert message_box.messages[1] == message2
        assert message_box.messages[2] == message3
    
    def test_read_all_empty_box(self):
        """空のメッセージボックスからの読み取りをテスト"""
        message_box = MessageBox()
        
        # 読み取り
        messages = message_box.read_all()
        
        # アサーション
        assert len(messages) == 0
        assert len(message_box.messages) == 0  # 元のボックスも空のまま
    
    def test_read_all_with_messages(self):
        """メッセージ有りボックスからの読み取りをテスト"""
        # テストデータ
        message_box = MessageBox()
        timestamp = datetime.now()
        message1 = Message.create(1, "Alice", 2, "Hello", timestamp)
        message2 = Message.create(2, "Bob", 1, "Hi there", timestamp)
        
        # メッセージを追加
        message_box.append(message1)
        message_box.append(message2)
        
        # 読み取り前の状態確認
        assert len(message_box.messages) == 2
        
        # 読み取り
        messages = message_box.read_all()
        
        # アサーション
        assert len(messages) == 2
        assert messages[0] == message1
        assert messages[1] == message2
        
        # 読み取り後はボックスがクリアされることを確認
        assert len(message_box.messages) == 0
    
    def test_read_all_twice(self):
        """連続での読み取りをテスト"""
        # テストデータ
        message_box = MessageBox()
        timestamp = datetime.now()
        message = Message.create(1, "Alice", 2, "Hello", timestamp)
        
        # メッセージを追加
        message_box.append(message)
        
        # 1回目の読み取り
        messages1 = message_box.read_all()
        assert len(messages1) == 1
        assert messages1[0] == message
        assert len(message_box.messages) == 0
        
        # 2回目の読み取り
        messages2 = message_box.read_all()
        assert len(messages2) == 0
        assert len(message_box.messages) == 0
    
    def test_append_after_read_all(self):
        """読み取り後の新しいメッセージ追加をテスト"""
        # テストデータ
        message_box = MessageBox()
        timestamp = datetime.now()
        message1 = Message.create(1, "Alice", 2, "Hello", timestamp)
        message2 = Message.create(2, "Bob", 1, "Hi", timestamp)
        
        # 最初のメッセージを追加して読み取り
        message_box.append(message1)
        messages1 = message_box.read_all()
        assert len(messages1) == 1
        assert len(message_box.messages) == 0
        
        # 新しいメッセージを追加
        message_box.append(message2)
        assert len(message_box.messages) == 1
        assert message_box.messages[0] == message2
        
        # 再度読み取り
        messages2 = message_box.read_all()
        assert len(messages2) == 1
        assert messages2[0] == message2
        assert len(message_box.messages) == 0
    
    def test_message_order_preservation(self):
        """メッセージの順序が保持されることをテスト"""
        # テストデータ
        message_box = MessageBox()
        timestamp = datetime.now()
        
        # 順番に複数のメッセージを追加
        messages = []
        for i in range(5):
            message = Message.create(1, f"User{i}", 2, f"Message {i}", timestamp)
            messages.append(message)
            message_box.append(message)
        
        # 読み取り
        read_messages = message_box.read_all()
        
        # 順序が保持されていることを確認
        assert len(read_messages) == 5
        for i in range(5):
            assert read_messages[i] == messages[i]
            assert read_messages[i].content == f"Message {i}"
    
    def test_message_box_independence(self):
        """複数のメッセージボックスが独立していることをテスト"""
        # 2つのメッセージボックスを作成
        box1 = MessageBox()
        box2 = MessageBox()
        
        timestamp = datetime.now()
        message1 = Message.create(1, "Alice", 2, "Box1 message", timestamp)
        message2 = Message.create(2, "Bob", 1, "Box2 message", timestamp)
        
        # それぞれに異なるメッセージを追加
        box1.append(message1)
        box2.append(message2)
        
        # それぞれのボックスが独立していることを確認
        assert len(box1.messages) == 1
        assert len(box2.messages) == 1
        assert box1.messages[0] == message1
        assert box2.messages[0] == message2
        
        # box1を読み取りしてもbox2に影響しないことを確認
        box1_messages = box1.read_all()
        assert len(box1_messages) == 1
        assert len(box1.messages) == 0  # box1はクリア
        assert len(box2.messages) == 1  # box2は変わらず

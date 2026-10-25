from datetime import datetime

import pytest

from ai_rpg_world.domain.player.exception import MessageValidationException
from ai_rpg_world.domain.player.value_object.message import Message


class TestMessage:
    """Message値オブジェクトのテスト"""

    def test_create_success(self):
        """正常作成のテスト"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        message = Message.create(
            message_id=1,
            sender_id=10,
            sender_name="Alice",
            recipient_id=20,
            content="Hello, World!",
            timestamp=timestamp,
        )

        assert message.message_id == 1
        assert message.sender_id == 10
        assert message.sender_name == "Alice"
        assert message.recipient_id == 20
        assert message.content == "Hello, World!"
        assert message.timestamp == timestamp

    def test_create_with_whitespace_content(self):
        """前後に空白のあるコンテンツの場合、トリムされる"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        message = Message.create(
            message_id=1,
            sender_id=10,
            sender_name="  Alice  ",
            recipient_id=20,
            content="  Hello, World!  ",
            timestamp=timestamp,
        )

        assert message.sender_name == "Alice"
        assert message.content == "Hello, World!"

    def test_direct_instantiation_zero_message_id(self):
        """message_idが0なら専用の理由付き例外で拒否する。"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        with pytest.raises(MessageValidationException, match="メッセージIDは正の数値である必要があります"):
            Message(0, 10, "Alice", 20, "Hello", timestamp)

    def test_direct_instantiation_zero_sender_id(self):
        """sender_idが0なら専用の理由付き例外で拒否する。"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        with pytest.raises(MessageValidationException, match="送信者IDは正の数値である必要があります"):
            Message(1, 0, "Alice", 20, "Hello", timestamp)

    def test_direct_instantiation_empty_sender_name(self):
        """sender_nameが空の場合"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        with pytest.raises(MessageValidationException, match="送信者名は空にできません"):
            Message(1, 10, "", 20, "Hello", timestamp)

    def test_direct_instantiation_whitespace_sender_name(self):
        """sender_nameが空白のみの場合"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        with pytest.raises(MessageValidationException, match="送信者名は空にできません"):
            Message(1, 10, "   ", 20, "Hello", timestamp)

    def test_direct_instantiation_zero_recipient_id(self):
        """recipient_idが0なら専用の理由付き例外で拒否する。"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        with pytest.raises(MessageValidationException, match="受信者IDは正の数値である必要があります"):
            Message(1, 10, "Alice", 0, "Hello", timestamp)

    def test_direct_instantiation_empty_content(self):
        """contentが空の場合"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        with pytest.raises(MessageValidationException, match="メッセージ内容は空にできません"):
            Message(1, 10, "Alice", 20, "", timestamp)

    def test_direct_instantiation_whitespace_content(self):
        """contentが空白のみの場合"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        with pytest.raises(MessageValidationException, match="メッセージ内容は空にできません"):
            Message(1, 10, "Alice", 20, "   ", timestamp)

    def test_direct_instantiation_content_too_long(self):
        """contentが1000文字を超える場合"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        long_content = "A" * 1001
        with pytest.raises(MessageValidationException, match="メッセージ内容は1000文字以内である必要があります"):
            Message(1, 10, "Alice", 20, long_content, timestamp)

    def test_direct_instantiation_self_message(self):
        """自分自身へのメッセージの場合"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        with pytest.raises(MessageValidationException, match="自分自身へのメッセージ送信はできません"):
            Message(1, 10, "Alice", 10, "Hello", timestamp)

    def test_display(self):
        """表示メソッドのテスト"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        message = Message.create(1, 10, "Alice", 20, "Hello, World!", timestamp)
        assert message.display() == "Alice: Hello, World!"

    def test_get_content_length(self):
        """コンテンツ長取得のテスト"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        message = Message.create(1, 10, "Alice", 20, "Hello, World!", timestamp)
        assert message.get_content_length() == 13

    def test_is_from_player(self):
        """送信者チェックのテスト"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        message = Message.create(1, 10, "Alice", 20, "Hello", timestamp)

        assert message.is_from_player(10) == True
        assert message.is_from_player(20) == False
        assert message.is_from_player(30) == False

    def test_is_to_player(self):
        """受信者チェックのテスト"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        message = Message.create(1, 10, "Alice", 20, "Hello", timestamp)

        assert message.is_to_player(20) == True
        assert message.is_to_player(10) == False
        assert message.is_to_player(30) == False

    def test_string_representation(self):
        """文字列表示のテスト"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        message = Message.create(1, 10, "Alice", 20, "Hello, World!", timestamp)
        expected = "Message(id=1, from=Alice, to_player=20, content='Hello, World!')"
        assert str(message) == expected

    def test_string_representation_long_content(self):
        """長いコンテンツの文字列表示のテスト"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        long_content = "A" * 60
        message = Message.create(1, 10, "Alice", 20, long_content, timestamp)
        expected = f"Message(id=1, from=Alice, to_player=20, content='{'A' * 50}...')"
        assert str(message) == expected

    @pytest.mark.parametrize(
        "different_fields",
        [
            (2, 10, "Alice", 20, "Hello", datetime(2024, 1, 1, 12, 0, 0)),
            (1, 15, "Alice", 20, "Hello", datetime(2024, 1, 1, 12, 0, 0)),
            (1, 10, "Bob", 20, "Hello", datetime(2024, 1, 1, 12, 0, 0)),
            (1, 10, "Alice", 30, "Hello", datetime(2024, 1, 1, 12, 0, 0)),
            (1, 10, "Alice", 20, "Goodbye", datetime(2024, 1, 1, 12, 0, 0)),
            (1, 10, "Alice", 20, "Hello", datetime(2024, 1, 2, 12, 0, 0)),
        ],
        ids=["message-id", "sender-id", "sender-name", "recipient-id", "content", "timestamp"],
    )
    def test_equality(self, different_fields):
        """全項目が同じ値は同値で、どの1項目が違っても同値にはならない。"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        message1 = Message.create(1, 10, "Alice", 20, "Hello", timestamp)
        message2 = Message.create(1, 10, "Alice", 20, "Hello", timestamp)
        message3 = Message.create(2, 10, "Alice", 20, "Hello", timestamp)
        message4 = Message.create(1, 15, "Alice", 20, "Hello", timestamp)

        assert message1 == message2
        assert message1 != message3
        assert message1 != message4
        assert message1 != "not message"
        assert message1 != Message.create(*different_fields)

    def test_hash(self):
        """ハッシュ値のテスト"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        message1 = Message.create(1, 10, "Alice", 20, "Hello", timestamp)
        message2 = Message.create(1, 10, "Alice", 20, "Hello", timestamp)
        message3 = Message.create(2, 10, "Alice", 20, "Hello", timestamp)

        assert hash(message1) == hash(message2)

        # setで使用可能
        message_set = {message1, message2, message3}
        assert len(message_set) == 2
        assert message2 in message_set
        assert message3 in message_set

    @pytest.mark.parametrize(
        ("field", "replacement"),
        [
            ("message_id", 2),
            ("sender_id", 15),
            ("sender_name", "Bob"),
            ("recipient_id", 30),
            ("content", "Changed"),
            ("timestamp", datetime(2024, 1, 2, 12, 0, 0)),
        ],
    )
    def test_immutability(self, field, replacement):
        """読取操作は値を変えず、公開項目への外部代入は拒否して全項目を保持する。"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        message1 = Message.create(1, 10, "Alice", 20, "Hello", timestamp)

        # メソッド呼び出し後も元のインスタンスは変更されないことを確認
        message1.display()
        message1.get_content_length()
        message1.is_from_player(10)

        with pytest.raises(AttributeError):
            setattr(message1, field, replacement)

        assert message1.message_id == 1
        assert message1.sender_id == 10
        assert message1.sender_name == "Alice"
        assert message1.recipient_id == 20
        assert message1.content == "Hello"
        assert message1.timestamp == timestamp

    def test_content_length_boundary(self):
        """コンテンツ長の境界値テスト"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)

        # 1000文字はOK
        content_1000 = "A" * 1000
        message = Message.create(1, 10, "Alice", 20, content_1000, timestamp)
        assert message.content == content_1000

        # 1001文字はNG
        content_1001 = "A" * 1001
        with pytest.raises(MessageValidationException):
            Message.create(1, 10, "Alice", 20, content_1001, timestamp)

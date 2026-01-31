from dataclasses import dataclass
from datetime import datetime
from typing import Union
from ai_rpg_world.domain.player.exception import MessageValidationException


@dataclass(frozen=True)
class Message:
    """メッセージ値オブジェクト

    プレイヤー間のメッセージを表します。
    メッセージID、送信者情報、受信者情報、内容、タイムスタンプを持ちます。
    """
    message_id: int
    sender_id: int
    sender_name: str
    recipient_id: int
    content: str
    timestamp: datetime

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if self.message_id <= 0:
            raise MessageValidationException(f"メッセージIDは正の数値である必要があります。message_id: {self.message_id}")
        if self.sender_id <= 0:
            raise MessageValidationException(f"送信者IDは正の数値である必要があります。sender_id: {self.sender_id}")
        if not self.sender_name or not self.sender_name.strip():
            raise MessageValidationException(f"送信者名は空にできません。sender_name: '{self.sender_name}'")
        if self.recipient_id <= 0:
            raise MessageValidationException(f"受信者IDは正の数値である必要があります。recipient_id: {self.recipient_id}")
        if not self.content or not self.content.strip():
            raise MessageValidationException(f"メッセージ内容は空にできません。content: '{self.content}'")
        if len(self.content.strip()) > 1000:
            raise MessageValidationException(f"メッセージ内容は1000文字以内である必要があります。現在の長さ: {len(self.content)}")

        # 自分自身へのメッセージ送信を禁止
        if self.sender_id == self.recipient_id:
            raise MessageValidationException(f"自分自身へのメッセージ送信はできません。sender_id: {self.sender_id}, recipient_id: {self.recipient_id}")

    @classmethod
    def create(
        cls,
        message_id: int,
        sender_id: int,
        sender_name: str,
        recipient_id: int,
        content: str,
        timestamp: datetime
    ) -> "Message":
        """メッセージを作成するファクトリメソッド

        Args:
            message_id: メッセージID
            sender_id: 送信者ID
            sender_name: 送信者名
            recipient_id: 受信者ID
            content: メッセージ内容（1〜1000文字）
            timestamp: 送信時刻

        Returns:
            Message: メッセージ値オブジェクト

        Raises:
            MessageValidationException: バリデーションエラー時
        """
        # コンテンツの前後空白を除去
        cleaned_content = content.strip()
        cleaned_sender_name = sender_name.strip()

        return cls(
            message_id=message_id,
            sender_id=sender_id,
            sender_name=cleaned_sender_name,
            recipient_id=recipient_id,
            content=cleaned_content,
            timestamp=timestamp
        )

    def display(self) -> str:
        """表示用のメッセージ文字列を取得

        Returns:
            str: "送信者名: メッセージ内容"の形式
        """
        return f"{self.sender_name}: {self.content}"

    def get_content_length(self) -> int:
        """メッセージ内容の長さを取得

        Returns:
            int: メッセージ内容の文字数
        """
        return len(self.content)

    def is_from_player(self, player_id: int) -> bool:
        """指定されたプレイヤーからのメッセージかどうか

        Args:
            player_id: プレイヤーID

        Returns:
            bool: 指定されたプレイヤーからのメッセージの場合True
        """
        return self.sender_id == player_id

    def is_to_player(self, player_id: int) -> bool:
        """指定されたプレイヤー宛のメッセージかどうか

        Args:
            player_id: プレイヤーID

        Returns:
            bool: 指定されたプレイヤー宛のメッセージの場合True
        """
        return self.recipient_id == player_id

    def __str__(self) -> str:
        """文字列としてのメッセージ"""
        return f"Message(id={self.message_id}, from={self.sender_name}, to_player={self.recipient_id}, content='{self.content[:50]}{'...' if len(self.content) > 50 else ''}')"

    def __eq__(self, other: object) -> bool:
        """等価性比較"""
        if not isinstance(other, Message):
            return NotImplemented
        return (
            self.message_id == other.message_id
            and self.sender_id == other.sender_id
            and self.sender_name == other.sender_name
            and self.recipient_id == other.recipient_id
            and self.content == other.content
            and self.timestamp == other.timestamp
        )

    def __hash__(self) -> int:
        """ハッシュ値"""
        return hash((
            self.message_id,
            self.sender_id,
            self.sender_name,
            self.recipient_id,
            self.content,
            self.timestamp,
        ))
from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Set
from src.domain.common.domain_event import DomainEvent
from src.domain.sns.mention import Mention
from src.domain.sns.post_content import PostContent


@dataclass(frozen=True)
class BaseSnsCreatedEvent(DomainEvent, ABC):
    """SNSコンテンツ作成イベントの基底クラス"""
    author_user_id: int = -1
    content: str = ""
    mentions: Set[Mention] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class BaseSnsLikedEvent(DomainEvent, ABC):
    """SNSコンテンツいいねイベントの基底クラス"""
    target_id: int = -1  # post_id or reply_id
    user_id: int = -1    # いいねしたユーザー
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class BaseSnsDeletedEvent(DomainEvent, ABC):
    """SNSコンテンツ削除イベントの基底クラス"""
    target_id: int = -1  # post_id or reply_id
    author_user_id: int = -1
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class BaseSnsMentionedEvent(DomainEvent, ABC):
    """メンションイベントの基底クラス"""
    mentioned_user_names: Set[str] = field(default_factory=set)
    mentioned_by_user_id: int = -1
    target_id: int = -1  # post_id or reply_id
    created_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class BaseSnsUserInteractionEvent(DomainEvent, ABC):
    """ユーザー間インタラクションイベントの基底クラス"""
    from_user_id: int = -1  # アクションを実行したユーザー
    to_user_id: int = -1    # アクションの対象ユーザー
    created_at: datetime = field(default_factory=datetime.now)


# 具体的なイベントクラス（統合版）
@dataclass(frozen=True)
class SnsContentCreatedEvent(BaseSnsCreatedEvent):
    """汎用コンテンツ作成イベント（ポスト・リプライ共通）"""
    target_id: int = -1  # post_id or reply_id
    parent_post_id: Optional[int] = None
    parent_reply_id: Optional[int] = None
    content_type: str = "post"  # "post" or "reply"


@dataclass(frozen=True)
class SnsContentLikedEvent(BaseSnsLikedEvent):
    """汎用コンテンツいいねイベント"""
    content_type: str = "post"  # "post" or "reply"
    content_author_id: int = -1  # コンテンツの作成者


@dataclass(frozen=True)
class SnsContentDeletedEvent(BaseSnsDeletedEvent):
    """汎用コンテンツ削除イベント"""
    content_type: str = "post"  # "post" or "reply"


@dataclass(frozen=True)
class SnsUserFollowedEvent(BaseSnsUserInteractionEvent):
    """ユーザーフォローイベント"""
    pass


@dataclass(frozen=True)
class SnsUserBlockedEvent(BaseSnsUserInteractionEvent):
    """ユーザーブロックイベント"""
    pass


@dataclass(frozen=True)
class SnsUserSubscribedEvent(BaseSnsUserInteractionEvent):
    """ユーザーサブスクライブイベント"""
    pass


@dataclass(frozen=True)
class SnsUserUnsubscribedEvent(BaseSnsUserInteractionEvent):
    """ユーザーアンサブスクライブイベント"""
    pass

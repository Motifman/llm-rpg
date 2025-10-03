from dataclasses import dataclass
from typing import Optional
from src.domain.sns.value_object.user_id import UserId
from src.domain.sns.value_object.post_id import PostId
from src.domain.sns.value_object.reply_id import ReplyId
from src.domain.sns.exception import (
    NotificationContentValidationException,
    PostIdValidationException,
    ReplyIdValidationException
)


@dataclass(frozen=True)
class NotificationContent:
    """通知内容"""

    # 通知のタイトルと本文
    title: str
    message: str

    # アクションを実行したユーザー情報
    actor_user_id: UserId
    actor_user_name: str

    # 関連するコンテンツ情報（ポストIDまたはリプライID）
    related_post_id: Optional[PostId] = None
    related_reply_id: Optional[ReplyId] = None

    # コンテンツタイプ（post/reply）
    content_type: Optional[str] = None

    # 関連コンテンツの本文（ポストやリプライの内容）
    content_text: Optional[str] = None

    @classmethod
    def create_follow_notification(
        cls,
        follower_user_id: UserId,
        follower_user_name: str
    ) -> "NotificationContent":
        """フォロー通知の作成"""
        return cls(
            title="新しいフォロワー",
            message=f"{follower_user_name}さんがあなたをフォローしました",
            actor_user_id=follower_user_id,
            actor_user_name=follower_user_name
        )

    @classmethod
    def create_subscribe_notification(
        cls,
        subscriber_user_id: UserId,
        subscriber_user_name: str
    ) -> "NotificationContent":
        """サブスクライブ通知の作成"""
        return cls(
            title="新しい購読者",
            message=f"{subscriber_user_name}さんがあなたの投稿を購読しました",
            actor_user_id=subscriber_user_id,
            actor_user_name=subscriber_user_name
        )

    @classmethod
    def create_like_notification(
        cls,
        liker_user_id: UserId,
        liker_user_name: str,
        content_type: str,
        content_id: int,
        content_text: Optional[str] = None
    ) -> "NotificationContent":
        """いいね通知の作成"""
        if content_type not in ["post", "reply"]:
            raise NotificationContentValidationException(
                f"content_typeは「post」または「reply」である必要があります。入力値: {content_type}"
            )

        try:
            content_id_obj = PostId(content_id) if content_type == "post" else ReplyId(content_id)
        except (PostIdValidationException, ReplyIdValidationException) as e:
            raise NotificationContentValidationException(
                f"無効なcontent_idです: {content_id}"
            ) from e

        return cls(
            title="いいね",
            message=f"{liker_user_name}さんがあなたの{content_type}にいいねしました",
            actor_user_id=liker_user_id,
            actor_user_name=liker_user_name,
            related_post_id=content_id_obj if content_type == "post" else None,
            related_reply_id=content_id_obj if content_type == "reply" else None,
            content_type=content_type,
            content_text=content_text
        )

    @classmethod
    def create_mention_notification(
        cls,
        mentioner_user_id: UserId,
        mentioner_user_name: str,
        content_type: str,
        content_id: int,
        content_text: Optional[str] = None
    ) -> "NotificationContent":
        """メンション通知の作成"""
        if content_type not in ["post", "reply"]:
            raise NotificationContentValidationException(
                f"content_typeは「post」または「reply」である必要があります。入力値: {content_type}"
            )

        try:
            content_id_obj = PostId(content_id) if content_type == "post" else ReplyId(content_id)
        except (PostIdValidationException, ReplyIdValidationException) as e:
            raise NotificationContentValidationException(
                f"無効なcontent_idです: {content_id}"
            ) from e

        return cls(
            title="メンション",
            message=f"{mentioner_user_name}さんが{content_type}であなたをメンションしました",
            actor_user_id=mentioner_user_id,
            actor_user_name=mentioner_user_name,
            related_post_id=content_id_obj if content_type == "post" else None,
            related_reply_id=content_id_obj if content_type == "reply" else None,
            content_type=content_type,
            content_text=content_text
        )

    @classmethod
    def create_reply_notification(
        cls,
        replier_user_id: UserId,
        replier_user_name: str,
        content_type: str,
        content_id: int,
        content_text: Optional[str] = None
    ) -> "NotificationContent":
        """返信通知の作成"""
        if content_type not in ["post", "reply"]:
            raise NotificationContentValidationException(
                f"content_typeは「post」または「reply」である必要があります。入力値: {content_type}"
            )

        try:
            content_id_obj = PostId(content_id) if content_type == "post" else ReplyId(content_id)
        except (PostIdValidationException, ReplyIdValidationException) as e:
            raise NotificationContentValidationException(
                f"無効なcontent_idです: {content_id}"
            ) from e

        return cls(
            title="新しい返信",
            message=f"{replier_user_name}さんがあなたの{content_type}に返信しました",
            actor_user_id=replier_user_id,
            actor_user_name=replier_user_name,
            related_post_id=content_id_obj if content_type == "post" else None,
            related_reply_id=content_id_obj if content_type == "reply" else None,
            content_type=content_type,
            content_text=content_text
        )

    @classmethod
    def create_post_notification(
        cls,
        author_user_id: UserId,
        author_user_name: str,
        content_text: str
    ) -> "NotificationContent":
        """投稿通知の作成"""
        return cls(
            title="新しいポスト",
            message=f"{author_user_name}さんがポストしました",
            actor_user_id=author_user_id,
            actor_user_name=author_user_name,
            content_text=content_text
        )

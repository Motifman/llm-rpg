from src.domain.sns.aggregate.post_aggregate import PostAggregate
from src.domain.sns.value_object.user_id import UserId
from src.domain.sns.aggregate.user_aggregate import UserAggregate
from src.domain.sns.enum.sns_enum import PostVisibility


class PostVisibilityDomainService:
    @staticmethod
    def can_view_post(post: PostAggregate, viewer_user: UserAggregate, author_user: UserAggregate) -> bool:
        """ポストの閲覧権限をチェック"""
        # ポストが削除されている場合
        if post.deleted:
            return False
        
        # 自分のポストは常に閲覧可能
        if author_user.user_id == viewer_user.user_id:
            return True
            
        # ブロック関係のチェック（双方向）
        if viewer_user.is_blocked(author_user.user_id) or author_user.is_blocked(viewer_user.user_id):
            return False
            
        # 可視性のチェック
        if post.post_content.visibility == PostVisibility.PRIVATE:
            return False
        elif post.post_content.visibility == PostVisibility.FOLLOWERS_ONLY:
            return viewer_user.is_following(author_user.user_id)  # 閲覧者がポストの主をフォローしているか

        return True  # PUBLICの場合
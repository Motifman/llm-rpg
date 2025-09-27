from src.domain.sns.aggregate.post_aggregate import PostAggregate
from src.domain.sns.value_object.user_id import UserId
from src.domain.sns.aggregate.user_aggregate import UserAggregate
from src.domain.sns.enum.sns_enum import PostVisibility


class PostVisibilityDomainService:
    def can_view_post(self, post: PostAggregate, viewer_user: UserAggregate, author_user: UserAggregate) -> bool:
        """ポストの閲覧権限をチェック"""
        # 自分のポストは常に閲覧可能
        if author_user.user_id == viewer_user.user_id:
            return True
            
        # ブロック関係のチェック
        if viewer_user.is_blocked(author_user.user_id):
            return False
            
        # 可視性のチェック
        if post.visibility == PostVisibility.PRIVATE:
            return False
        elif post.visibility == PostVisibility.FOLLOWERS_ONLY:
            return author_user.is_following(viewer_user.user_id)  # ポストの主が閲覧者をフォローしているか
            
        return True  # PUBLICの場合
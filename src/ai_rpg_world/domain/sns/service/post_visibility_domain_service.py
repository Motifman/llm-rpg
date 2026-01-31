from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from ai_rpg_world.domain.sns.value_object.user_id import UserId
from ai_rpg_world.domain.sns.aggregate.user_aggregate import UserAggregate
from ai_rpg_world.domain.sns.enum.sns_enum import PostVisibility


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

    @staticmethod
    def can_view_reply(reply: ReplyAggregate, viewer_user: UserAggregate, author_user: UserAggregate, parent_post: PostAggregate = None) -> bool:
        """リプライの閲覧権限をチェック"""
        # リプライが削除されている場合
        if reply.deleted:
            return False

        # 自分のリプライは常に閲覧可能
        if author_user.user_id == viewer_user.user_id:
            return True

        # ブロック関係のチェック（双方向）
        if viewer_user.is_blocked(author_user.user_id) or author_user.is_blocked(viewer_user.user_id):
            return False

        # リプライの可視性をチェック
        visibility = reply.content.visibility

        if visibility == PostVisibility.PRIVATE:
            # プライベートリプライは作成者のみ閲覧可能
            return author_user.user_id == viewer_user.user_id
        elif visibility == PostVisibility.FOLLOWERS_ONLY:
            # フォロワー限定リプライはフォロワーだけが閲覧可能
            return viewer_user.is_following(author_user.user_id)

        return True  # PUBLICの場合

    @staticmethod
    def can_view_deleted_post_for_reply_thread(post: PostAggregate, viewer_user: UserAggregate, author_user: UserAggregate) -> bool:
        """リプライツリー表示のために削除されたポストを表示できるかどうか"""
        # 自分の削除したポストは表示可能
        if author_user.user_id == viewer_user.user_id:
            return True

        # ブロック関係のチェック（双方向）
        if viewer_user.is_blocked(author_user.user_id) or author_user.is_blocked(viewer_user.user_id):
            return False

        return True

    @staticmethod
    def can_view_deleted_reply_for_thread(reply: ReplyAggregate, viewer_user: UserAggregate, author_user: UserAggregate) -> bool:
        """リプライツリー表示のために削除されたリプライを表示できるかどうか"""
        # 自分の削除したリプライは表示可能
        if author_user.user_id == viewer_user.user_id:
            return True

        # ブロック関係のチェック（双方向）
        if viewer_user.is_blocked(author_user.user_id) or author_user.is_blocked(viewer_user.user_id):
            return False

        return True
"""
InMemoryReplyRepository - ReplyAggregateを使用するインメモリ実装
"""
from typing import List, Optional, Dict, Set, Union
from datetime import datetime, timedelta
import random
from src.domain.sns.repository.reply_repository import ReplyRepository
from src.domain.sns.aggregate.reply_aggregate import ReplyAggregate
from src.domain.sns.value_object.post_content import PostContent
from src.domain.sns.value_object.post_id import PostId
from src.domain.sns.value_object.reply_id import ReplyId
from src.domain.sns.value_object.user_id import UserId
from src.domain.sns.value_object.like import Like
from src.domain.sns.value_object.mention import Mention
from src.domain.sns.enum.sns_enum import PostVisibility


class InMemoryReplyRepository(ReplyRepository):
    """ReplyAggregateを使用するインメモリリポジトリ"""

    def __init__(self):
        self._replies: Dict[ReplyId, ReplyAggregate] = {}
        self._next_reply_id = ReplyId(1)

        # サンプルリプライデータを作成
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプルリプライデータのセットアップ"""
        # 現在の時間を基準に過去のリプライを作成
        base_time = datetime.now()

        # リプライ1: ポスト1（勇者の冒険開始ポスト）へのリプライ
        reply1_content = PostContent(
            content="一緒に冒険に行きたい！ 僕も手伝うよ。",
            hashtags=("冒険", "協力"),
            visibility=PostVisibility.PUBLIC
        )
        reply1_created_at = base_time - timedelta(hours=1, minutes=45)
        reply1 = ReplyAggregate(
            ReplyId(1), UserId(2), reply1_content, set(), set(), set(),
            False, PostId(1), None, reply1_created_at
        )
        self._replies[ReplyId(1)] = reply1

        # リプライ2: ポスト1への別のリプライ
        reply2_content = PostContent(
            content="素晴らしい冒険の始まりですね！ 応援しています。",
            hashtags=("冒険", "応援"),
            visibility=PostVisibility.PUBLIC
        )
        reply2_created_at = base_time - timedelta(hours=1, minutes=30)
        reply2 = ReplyAggregate(
            ReplyId(2), UserId(3), reply2_content, set(), set(), set(),
            False, PostId(1), None, reply2_created_at
        )
        self._replies[ReplyId(2)] = reply2

        # リプライ3: ポスト2（魔法使いの魔法研究ポスト）へのリプライ
        reply3_content = PostContent(
            content="その魔法、私も興味あるよ！ 一緒に研究しよう。",
            hashtags=("魔法", "研究"),
            visibility=PostVisibility.PUBLIC
        )
        reply3_created_at = base_time - timedelta(hours=45)
        reply3 = ReplyAggregate(
            ReplyId(3), UserId(1), reply3_content, set(), set(), set(),
            False, PostId(2), None, reply3_created_at
        )
        self._replies[ReplyId(3)] = reply3

        # リプライ4: リプライ3へのリプライ（ネスト構造）
        reply4_content = PostContent(
            content="いいね！ 魔法の理論について議論しよう。",
            hashtags=("魔法", "議論"),
            visibility=PostVisibility.PUBLIC
        )
        reply4_created_at = base_time - timedelta(hours=30)
        reply4 = ReplyAggregate(
            ReplyId(4), UserId(2), reply4_content, set(), set(), set(),
            False, None, ReplyId(3), reply4_created_at
        )
        self._replies[ReplyId(4)] = reply4

        # リプライ5: ポスト4（盗賊の宝探しポスト）へのリプライ
        reply5_content = PostContent(
            content="その宝物、すごく魅力的だね！ 見に行きたい。",
            hashtags=("宝物", "冒険"),
            visibility=PostVisibility.PUBLIC
        )
        reply5_created_at = base_time - timedelta(minutes=40)
        reply5 = ReplyAggregate(
            ReplyId(5), UserId(1), reply5_content, set(), set(), set(),
            False, PostId(4), None, reply5_created_at
        )
        self._replies[ReplyId(5)] = reply5

        # リプライ6: ポスト5（僧侶の癒しポスト）へのリプライ
        reply6_content = PostContent(
            content="いつもみんなを癒してくれるなんて、素晴らしいですね。",
            hashtags=("癒し", "感謝"),
            visibility=PostVisibility.PUBLIC
        )
        reply6_created_at = base_time - timedelta(minutes=25)
        reply6 = ReplyAggregate(
            ReplyId(6), UserId(4), reply6_content, set(), set(), set(),
            False, PostId(5), None, reply6_created_at
        )
        self._replies[ReplyId(6)] = reply6

        # リプライ7: リプライ6へのリプライ
        reply7_content = PostContent(
            content="ありがとう！ みんなの笑顔が私の原動力だよ。",
            hashtags=("癒し", "感謝"),
            visibility=PostVisibility.PUBLIC
        )
        reply7_created_at = base_time - timedelta(minutes=20)
        reply7 = ReplyAggregate(
            ReplyId(7), UserId(5), reply7_content, set(), set(), set(),
            False, None, ReplyId(6), reply7_created_at
        )
        self._replies[ReplyId(7)] = reply7

        # リプライ8: リプライ7へのさらに深いリプライ（3階層）
        reply8_content = PostContent(
            content="そんな気持ち、素晴らしいと思います！",
            hashtags=("癒し", "感動"),
            visibility=PostVisibility.PUBLIC
        )
        reply8_created_at = base_time - timedelta(minutes=15)
        reply8 = ReplyAggregate(
            ReplyId(8), UserId(3), reply8_content, set(), set(), set(),
            False, None, ReplyId(7), reply8_created_at
        )
        self._replies[ReplyId(8)] = reply8

        # リプライ9: ポスト6（商人の取引ポスト）へのリプライ（フォロワー限定）
        reply9_content = PostContent(
            content="良い品物があるんですね。興味ありますよ。",
            hashtags=("取引", "興味"),
            visibility=PostVisibility.FOLLOWERS_ONLY
        )
        reply9_created_at = base_time - timedelta(minutes=10)
        reply9 = ReplyAggregate(
            ReplyId(9), UserId(1), reply9_content, set(), set(), set(),
            False, PostId(6), None, reply9_created_at
        )
        self._replies[ReplyId(9)] = reply9

        # リプライ10: ポスト1へのもう一つのリプライ（最近のもの）
        reply10_content = PostContent(
            content="冒険の詳細、聞かせてほしいな！",
            hashtags=("冒険", "詳細"),
            visibility=PostVisibility.PUBLIC
        )
        reply10_created_at = base_time - timedelta(minutes=5)
        reply10 = ReplyAggregate(
            ReplyId(10), UserId(4), reply10_content, set(), set(), set(),
            False, PostId(1), None, reply10_created_at
        )
        self._replies[ReplyId(10)] = reply10

        # 次に使用するリプライIDを設定
        self._next_reply_id = ReplyId(11)

    def generate_reply_id(self) -> ReplyId:
        """新しいリプライIDを生成"""
        reply_id = self._next_reply_id
        self._next_reply_id = ReplyId(reply_id.value + 1)
        return reply_id

    def save(self, reply: ReplyAggregate) -> None:
        """リプライを保存"""
        self._replies[reply.reply_id] = reply
        reply.clear_events()  # 発行済みのイベントをクリア

    def find_by_id(self, reply_id: ReplyId) -> Optional[ReplyAggregate]:
        """IDでリプライを取得"""
        return self._replies.get(reply_id)

    def find_by_post_id(self, post_id: PostId, limit: int = 20, offset: int = 0) -> List[ReplyAggregate]:
        """特定のポストへのリプライ一覧を取得"""
        replies = [r for r in self._replies.values() if r.parent_post_id == post_id and not r.deleted]
        # 作成日時でソート（新しい順）
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[offset:offset + limit]

    def find_by_post_id_include_deleted(self, post_id: PostId, limit: int = 20, offset: int = 0) -> List[ReplyAggregate]:
        """特定のポストへのリプライ一覧を取得（削除済みを含む）"""
        replies = [r for r in self._replies.values() if r.parent_post_id == post_id]
        # 作成日時でソート（新しい順）
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[offset:offset + limit]

    def find_by_user_id(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[ReplyAggregate]:
        """特定のユーザーのリプライ一覧を取得"""
        replies = [r for r in self._replies.values() if r.author_user_id == user_id and not r.deleted]
        # 作成日時でソート（新しい順）
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[offset:offset + limit]

    def find_by_parent_reply_id(self, parent_reply_id: ReplyId, limit: int = 20) -> List[ReplyAggregate]:
        """特定の親リプライへのリプライ一覧を取得（スレッド表示用）"""
        replies = [r for r in self._replies.values() if r.parent_reply_id == parent_reply_id and not r.deleted]
        # 作成日時でソート（新しい順）
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[:limit]

    def find_replies_mentioning_user(self, user_name: str, limit: int = 20) -> List[ReplyAggregate]:
        """指定ユーザーをメンションしたリプライを取得"""
        replies = []
        for reply in self._replies.values():
            if not reply.deleted and user_name in reply.get_mentioned_users():
                replies.append(reply)

        # 作成日時でソート（新しい順）
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[:limit]

    def find_replies_liked_by_user(self, user_id: UserId, limit: int = 20) -> List[ReplyAggregate]:
        """指定ユーザーがいいねしたリプライ一覧を取得"""
        replies = []
        for reply in self._replies.values():
            if not reply.deleted and reply.is_liked_by_user(user_id):
                replies.append(reply)

        # 作成日時でソート（新しい順）
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[:limit]

    def find_replies_with_parent_posts(self, limit: int = 20) -> List[tuple]:
        """リプライとその親ポストの情報をまとめて取得（未実装）"""
        # このメソッドは複雑なので、今回は未実装
        return []

    def search_replies_by_content(self, query: str, limit: int = 20) -> List[ReplyAggregate]:
        """コンテンツでリプライを検索"""
        replies = []
        query_lower = query.lower()
        for reply in self._replies.values():
            if not reply.deleted and query_lower in reply.content.content.lower():
                replies.append(reply)

        # 作成日時でソート（新しい順）
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[:limit]

    def get_reply_count(self, post_id: PostId) -> int:
        """特定のポストへのリプライ数を取得"""
        return len([r for r in self._replies.values() if r.parent_post_id == post_id and not r.deleted])

    def find_thread_replies(self, root_post_id: PostId, max_depth: int = 3) -> Dict[Union[PostId, ReplyId], List[ReplyAggregate]]:
        """ポストへのリプライツリーを取得（スレッド表示用）"""
        result = {}

        def collect_replies(parent_id: Union[PostId, ReplyId], current_depth: int):
            if current_depth > max_depth:
                return

            replies = []
            if isinstance(parent_id, PostId):
                # ポストへの直接リプライ
                replies = [r for r in self._replies.values() if r.parent_post_id == parent_id and not r.deleted]
            else:
                # リプライへのリプライ
                replies = [r for r in self._replies.values() if r.parent_reply_id == parent_id and not r.deleted]

            # 作成日時でソート（古い順）
            replies.sort(key=lambda x: x.created_at)

            result[parent_id] = replies

            # 子リプライを再帰的に取得
            for reply in replies:
                collect_replies(reply.reply_id, current_depth + 1)

        collect_replies(root_post_id, 0)
        return result

    def find_thread_replies_include_deleted(self, root_post_id: PostId, max_depth: int = 3) -> Dict[Union[PostId, ReplyId], List[ReplyAggregate]]:
        """ポストへのリプライツリーを取得（スレッド表示用、削除済みを含む）"""
        result = {}

        def collect_replies(parent_id: Union[PostId, ReplyId], current_depth: int):
            if current_depth > max_depth:
                return

            replies = []
            if isinstance(parent_id, PostId):
                # ポストへの直接リプライ（削除済みを含む）
                replies = [r for r in self._replies.values() if r.parent_post_id == parent_id]
            else:
                # リプライへのリプライ（削除済みを含む）
                replies = [r for r in self._replies.values() if r.parent_reply_id == parent_id]

            # 作成日時でソート（古い順）
            replies.sort(key=lambda x: x.created_at)

            result[parent_id] = replies

            # 子リプライを再帰的に取得
            for reply in replies:
                collect_replies(reply.reply_id, current_depth + 1)

        collect_replies(root_post_id, 0)
        return result

    def find_replies_by_post_ids(self, post_ids: List[PostId]) -> Dict[PostId, List[ReplyAggregate]]:
        """複数のポストへのリプライを取得"""
        result = {}
        for post_id in post_ids:
            replies = [r for r in self._replies.values() if r.parent_post_id == post_id and not r.deleted]
            # 作成日時でソート（新しい順）
            replies.sort(key=lambda x: x.created_at, reverse=True)
            result[post_id] = replies
        return result

    def get_user_reply_stats(self, user_id: UserId) -> Dict[str, int]:
        """ユーザーのリプライ統計を取得"""
        user_replies = [r for r in self._replies.values() if r.author_user_id == user_id and not r.deleted]
        total_likes = sum(len(reply.likes) for reply in user_replies)

        return {
            "total_replies": len(user_replies),
            "total_likes_received": total_likes,
            "replies_this_month": len([r for r in user_replies if (datetime.now() - r.created_at).days <= 30])
        }

    def find_recent_replies(self, limit: int = 20) -> List[ReplyAggregate]:
        """最新のリプライを取得"""
        replies = [r for r in self._replies.values() if not r.deleted]
        # 作成日時でソート（新しい順）
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[:limit]

    def find_replies_excluding_blocked_users(
        self,
        user_id: UserId,
        blocked_user_ids: List[UserId],
        limit: int = 20
    ) -> List[ReplyAggregate]:
        """ブロックしたユーザーのリプライを除外した一覧を取得（未実装）"""
        # ブロック機能はまだ実装されていないので、全てのリプライを返す
        replies = [r for r in self._replies.values() if not r.deleted]
        # 作成日時でソート（新しい順）
        replies.sort(key=lambda x: x.created_at, reverse=True)
        return replies[:limit]

    def bulk_delete_replies(self, reply_ids: List[ReplyId], user_id: UserId) -> int:
        """複数のリプライを一括削除（自分のリプライのみ）"""
        deleted_count = 0
        for reply_id in reply_ids:
            reply = self._replies.get(reply_id)
            if reply and reply.author_user_id == user_id and not reply.deleted:
                reply.delete(user_id, "reply")
                deleted_count += 1
        return deleted_count

    def cleanup_deleted_replies(self, older_than_days: int = 30) -> int:
        """古い削除済みリプライをクリーンアップ"""
        cutoff_date = datetime.now() - timedelta(days=older_than_days)
        deleted_replies = [r for r in self._replies.values()
                          if r.deleted and r.created_at < cutoff_date]

        for reply in deleted_replies:
            del self._replies[reply.reply_id]

        return len(deleted_replies)

    def find_by_ids(self, entity_ids: List[int]) -> List[ReplyAggregate]:
        """IDのリストでリプライを検索"""
        reply_ids = [ReplyId(rid) for rid in entity_ids]
        return [self._replies.get(rid) for rid in reply_ids if rid in self._replies and not self._replies[rid].deleted]

    def delete(self, entity_id: ReplyId) -> bool:
        """リプライを削除（論理削除）"""
        if entity_id in self._replies:
            reply = self._replies[entity_id]
            if not reply.deleted:
                reply.delete(reply.author_user_id, "reply")
                return True
        return False

    def find_all(self) -> List[ReplyAggregate]:
        """全てのリプライを取得（削除済みは除く）"""
        return [reply for reply in self._replies.values() if not reply.deleted]

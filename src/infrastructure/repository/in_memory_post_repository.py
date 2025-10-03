"""
InMemoryPostRepository - PostAggregateを使用するインメモリ実装
"""
from typing import List, Optional, Dict, Set
from datetime import datetime, timedelta
import random
from src.domain.sns.repository.post_repository import PostRepository
from src.domain.sns.aggregate.post_aggregate import PostAggregate
from src.domain.sns.value_object.post_content import PostContent
from src.domain.sns.value_object.post_id import PostId
from src.domain.sns.value_object.user_id import UserId
from src.domain.sns.value_object.like import Like
from src.domain.sns.value_object.mention import Mention
from src.domain.sns.enum.sns_enum import PostVisibility


class InMemoryPostRepository(PostRepository):
    """PostAggregateを使用するインメモリリポジトリ"""

    def __init__(self):
        self._posts: Dict[PostId, PostAggregate] = {}
        self._next_post_id = PostId(1)

        # サンプルポストデータを作成
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプルポストデータのセットアップ"""
        # 現在の時間を基準に過去のポストを作成
        base_time = datetime.now()

        # ポスト1: 勇者の冒険開始ポスト (パブリック)
        post1_content = PostContent(
            content="今日は新しい冒険が始まる！ みんなの応援待ってるよ！",
            hashtags=("冒険", "勇者"),
            visibility=PostVisibility.PUBLIC
        )
        post1_created_at = base_time - timedelta(hours=2)
        post1 = PostAggregate(PostId(1), UserId(1), post1_content, set(), set(), set(), False, None, None, post1_created_at)
        self._posts[PostId(1)] = post1

        # ポスト2: 魔法使いの魔法研究ポスト (パブリック)
        post2_content = PostContent(
            content="新しい魔法の研究中！ 魔法の力で世界をより良くしたいな。",
            hashtags=("魔法", "研究"),
            visibility=PostVisibility.PUBLIC
        )
        post2_created_at = base_time - timedelta(hours=1, minutes=30)
        post2 = PostAggregate(PostId(2), UserId(2), post2_content, set(), set(), set(), False, None, None, post2_created_at)
        self._posts[PostId(2)] = post2

        # ポスト3: 戦士の修行ポスト (フォロワー限定)
        post3_content = PostContent(
            content="今日も剣の修行を頑張った！ 強くなるために毎日努力だ。",
            hashtags=("剣術", "修行"),
            visibility=PostVisibility.FOLLOWERS_ONLY
        )
        post3_created_at = base_time - timedelta(hours=1)
        post3 = PostAggregate(PostId(3), UserId(3), post3_content, set(), set(), set(), False, None, None, post3_created_at)
        self._posts[PostId(3)] = post3

        # ポスト4: 盗賊の宝探しポスト (パブリック)
        post4_content = PostContent(
            content="素晴らしい宝物を見つけたぞ！ これでみんな幸せになるね。",
            hashtags=("宝物", "冒険"),
            visibility=PostVisibility.PUBLIC
        )
        post4_created_at = base_time - timedelta(minutes=45)
        post4 = PostAggregate(PostId(4), UserId(4), post4_content, set(), set(), set(), False, None, None, post4_created_at)
        self._posts[PostId(4)] = post4

        # ポスト5: 僧侶の癒しポスト (パブリック)
        post5_content = PostContent(
            content="今日も多くの人々を癒すことができた。 みんなの笑顔を見るのが何よりの喜びだ。",
            hashtags=("癒し", "僧侶"),
            visibility=PostVisibility.PUBLIC
        )
        post5_created_at = base_time - timedelta(minutes=30)
        post5 = PostAggregate(PostId(5), UserId(5), post5_content, set(), set(), set(), False, None, None, post5_created_at)
        self._posts[PostId(5)] = post5

        # ポスト6: 商人の取引ポスト (フォロワー限定)
        post6_content = PostContent(
            content="良い品物を手に入れたよ！ 興味のある人は声かけてね。",
            hashtags=("取引", "商人"),
            visibility=PostVisibility.FOLLOWERS_ONLY
        )
        post6_created_at = base_time - timedelta(minutes=15)
        post6 = PostAggregate(PostId(6), UserId(6), post6_content, set(), set(), set(), False, None, None, post6_created_at)
        self._posts[PostId(6)] = post6

        # ポスト7: 勇者のリプライポスト (パブリック)
        post7_content = PostContent(
            content="もちろん一緒に研究しよう！ 魔法の力は冒険に欠かせないよ。",
            hashtags=("魔法", "協力"),
            visibility=PostVisibility.PUBLIC
        )
        post7_created_at = base_time - timedelta(minutes=10)
        post7 = PostAggregate(PostId(7), UserId(1), post7_content, set(), set(), set(), False, None, None, post7_created_at)
        self._posts[PostId(7)] = post7

        # ポスト8: 魔法使いの追加ポスト (パブリック)
        post8_content = PostContent(
            content="みんなの応援ありがとう！ 一緒に素晴らしい冒険にしよう。",
            hashtags=("魔法", "冒険"),
            visibility=PostVisibility.PUBLIC
        )
        post8_created_at = base_time - timedelta(minutes=5)
        post8 = PostAggregate(PostId(8), UserId(2), post8_content, set(), set(), set(), False, None, None, post8_created_at)
        self._posts[PostId(8)] = post8

        # ポスト9: 勇者の個人的なメモ (プライベート)
        post9_content = PostContent(
            content="今日の出来事について考えている。冒険は楽しいけれど、責任も重いな...",
            hashtags=("メモ", "内省"),
            visibility=PostVisibility.PRIVATE
        )
        post9_created_at = base_time - timedelta(minutes=3)
        post9 = PostAggregate(PostId(9), UserId(1), post9_content, set(), set(), set(), False, None, None, post9_created_at)
        self._posts[PostId(9)] = post9

        # ポスト10: 魔法使いの研究ノート (フォロワー限定)
        post10_content = PostContent(
            content="新しい魔法の理論をまとめている。フォロワー諸君の意見が聞きたい。",
            hashtags=("魔法", "理論", "研究"),
            visibility=PostVisibility.FOLLOWERS_ONLY
        )
        post10_created_at = base_time - timedelta(minutes=2)
        post10 = PostAggregate(PostId(10), UserId(2), post10_content, set(), set(), set(), False, None, None, post10_created_at)
        self._posts[PostId(10)] = post10

        # ポスト11: 戦士の日記 (プライベート)
        post11_content = PostContent(
            content="剣の修行は厳しいが、強くなれている実感がある。明日はもっと頑張ろう。",
            hashtags=("日記", "修行"),
            visibility=PostVisibility.PRIVATE
        )
        post11_created_at = base_time - timedelta(minutes=1)
        post11 = PostAggregate(PostId(11), UserId(3), post11_content, set(), set(), set(), False, None, None, post11_created_at)
        self._posts[PostId(11)] = post11

        # ポスト12: 人気ポスト - イベントのお知らせ (パブリック) - 多くのいいねを集める
        post12_content = PostContent(
            content="明日、街の広場で大きなイベントが開催されます！ みんなで一緒に楽しみましょう！ #イベント #街 #みんな",
            hashtags=("イベント", "街", "みんな"),
            visibility=PostVisibility.PUBLIC
        )
        post12_created_at = base_time - timedelta(hours=3)
        post12 = PostAggregate(PostId(12), UserId(1), post12_content, set(), set(), set(), False, None, None, post12_created_at)
        self._posts[PostId(12)] = post12

        # ポスト13: 魔法の研究発表 (パブリック)
        post13_content = PostContent(
            content="新しい魔法の研究成果を発表します！ 火の魔法が大幅にパワーアップしました。 #魔法 #研究 #進化",
            hashtags=("魔法", "研究", "進化"),
            visibility=PostVisibility.PUBLIC
        )
        post13_created_at = base_time - timedelta(hours=2, minutes=30)
        post13 = PostAggregate(PostId(13), UserId(2), post13_content, set(), set(), set(), False, None, None, post13_created_at)
        self._posts[PostId(13)] = post13

        # ポスト14: 冒険の思い出話 (パブリック)
        post14_content = PostContent(
            content="昔の冒険の思い出を語ろう。ドラゴンと戦ったあの日は忘れられないな。 #冒険 #思い出 #ドラゴン",
            hashtags=("冒険", "思い出", "ドラゴン"),
            visibility=PostVisibility.PUBLIC
        )
        post14_created_at = base_time - timedelta(hours=1, minutes=45)
        post14 = PostAggregate(PostId(14), UserId(4), post14_content, set(), set(), set(), False, None, None, post14_created_at)
        self._posts[PostId(14)] = post14

        # ポスト15: 癒しの音楽会のお知らせ (パブリック)
        post15_content = PostContent(
            content="今夜、癒しの音楽会を開催します。美しい音楽と共に心を癒しましょう。 #音楽 #癒し #イベント",
            hashtags=("音楽", "癒し", "イベント"),
            visibility=PostVisibility.PUBLIC
        )
        post15_created_at = base_time - timedelta(hours=1, minutes=15)
        post15 = PostAggregate(PostId(15), UserId(5), post15_content, set(), set(), set(), False, None, None, post15_created_at)
        self._posts[PostId(15)] = post15

        # ポスト16: 剣術の新しい技 (フォロワー限定)
        post16_content = PostContent(
            content="新しい剣術の技を開発しました！ フォロワー諸君に特別に公開します。 #剣術 #技 #修行",
            hashtags=("剣術", "技", "修行"),
            visibility=PostVisibility.FOLLOWERS_ONLY
        )
        post16_created_at = base_time - timedelta(minutes=45)
        post16 = PostAggregate(PostId(16), UserId(3), post16_content, set(), set(), set(), False, None, None, post16_created_at)
        self._posts[PostId(16)] = post16

        # ポスト17: 宝探しのヒント (パブリック)
        post17_content = PostContent(
            content="次の宝探しのヒント：森の奥深く、月の光が差す場所を探せ。 #宝探し #ヒント #冒険",
            hashtags=("宝探し", "ヒント", "冒険"),
            visibility=PostVisibility.PUBLIC
        )
        post17_created_at = base_time - timedelta(minutes=30)
        post17 = PostAggregate(PostId(17), UserId(4), post17_content, set(), set(), set(), False, None, None, post17_created_at)
        self._posts[PostId(17)] = post17

        # ポスト18: 商人のスペシャルオファー (パブリック)
        post18_content = PostContent(
            content="スペシャルオファー！ 今日だけ、全商品20%オフ！ お買い得ですよ。 #セール #商人 #お得",
            hashtags=("セール", "商人", "お得"),
            visibility=PostVisibility.PUBLIC
        )
        post18_created_at = base_time - timedelta(minutes=20)
        post18 = PostAggregate(PostId(18), UserId(6), post18_content, set(), set(), set(), False, None, None, post18_created_at)
        self._posts[PostId(18)] = post18

        # ポスト19: 魔法のワークショップ (パブリック)
        post19_content = PostContent(
            content="魔法のワークショップ開催！ 初心者でも参加OKです。一緒に魔法を学びましょう。 #ワークショップ #魔法 #初心者",
            hashtags=("ワークショップ", "魔法", "初心者"),
            visibility=PostVisibility.PUBLIC
        )
        post19_created_at = base_time - timedelta(minutes=10)
        post19 = PostAggregate(PostId(19), UserId(2), post19_content, set(), set(), set(), False, None, None, post19_created_at)
        self._posts[PostId(19)] = post19

        # ポスト20: 人気ポスト - 英雄の凱旋 (パブリック) - 大量のいいねを集める
        post20_content = PostContent(
            content="ついに魔王を倒した！ みんなの応援のおかげだ。ありがとう！ #勝利 #英雄 #魔王",
            hashtags=("勝利", "英雄", "魔王"),
            visibility=PostVisibility.PUBLIC
        )
        post20_created_at = base_time - timedelta(hours=4)
        post20 = PostAggregate(PostId(20), UserId(1), post20_content, set(), set(), set(), False, None, None, post20_created_at)
        self._posts[PostId(20)] = post20

        # いいねデータを追加（ランダムに設定）
        self._add_sample_likes()

        self._next_post_id = PostId(21)

    def _add_sample_likes(self):
        """サンプルいいねデータを追加"""
        # ポスト1（勇者の冒険開始ポスト）にいいね
        self._posts[PostId(1)].like_post(UserId(2))  # 魔法使いから
        self._posts[PostId(1)].like_post(UserId(3))  # 戦士から
        self._posts[PostId(1)].like_post(UserId(5))  # 僧侶から

        # ポスト2（魔法使いの研究ポスト）にいいね
        self._posts[PostId(2)].like_post(UserId(1))  # 勇者から
        self._posts[PostId(2)].like_post(UserId(5))  # 僧侶から

        # ポスト3（戦士の修行ポスト）にいいね
        self._posts[PostId(3)].like_post(UserId(1))  # 勇者から
        self._posts[PostId(3)].like_post(UserId(2))  # 魔法使いから

        # ポスト4（盗賊の宝探しポスト）にいいね
        self._posts[PostId(4)].like_post(UserId(1))  # 勇者から

        # ポスト5（僧侶の癒しポスト）にいいね
        self._posts[PostId(5)].like_post(UserId(1))  # 勇者から
        self._posts[PostId(5)].like_post(UserId(2))  # 魔法使いから
        self._posts[PostId(5)].like_post(UserId(3))  # 戦士から
        self._posts[PostId(5)].like_post(UserId(4))  # 盗賊から

        # ポスト6（商人の取引ポスト）にいいね（少ない）
        self._posts[PostId(6)].like_post(UserId(4))  # 盗賊から

        # ポスト7（勇者のリプライ）にいいね
        self._posts[PostId(7)].like_post(UserId(2))  # 魔法使いから

        # ポスト8（魔法使いの追加ポスト）にいいね
        self._posts[PostId(8)].like_post(UserId(1))  # 勇者から
        self._posts[PostId(8)].like_post(UserId(3))  # 戦士から
        self._posts[PostId(8)].like_post(UserId(5))  # 僧侶から

        # ポスト10（魔法使いの研究ノート）にいいね（フォロワー限定なのでフォロワーからのみ）
        self._posts[PostId(10)].like_post(UserId(1))  # 勇者から（フォロワー）
        self._posts[PostId(10)].like_post(UserId(3))  # 戦士から（フォロワーではないがテスト用）

        # 新しいポストのいいねデータを追加
        # ポスト12（イベントのお知らせ）に多くのいいね
        for user_id in [1, 2, 3, 4, 5, 6]:
            self._posts[PostId(12)].like_post(UserId(user_id))

        # ポスト13（魔法の研究発表）にいいね
        self._posts[PostId(13)].like_post(UserId(1))  # 勇者から
        self._posts[PostId(13)].like_post(UserId(3))  # 戦士から
        self._posts[PostId(13)].like_post(UserId(5))  # 僧侶から

        # ポスト14（冒険の思い出話）にいいね
        self._posts[PostId(14)].like_post(UserId(1))  # 勇者から
        self._posts[PostId(14)].like_post(UserId(2))  # 魔法使いから

        # ポスト15（音楽会のお知らせ）にいいね
        self._posts[PostId(15)].like_post(UserId(1))  # 勇者から
        self._posts[PostId(15)].like_post(UserId(2))  # 魔法使いから
        self._posts[PostId(15)].like_post(UserId(4))  # 盗賊から
        self._posts[PostId(15)].like_post(UserId(6))  # 商人から

        # ポスト16（剣術の新しい技）にいいね
        self._posts[PostId(16)].like_post(UserId(1))  # 勇者から
        self._posts[PostId(16)].like_post(UserId(2))  # 魔法使いから

        # ポスト17（宝探しのヒント）にいいね
        self._posts[PostId(17)].like_post(UserId(1))  # 勇者から
        self._posts[PostId(17)].like_post(UserId(6))  # 商人から

        # ポスト18（商人のスペシャルオファー）にいいね
        self._posts[PostId(18)].like_post(UserId(1))  # 勇者から
        self._posts[PostId(18)].like_post(UserId(2))  # 魔法使いから
        self._posts[PostId(18)].like_post(UserId(3))  # 戦士から
        self._posts[PostId(18)].like_post(UserId(4))  # 盗賊から
        self._posts[PostId(18)].like_post(UserId(5))  # 僧侶から

        # ポスト19（魔法のワークショップ）にいいね
        self._posts[PostId(19)].like_post(UserId(1))  # 勇者から
        self._posts[PostId(19)].like_post(UserId(3))  # 戦士から
        self._posts[PostId(19)].like_post(UserId(4))  # 盗賊から
        self._posts[PostId(19)].like_post(UserId(5))  # 僧侶から
        self._posts[PostId(19)].like_post(UserId(6))  # 商人から

        # ポスト20（英雄の凱旋）に大量のいいね（最も人気）
        for user_id in range(1, 7):  # 全てのユーザーから
            self._posts[PostId(20)].like_post(UserId(user_id))
        # さらに追加で人気を出す
        self._posts[PostId(20)].like_post(UserId(1))  # 重複いいね（実際には無視されるはずだがテスト用）
        self._posts[PostId(20)].like_post(UserId(2))

    def find_by_id(self, post_id: int) -> Optional[PostAggregate]:
        """ポストIDでポストを検索"""
        try:
            post_id_obj = PostId(post_id) if not isinstance(post_id, PostId) else post_id
            return self._posts.get(post_id_obj)
        except ValueError:
            return None

    def find_by_ids(self, post_ids: List[PostId]) -> List[PostAggregate]:
        """複数のポストIDでポストを検索"""
        result = []
        for post_id in post_ids:
            post = self._posts.get(post_id)
            if post:
                result.append(post)
        return result

    def save(self, post: PostAggregate) -> PostAggregate:
        """ポストを保存"""
        self._posts[post.post_id] = post
        post.clear_events()  # 発行済みのイベントをクリア
        return post

    def delete(self, post_id: PostId) -> bool:
        """ポストを削除"""
        if post_id in self._posts:
            del self._posts[post_id]
            return True
        return False

    def exists_by_id(self, post_id: PostId) -> bool:
        """ポストIDが存在するかチェック"""
        return post_id in self._posts

    def count(self) -> int:
        """ポストの総数を取得"""
        return len(self._posts)

    def find_all(self) -> List[PostAggregate]:
        """全てのポストを取得"""
        return list(self._posts.values())

    def find_by_user_id(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        """特定のユーザーのポスト一覧を取得（タイムライン用）"""
        user_posts = [post for post in self._posts.values() if post.author_user_id == user_id]
        # 作成日時の降順でソート
        user_posts.sort(key=lambda p: p.created_at, reverse=True)
        return user_posts[offset:offset + limit]

    def find_by_user_ids(self, user_ids: List[UserId], limit: int = 50, offset: int = 0, sort_by: str = "created_at") -> List[PostAggregate]:
        """複数のユーザーのポストを取得（フォロー中ユーザーの投稿取得用、ソート付き）"""
        result = []
        for user_id in user_ids:
            user_posts = self.find_by_user_id(user_id, limit // len(user_ids) if len(user_ids) > 0 else limit)
            result.extend(user_posts)

        # ソートキーの決定
        if sort_by == "created_at":
            sort_key = lambda p: p.created_at
        else:
            sort_key = lambda p: p.created_at  # デフォルトは作成日時

        # ソート
        result.sort(key=sort_key, reverse=True)

        # offsetとlimitを適用
        if offset > 0:
            result = result[offset:]
        return result[:limit]

    def find_recent_posts(self, limit: int = 20) -> List[PostAggregate]:
        """最新のポストを取得（トレンド表示用）"""
        all_posts = list(self._posts.values())
        # 作成日時の降順でソート
        all_posts.sort(key=lambda p: p.created_at, reverse=True)
        return all_posts[:limit]

    def find_posts_mentioning_user(self, user_name: str, limit: int = 20) -> List[PostAggregate]:
        """指定ユーザーをメンションしたポストを取得"""
        mentioned_posts = []
        for post in self._posts.values():
            if any(mention.mentioned_user_name == user_name for mention in post.mentions):
                mentioned_posts.append(post)

        # 作成日時の降順でソート
        mentioned_posts.sort(key=lambda p: p.created_at, reverse=True)
        return mentioned_posts[:limit]

    def find_liked_posts_by_user(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        """指定ユーザーがいいねしたポスト一覧を取得"""
        liked_posts = []
        for post in self._posts.values():
            if any(like.user_id == user_id for like in post.likes):
                liked_posts.append(post)

        # いいねした日時の降順でソート（簡易的に作成日時を使用）
        liked_posts.sort(key=lambda p: p.created_at, reverse=True)

        # offsetとlimitを適用
        if offset > 0:
            liked_posts = liked_posts[offset:]
        return liked_posts[:limit]

    def find_posts_liked_by_user(self, user_id: UserId, limit: int = 20) -> List[PostAggregate]:
        """指定ユーザーからいいねされたポスト一覧を取得"""
        return self.find_liked_posts_by_user(user_id, limit)  # 同じ実装でOK

    def search_posts_by_content(self, query: str, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        """コンテンツでポストを検索"""
        result = []
        query_lower = query.lower()
        for post in self._posts.values():
            if query_lower in post.post_content.content.lower():
                result.append(post)

        # 作成日時の降順でソート
        result.sort(key=lambda p: p.created_at, reverse=True)

        # offsetとlimitを適用
        if offset > 0:
            result = result[offset:]
        return result[:limit]

    def find_posts_by_hashtag(self, hashtag: str, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        """指定ハッシュタグのポストを取得"""
        result = []
        hashtag_lower = hashtag.lower()
        for post in self._posts.values():
            # ポストのハッシュタグに指定ハッシュタグが含まれているかチェック
            if any(tag.lower() == hashtag_lower for tag in post.post_content.hashtags):
                result.append(post)

        # 作成日時の降順でソート
        result.sort(key=lambda p: p.created_at, reverse=True)

        # offsetとlimitを適用
        if offset > 0:
            result = result[offset:]
        return result[:limit]

    def get_like_count(self, post_id: PostId) -> int:
        """特定のポストのいいね数を取得"""
        post = self._posts.get(post_id)
        if post:
            return len(post.likes)
        return 0

    def get_user_post_stats(self, user_id: UserId) -> Dict[str, int]:
        """ユーザーの投稿統計（総投稿数、総いいね数など）を取得"""
        user_posts = [post for post in self._posts.values() if post.author_user_id == user_id]
        total_posts = len(user_posts)
        total_likes = sum(len(post.likes) for post in user_posts)

        return {
            "total_posts": total_posts,
            "total_likes": total_likes
        }

    def find_trending_posts(self, timeframe_hours: int = 24, limit: int = 10, offset: int = 0) -> List[PostAggregate]:
        """トレンドのポストを取得（いいね数やリプライ数でソート）"""
        cutoff_time = datetime.now() - timedelta(hours=timeframe_hours)
        recent_posts = [post for post in self._posts.values() if post.created_at >= cutoff_time]

        # いいね数で降順ソート
        recent_posts.sort(key=lambda p: len(p.likes), reverse=True)

        # offsetとlimitを適用
        if offset > 0:
            recent_posts = recent_posts[offset:]
        return recent_posts[:limit]

    def bulk_delete_posts(self, post_ids: List[PostId], user_id: UserId) -> int:
        """複数のポストを一括削除（自分のポストのみ）"""
        deleted_count = 0
        for post_id in post_ids:
            post = self._posts.get(post_id)
            if post and post.author_user_id == user_id:
                del self._posts[post_id]
                deleted_count += 1
        return deleted_count

    def cleanup_deleted_posts(self, older_than_days: int = 30) -> int:
        """古い削除済みポストをクリーンアップ"""
        # インメモリ実装では削除済みポストは物理的に削除されているので、何もしない
        return 0

    def find_private_posts_by_user(self, user_id: UserId, limit: int = 20, offset: int = 0) -> List[PostAggregate]:
        """特定のユーザーのプライベートポストを取得（作成日時降順）"""
        # ユーザーの全てのポストを取得
        user_posts = [post for post in self._posts.values() if post.author_user_id == user_id]

        # プライベートポストのみをフィルタリング
        private_posts = [post for post in user_posts if post.is_private()]

        # 作成日時の降順でソート
        private_posts.sort(key=lambda p: p.get_sort_key_by_created_at(), reverse=True)

        # offsetとlimitを適用
        return private_posts[offset:offset + limit]

    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全てのポストを削除（テスト用）"""
        self._posts.clear()
        self._next_post_id = PostId(1)

    def find_posts_in_timeframe(self, timeframe_hours: int = 24, limit: int = 1000) -> List[PostAggregate]:
        """指定時間内の全ポストを取得（トレンド計算用）"""
        from datetime import datetime, timedelta

        cutoff_time = datetime.now() - timedelta(hours=timeframe_hours)
        recent_posts = [post for post in self._posts.values() if post.created_at >= cutoff_time]
        return recent_posts[:limit]

    def generate_post_id(self) -> PostId:
        """ポストIDを生成"""
        post_id = self._next_post_id
        self._next_post_id = PostId(self._next_post_id.value + 1)
        return post_id

import pytest
import math
from datetime import datetime, timedelta

from ai_rpg_world.domain.sns.service.trending_domain_service import TrendingDomainService
from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.value_object import PostId, UserId, PostContent
from ai_rpg_world.domain.sns.enum import PostVisibility


class TestTrendingDomainService:
    """TrendingDomainServiceのテスト"""

    def create_test_post(self, post_id: int, user_id: int, content: str, created_at: datetime) -> PostAggregate:
        """テスト用のポストを作成"""
        # contentからハッシュタグを抽出（#で始まる単語）
        import re
        hashtags_in_content = re.findall(r'#(\w+)', content)
        hashtags = tuple(hashtags_in_content) if hashtags_in_content else ("test", "hashtag")

        post_content = PostContent(
            content=content,
            hashtags=hashtags,
            visibility=PostVisibility.PUBLIC
        )
        post = PostAggregate.create(
            post_id=PostId(post_id),
            author_user_id=UserId(user_id),
            post_content=post_content
        )
        # 作成時刻を設定
        post._created_at = created_at
        return post

    def test_calculate_trending_hashtags_basic(self):
        """基本的なトレンド計算テスト"""
        now = datetime.now()

        # テストデータ作成
        posts = [
            self.create_test_post(1, 1, "#人気 #トレンド", now - timedelta(hours=1)),  # 1時間前
            self.create_test_post(2, 1, "#人気 #話題", now - timedelta(hours=0.5)),  # 30分前
            self.create_test_post(3, 1, "#おすすめ", now),  # 現在
        ]

        result = TrendingDomainService.calculate_trending_hashtags(
            posts=posts,
            now=now,
            decay_lambda=0.1,
            recent_window_hours=1.0,
            max_results=10
        )

        # 結果の検証
        assert isinstance(result, list)
        assert len(result) == 4  # 4つのユニークなハッシュタグ

        # 各要素が (hashtag, score) のタプルであることを確認
        for hashtag, score in result:
            assert isinstance(hashtag, str)
            assert isinstance(score, float)
            assert score > 0

        # スコアが降順にソートされていることを確認
        scores = [score for _, score in result]
        assert scores == sorted(scores, reverse=True)

    def test_calculate_trending_hashtags_hybrid_score(self):
        """ハイブリッドスコア計算の詳細テスト"""
        now = datetime.now()

        # テストデータ: 全て直近1時間以内
        posts = [
            self.create_test_post(1, 1, "#トレンド #人気", now - timedelta(hours=1)),  # 1h前
            self.create_test_post(2, 1, "#トレンド #話題", now - timedelta(hours=0.5)),  # 30m前
            self.create_test_post(3, 1, "#人気 #おすすめ", now),  # 現在
        ]

        result = TrendingDomainService.calculate_trending_hashtags(
            posts=posts,
            now=now,
            decay_lambda=0.1,
            recent_window_hours=1.0,
            max_results=10
        )

        # 期待される順位を確認
        hashtags = [hashtag for hashtag, _ in result]
        expected_order = ["人気", "トレンド", "おすすめ", "話題"]  # ハッシュタグのみ

        for i, expected_hashtag in enumerate(expected_order):
            if i < len(hashtags):
                assert hashtags[i] == expected_hashtag, f"順位{i+1}が{expected_hashtag}であるべき: {hashtags}"

    def test_calculate_trending_hashtags_growth_rate(self):
        """成長率の効果をテスト"""
        now = datetime.now()

        # テストデータ: 一部が直近1時間を超える
        posts = [
            # 古いポスト（2時間前）
            self.create_test_post(1, 1, "#古いトレンド", now - timedelta(hours=2)),
            self.create_test_post(2, 1, "#古いトレンド", now - timedelta(hours=2)),
            # 新しいポスト（30分前）
            self.create_test_post(3, 1, "#新しいトレンド", now - timedelta(hours=0.5)),
        ]

        result = TrendingDomainService.calculate_trending_hashtags(
            posts=posts,
            now=now,
            decay_lambda=0.1,
            recent_window_hours=1.0,  # 1時間を直近とする
            max_results=10
        )

        # #古いトレンド: 総数=2, 直近=0, 成長率=0/(2-0+1)=0
        # #新しいトレンド: 総数=1, 直近=1, 成長率=1/(1-1+1)=1

        # 新しいトレンドの方がスコアが高くなるはず
        hashtags = [hashtag for hashtag, _ in result]
        assert hashtags[0] == "新しいトレンド", f"成長率の高いハッシュタグが先頭に来るべき: {hashtags}"

    def test_calculate_trending_hashtags_empty_posts(self):
        """空のポストリストのテスト"""
        now = datetime.now()

        result = TrendingDomainService.calculate_trending_hashtags(
            posts=[],
            now=now,
            decay_lambda=0.1,
            recent_window_hours=1.0,
            max_results=10
        )

        assert result == []

    def test_calculate_trending_hashtags_no_hashtags(self):
        """ハッシュタグのないポストのテスト"""
        now = datetime.now()

        posts = [
            self.create_test_post(1, 1, "ハッシュタグのないポスト", now),
        ]

        result = TrendingDomainService.calculate_trending_hashtags(
            posts=posts,
            now=now,
            decay_lambda=0.1,
            recent_window_hours=1.0,
            max_results=10
        )

        # デフォルトのハッシュタグが使用される
        hashtags = [hashtag for hashtag, _ in result]
        assert "test" in hashtags
        assert "hashtag" in hashtags

    def test_calculate_trending_hashtags_max_results(self):
        """max_resultsパラメータのテスト"""
        now = datetime.now()

        # 多くのハッシュタグを持つポストを作成
        posts = []
        hashtags = [f"tag{i}" for i in range(5)]
        content = " ".join(f"#{tag}" for tag in hashtags)
        posts.append(self.create_test_post(1, 1, content, now))

        result = TrendingDomainService.calculate_trending_hashtags(
            posts=posts,
            now=now,
            decay_lambda=0.1,
            recent_window_hours=1.0,
            max_results=3
        )

        assert len(result) == 3

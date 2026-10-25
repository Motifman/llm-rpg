from datetime import datetime, timedelta

import pytest

from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate
from ai_rpg_world.domain.sns.enum import PostVisibility
from ai_rpg_world.domain.sns.service.trending_domain_service import TrendingDomainService
from ai_rpg_world.domain.sns.value_object import PostContent, PostId, UserId


class TestTrendingDomainService:
    """TrendingDomainServiceのテスト"""

    def create_test_post(
        self,
        post_id: int,
        user_id: int,
        content: str,
        created_at: datetime,
        hashtags: tuple[str, ...] | None = None,
    ) -> PostAggregate:
        """テスト用のポストを作成"""
        # contentからハッシュタグを抽出（#で始まる単語）
        import re

        if hashtags is None:
            hashtags = tuple(re.findall(r"#(\w+)", content))

        post_content = PostContent(content=content, hashtags=hashtags, visibility=PostVisibility.PUBLIC)
        post = PostAggregate.create(post_id=PostId(post_id), author_user_id=UserId(user_id), post_content=post_content)
        # 作成時刻を設定
        post._created_at = created_at
        return post

    def test_calculate_trending_hashtags_basic(self):
        """3投稿の4タグを頻度・直近の増加・時間減衰に応じた得点の降順で返す。"""
        now = datetime.now()

        # テストデータ作成
        posts = [
            self.create_test_post(1, 1, "#人気 #トレンド", now - timedelta(hours=1)),  # 1時間前
            self.create_test_post(2, 1, "#人気 #話題", now - timedelta(hours=0.5)),  # 30分前
            self.create_test_post(3, 1, "#おすすめ", now),  # 現在
        ]

        result = TrendingDomainService.calculate_trending_hashtags(
            posts=posts, now=now, decay_lambda=0.1, recent_window_hours=1.0, max_results=10
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

        # 1h / 0.5h / 0h の各投稿が寄与する既知の得点。
        # 対象の計算関数を期待値の生成に使わない。
        assert dict(result) == pytest.approx(
            {
                "人気": 4.078195683600,
                "トレンド": 0.627185505177,
                "話題": 0.659341993658,
                "おすすめ": 0.693147180560,
            }
        )

    def test_calculate_trending_hashtags_hybrid_score(self):
        """直近の出現数と時間減衰に従い、異なる得点を持つ4タグを欠落なく返す。"""
        now = datetime.now()

        # テストデータ: 全て直近1時間以内
        posts = [
            self.create_test_post(1, 1, "#トレンド #人気", now - timedelta(hours=1)),  # 1h前
            self.create_test_post(2, 1, "#トレンド #話題", now - timedelta(hours=0.5)),  # 30m前
            self.create_test_post(3, 1, "#人気 #おすすめ", now),  # 現在
        ]

        result = TrendingDomainService.calculate_trending_hashtags(
            posts=posts, now=now, decay_lambda=0.1, recent_window_hours=1.0, max_results=10
        )

        # 期待される順位を確認
        hashtags = [hashtag for hashtag, _ in result]
        expected_order = ["人気", "トレンド", "おすすめ", "話題"]  # ハッシュタグのみ

        assert hashtags == expected_order

    def test_calculate_trending_hashtags_growth_rate(self):
        """古い2投稿のタグも得点0で残し、直近1投稿のタグを上位に返す。"""
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
            max_results=10,
        )

        # #古いトレンド: 総数=2, 直近=0, 成長率=0/(2-0+1)=0
        # #新しいトレンド: 総数=1, 直近=1, 成長率=1/(1-1+1)=1

        # 新しいトレンドの方がスコアが高くなるはず
        hashtags = [hashtag for hashtag, _ in result]
        assert hashtags[0] == "新しいトレンド", f"成長率の高いハッシュタグが先頭に来るべき: {hashtags}"
        assert set(hashtags) == {"新しいトレンド", "古いトレンド"}
        scores = dict(result)
        assert scores["古いトレンド"] == 0.0
        assert scores["新しいトレンド"] == pytest.approx(0.659341993658)

    def test_calculate_trending_hashtags_empty_posts(self):
        """空のポストリストのテスト"""
        now = datetime.now()

        result = TrendingDomainService.calculate_trending_hashtags(
            posts=[], now=now, decay_lambda=0.1, recent_window_hours=1.0, max_results=10
        )

        assert result == []

    @pytest.mark.parametrize(
        ("hashtags", "expected_hashtags"),
        [
            pytest.param(("test", "hashtag"), ["hashtag", "test"], id="explicit-tags"),
            pytest.param((), [], id="no-tags"),
        ],
    )
    def test_calculate_trending_hashtags_uses_explicit_tags(self, hashtags, expected_hashtags):
        """本文に#がなくても指定タグを集計し、タグが空の投稿からは何も返さない。"""
        now = datetime.now()

        posts = [
            self.create_test_post(1, 1, "ハッシュタグのないポスト", now, hashtags=hashtags),
        ]

        result = TrendingDomainService.calculate_trending_hashtags(
            posts=posts, now=now, decay_lambda=0.1, recent_window_hours=1.0, max_results=10
        )

        # 同点のタグ同士に順位の約束を追加しない。
        assert sorted(hashtag for hashtag, _ in result) == expected_hashtags

    def test_calculate_trending_hashtags_max_results(self):
        """max_resultsパラメータのテスト"""
        now = datetime.now()

        # 多くのハッシュタグを持つポストを作成
        posts = []
        hashtags = [f"tag{i}" for i in range(5)]
        content = " ".join(f"#{tag}" for tag in hashtags)
        posts.append(self.create_test_post(1, 1, content, now))

        result = TrendingDomainService.calculate_trending_hashtags(
            posts=posts, now=now, decay_lambda=0.1, recent_window_hours=1.0, max_results=3
        )

        assert len(result) == 3

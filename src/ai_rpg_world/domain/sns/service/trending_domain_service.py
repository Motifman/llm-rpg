import math
from datetime import datetime
from typing import List, Tuple, Dict

from ai_rpg_world.domain.sns.aggregate.post_aggregate import PostAggregate


class TrendingDomainService:
    """トレンド計算ドメインサービス"""

    @staticmethod
    def calculate_trending_hashtags(
        posts: List[PostAggregate],
        now: datetime,
        decay_lambda: float,
        recent_window_hours: float = 1.0,
        max_results: int = 10
    ) -> List[Tuple[str, float]]:
        """過去のポストからトレンドハッシュタグを計算 (ハイブリッド方式)

        Args:
            posts: 分析対象のポストリスト
            now: 現在時刻
            decay_lambda: 減衰係数（λ）
            recent_window_hours: 「直近」とみなす時間幅（成長率用）
            max_results: 最大結果数

        Returns:
            ハッシュタグとスコアのタプルのリスト（スコア降順）
        """

        # 各ハッシュタグごとに情報を集める
        hashtag_stats: Dict[str, Dict[str, float]] = {}

        for post in posts:
            # ポスト作成時刻との差
            time_diff_hours = (now - post.created_at).total_seconds() / 3600.0

            # 時間減衰スコア
            decay_score = math.exp(-decay_lambda * time_diff_hours)

            # 成長率計算用に直近・過去を分ける
            is_recent = time_diff_hours <= recent_window_hours

            for hashtag in post.post_content.hashtags:
                if hashtag not in hashtag_stats:
                    hashtag_stats[hashtag] = {
                        "count_total": 0.0,
                        "count_recent": 0.0,
                        "decay_score": 0.0,
                    }

                hashtag_stats[hashtag]["count_total"] += 1
                hashtag_stats[hashtag]["decay_score"] += decay_score
                if is_recent:
                    hashtag_stats[hashtag]["count_recent"] += 1

        # スコア計算
        hashtag_scores: Dict[str, float] = {}
        for hashtag, stats in hashtag_stats.items():
            count_total = stats["count_total"]
            count_recent = stats["count_recent"]
            decay_score = stats["decay_score"]

            # 成長率: 直近 / (総数 - 直近 + 1) で安定化
            growth_rate = count_recent / (count_total - count_recent + 1)

            # スコア = log(1+総数) × 成長率 × 時間減衰
            score = math.log(1 + count_total) * growth_rate * decay_score
            hashtag_scores[hashtag] = score

        # スコア順にソートして返す
        sorted_hashtags = sorted(hashtag_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_hashtags[:max_results]

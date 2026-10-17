"""Episodic Memory ドメイン例外群。

``EpisodicDomainException`` を基底に置く。既存の episodic VO 群 (``EpisodeAction`` 等) は歴史的経緯で組み込み
``ValueError`` のままだが、CLAUDE.md の規約 (「ドメイン層では組み込み例外では
なくドメイン例外を投げる」) に従い、新規追加分はここに足す。約束
(``PendingPrediction``) の検証例外は #1631 で消した。
"""

from ai_rpg_world.domain.common.exception import DomainException


class EpisodicDomainException(DomainException):
    """Episodic Memory ドメインの基底例外。"""

    domain = "memory.episodic"


__all__ = [
    "EpisodicDomainException",
]

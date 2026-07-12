"""Episodic Memory ドメイン例外群。

U10a (予測誤差統一設計 部品6 / pending prediction): ``PendingPrediction`` /
``PendingPredictionDraft`` VO の不変条件違反を、``domain/memory/semantic/exception``
と同じパターンで ``EpisodicDomainException`` 配下の ``ValidationException`` として
表現する。既存の episodic VO 群 (``EpisodeAction`` 等) は歴史的経緯で組み込み
``ValueError`` のままだが、CLAUDE.md の規約 (「ドメイン層では組み込み例外では
なくドメイン例外を投げる」) に従い、新規追加分はドメイン例外を使う。
"""

from ai_rpg_world.domain.common.exception import DomainException, ValidationException


class EpisodicDomainException(DomainException):
    """Episodic Memory ドメインの基底例外。"""

    domain = "memory.episodic"


class PendingPredictionValidationException(
    EpisodicDomainException, ValidationException
):
    """``PendingPrediction`` / ``PendingPredictionDraft`` のバリデーション例外

    (フィールドの型 / 空文字 / resolution_cues の形式 / tick 範囲の逆転 等)。
    """

    error_code = "EPISODIC.PENDING_PREDICTION_VALIDATION"


class HeardClaimValidationException(EpisodicDomainException, ValidationException):
    """``HeardClaim`` (伝聞) のバリデーション例外 (speaker / claim の空文字等)。"""

    error_code = "EPISODIC.HEARD_CLAIM_VALIDATION"


__all__ = [
    "EpisodicDomainException",
    "PendingPredictionValidationException",
    "HeardClaimValidationException",
]

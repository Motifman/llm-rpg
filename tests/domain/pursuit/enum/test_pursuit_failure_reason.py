"""PursuitFailureReason enum のテスト"""

from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
    PursuitFailureReason,
)


class TestPursuitFailureReason:
    """Phase 1 で許可された失敗理由を固定する。"""

    def test_allowed_values_match_phase_one_vocabulary(self):
        """Phase 1 の失敗理由だけを保持すること"""
        assert PursuitFailureReason.TARGET_MISSING.value == "target_missing"
        assert PursuitFailureReason.PATH_UNREACHABLE.value == "path_unreachable"
        assert (
            PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN.value
            == "vision_lost_at_last_known"
        )

    def test_cancelled_is_not_a_failure_reason(self):
        """cancelled は失敗理由として含めないこと"""
        values = {reason.value for reason in PursuitFailureReason}

        assert "cancelled" not in values

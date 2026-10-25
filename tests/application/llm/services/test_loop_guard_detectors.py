from __future__ import annotations

from ai_rpg_world.application.llm.services.loop_guard_detectors import (
    ConsecutiveRepeat,
    ConsecutiveSameActionDetector,
    CrossTickFailureDetector,
    CrossTickFailureRepeat,
    RecordedAction,
)


def _action(
    *,
    tool_name: str = "gather",
    fingerprint: str = "{}",
    success: bool | None = None,
    error_code: str | None = None,
    tick: int | None = 0,
) -> RecordedAction:
    return RecordedAction(
        player_key=1,
        tool_name=tool_name,
        fingerprint=fingerprint,
        success=success,
        error_code=error_code,
        tick=tick,
    )


class TestConsecutiveSameActionDetector:
    """ConsecutiveSameActionDetector が警告を出さずに signal だけを返すことを保証する。"""

    def test_returns_signal_only_at_multiples_of_threshold(self) -> None:
        """閾値 2 で同じ行動を 4 回続けると、2 回目と 4 回目だけ連続回数つきの signal を返す。"""
        detector = ConsecutiveSameActionDetector(thresholds={"gather": 2})

        results = [detector.observe(_action()) for _ in range(4)]

        assert results == [
            None,
            ConsecutiveRepeat(tool_name="gather", fingerprint="{}", consecutive=2, tick=0),
            None,
            ConsecutiveRepeat(tool_name="gather", fingerprint="{}", consecutive=4, tick=0),
        ]


class TestCrossTickFailureDetector:
    """CrossTickFailureDetector が失敗だけを tick の窓で数えることを保証する。"""

    def test_ignores_successful_actions(self) -> None:
        """成功した行動は何回記録しても signal を返さない。"""
        detector = CrossTickFailureDetector(window=20, threshold=2)

        results = [detector.observe(_action(success=True, tick=t)) for t in range(5)]

        assert results == [None] * 5

    def test_returns_signal_when_same_failure_reaches_threshold_within_window(
        self,
    ) -> None:
        """窓 20・閾値 2 で同じ失敗が tick 3 と 10 に出ると、2 回目で件数と tick つきの signal を返す。"""
        detector = CrossTickFailureDetector(window=20, threshold=2)

        first = detector.observe(_action(success=False, error_code="E", tick=3))
        second = detector.observe(_action(success=False, error_code="E", tick=10))

        assert first is None
        assert second == CrossTickFailureRepeat(
            tool_name="gather",
            fingerprint="{}",
            error_code="E",
            count=2,
            window=20,
            tick=10,
        )

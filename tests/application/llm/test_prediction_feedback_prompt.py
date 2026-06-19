"""前回の予測と実際 section の本文生成テスト。"""

from datetime import datetime, timedelta, timezone

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.prompt_builder import (
    build_prediction_feedback_text,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)


_T0 = datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc)


def _action(
    *,
    minutes: int,
    expected_result: str | None,
    result_summary: str = "扉は開かなかった",
    success: bool = True,
    error_code: str | None = None,
    tool_name: str = "spot_graph_interact",
) -> ActionResultEntry:
    return ActionResultEntry(
        occurred_at=_T0 + timedelta(minutes=minutes),
        action_summary="扉を調べた",
        result_summary=result_summary,
        success=success,
        error_code=error_code,
        tool_name=tool_name,
        expected_result=expected_result,
    )


def _obs(minutes: int, prose: str) -> ObservationEntry:
    return ObservationEntry(
        occurred_at=_T0 + timedelta(minutes=minutes),
        output=ObservationOutput(
            prose=prose,
            structured={},
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        ),
    )


class TestBuildPredictionFeedbackText:
    """ActionResultEntry.expected_result から prompt feedback を組み立てる。"""

    def test_expected_result_なしなら空文字(self) -> None:
        """予測を持つ action が無いと section 本文は出ない。"""
        text = build_prediction_feedback_text(
            [_action(minutes=0, expected_result=None)],
            [_obs(1, "静かな廊下だった")],
        )
        assert text == ""

    def test_latest_expected_result_付き_action_と後続観測2件を並べる(self) -> None:
        """最新の予測付き action 1 件だけを使い、後続観測は最大 2 件に圧縮する。"""
        text = build_prediction_feedback_text(
            [
                _action(minutes=0, expected_result="古い予測"),
                _action(minutes=2, expected_result="扉の仕掛けが分かる"),
            ],
            [
                _obs(1, "古い観測"),
                _obs(3, "鍵穴に青い光が見えた"),
                _obs(4, "床板が少し沈んだ"),
                _obs(5, "遠くで鐘が鳴った"),
            ],
        )
        assert "願望ではなく世界への仮説" in text
        assert "- 予測: 扉の仕掛けが分かる" in text
        assert "tool=spot_graph_interact" in text
        assert "success=True" in text
        assert "result=扉は開かなかった" in text
        assert "鍵穴に青い光が見えた" in text
        assert "床板が少し沈んだ" in text
        assert "遠くで鐘が鳴った" not in text
        assert "古い予測" not in text
        assert "古い観測" not in text

    def test_failed_action_では_error_code_も実際に含める(self) -> None:
        """失敗 action の実際には success=False と error_code を出す。"""
        text = build_prediction_feedback_text(
            [
                _action(
                    minutes=0,
                    expected_result="扉が開く",
                    result_summary="鍵が足りない",
                    success=False,
                    error_code="LOCKED",
                )
            ],
            [],
        )
        assert "success=False" in text
        assert "error_code=LOCKED" in text
        assert "result=鍵が足りない" in text

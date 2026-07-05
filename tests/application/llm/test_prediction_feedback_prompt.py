"""前回の予測と実際 section の本文生成テスト (U0: 段0 台帳の N 件化)。"""

from datetime import datetime, timedelta, timezone

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.services.prompt_builder import (
    _PREDICTION_FEEDBACK_LEDGER_LIMIT,
    _PREDICTION_FEEDBACK_TOTAL_CHAR_CAP,
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
    tool_name: str = "interact",
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

    def test_予測付きentryが0件なら空文字(self) -> None:
        """予測 (expected_result) を一切持たない action だけなら、複数件あっても空文字。"""
        text = build_prediction_feedback_text(
            [
                _action(minutes=0, expected_result=None),
                _action(minutes=1, expected_result=None),
            ],
            [],
        )
        assert text == ""

    def test_直近3件が新しい順に台帳として並ぶ(self) -> None:
        """予測付き action が 4 件あっても、直近 3 件だけが新しい順に載る。"""
        text = build_prediction_feedback_text(
            [
                _action(minutes=0, expected_result="予測1 (最古)"),
                _action(minutes=10, expected_result="予測2"),
                _action(minutes=20, expected_result="予測3"),
                _action(minutes=30, expected_result="予測4 (最新)"),
            ],
            [
                _obs(11, "予測2への後続観測"),
                _obs(21, "予測3への後続観測"),
                _obs(31, "予測4への後続観測"),
            ],
        )
        assert _PREDICTION_FEEDBACK_LEDGER_LIMIT == 3
        assert "予測1 (最古)" not in text
        assert "予測2" in text
        assert "予測3" in text
        assert "予測4 (最新)" in text
        # 新しい順に並ぶこと
        assert text.index("予測4 (最新)") < text.index("予測3") < text.index("予測2")

    def test_cap超過時は古いentryから切り詰められる(self) -> None:
        """総文字数が cap を超える場合、新しい entry を優先し古い entry を落とす。"""
        long_expected = "あ" * 500
        text = build_prediction_feedback_text(
            [
                _action(minutes=0, expected_result=f"最古_{long_expected}"),
                _action(minutes=10, expected_result=f"次点_{long_expected}"),
                _action(minutes=20, expected_result=f"最新_{long_expected}"),
            ],
            [
                _obs(11, "後続観測A"),
                _obs(21, "後続観測B"),
            ],
        )
        assert len(text) <= _PREDICTION_FEEDBACK_TOTAL_CHAR_CAP + len(long_expected)
        assert "最新_" in text
        assert "最古_" not in text

    def test_最新entryに後続観測が無ければ結果待ち行になる(self) -> None:
        """後続観測がまだ無い最新 entry は「結果待ち」として予測だけを出す。"""
        text = build_prediction_feedback_text(
            [_action(minutes=0, expected_result="扉の仕掛けが分かる")],
            [],
        )
        assert "- 予測 (結果待ち): 扉の仕掛けが分かる" in text
        assert "- 実際:" not in text

    def test_最新entryに後続観測があれば結果待ちにならない(self) -> None:
        """最新 entry でも後続観測があれば通常どおり予測/実際/後続観測を出す。"""
        text = build_prediction_feedback_text(
            [_action(minutes=0, expected_result="扉の仕掛けが分かる")],
            [_obs(1, "鍵穴に青い光が見えた")],
        )
        assert "結果待ち" not in text
        assert "- 予測: 扉の仕掛けが分かる" in text
        assert "- 実際:" in text
        assert "鍵穴に青い光が見えた" in text

    def test_古いentryの後続観測は次に新しいentryの時刻で区切られる(self) -> None:
        """entry ごとの後続観測が、次に新しい予測付き entry の occurred_at で
        区切られ、複数 entry 間で観測が重複しないこと。"""
        text = build_prediction_feedback_text(
            [
                _action(minutes=0, expected_result="古い予測"),
                _action(minutes=2, expected_result="扉の仕掛けが分かる"),
            ],
            [
                _obs(1, "古い予測への観測"),
                _obs(3, "鍵穴に青い光が見えた"),
                _obs(4, "床板が少し沈んだ"),
                _obs(5, "遠くで鐘が鳴った"),
            ],
        )
        assert "願望ではなく世界への仮説" in text
        assert "- 予測: 扉の仕掛けが分かる" in text
        assert "tool=interact" in text
        assert "success=True" in text
        assert "result=扉は開かなかった" in text
        assert "鍵穴に青い光が見えた" in text
        assert "床板が少し沈んだ" in text
        assert "遠くで鐘が鳴った" not in text
        # 古い entry ("古い予測") にはその区間の観測だけが紐づく
        assert "- 予測: 古い予測" in text
        assert "古い予測への観測" in text

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
            [_obs(1, "扉は開かなかった")],
        )
        assert "success=False" in text
        assert "error_code=LOCKED" in text
        assert "result=鍵が足りない" in text

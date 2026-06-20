"""action_summary の表示整形 (#526 後続 PR-A)。

主観入力 (intention / expected_result / emotion_hint / reason) を行動ログの JSON
から落とし、inner_thought と結果に効く args は残す。expected_result は
``format_action_result_line_for_recent_events`` 側で [予測: ...] として別表記する。
"""

from datetime import datetime, timezone

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    format_action_result_line_for_recent_events,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.llm_argument_fingerprint import (
    build_argument_fingerprint,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    format_action_summary,
)


_FULL_ARGS = {
    "target_label": "古い祭壇",
    "action": "inspect",
    "inner_thought": "何か手がかりがあるはずだ",
    "intention": "祭壇の封印の手がかりを探す",
    "expected_result": "祭壇から封印の手がかりが得られる",
    "emotion_hint": "curiosity",
}


class TestFormatActionSummary:
    """format_action_summary が主観ノイズを落とし inner_thought と outcome args を残す。"""

    def test_hides_subjective_noise_keeps_inner_thought_and_outcome_args(self) -> None:
        """intention/expected_result/emotion_hint は出ず、inner_thought と target_label/action は残る。"""
        out = format_action_summary("spot_graph_interact", _FULL_ARGS)
        assert "target_label" in out
        assert "古い祭壇" in out
        assert "action" in out
        # inner_thought は常時表示の挙動を維持するため残す
        assert "inner_thought" in out
        assert "何か手がかりがあるはずだ" in out
        # 主観ノイズは行動ログに出さない
        assert "intention" not in out
        assert "祭壇の封印の手がかりを探す" not in out
        assert "expected_result" not in out
        assert "祭壇から封印の手がかりが得られる" not in out
        assert "emotion_hint" not in out
        assert "curiosity" not in out

    def test_no_args_returns_bare_summary(self) -> None:
        """args が空なら tool 名だけ。"""
        assert format_action_summary("spot_graph_wait", None) == "spot_graph_wait を実行しました。"

    def test_only_subjective_args_collapses_to_bare_summary(self) -> None:
        """outcome args が無く主観だけなら、落とした結果 tool 名だけになる。"""
        out = format_action_summary("noop_tool", {"intention": "x", "emotion_hint": "neutral"})
        assert out == "noop_tool を実行しました。"

    def test_fingerprint_is_independent_of_display(self) -> None:
        """loop_guard 用 fingerprint は raw args から計算され、表示整形に影響されない。"""
        # fingerprint は narrative を strip した raw args ベース (action_summary 非依存)
        fp_full = build_argument_fingerprint(_FULL_ARGS)
        fp_outcome_only = build_argument_fingerprint(
            {"target_label": "古い祭壇", "action": "inspect"}
        )
        # narrative strip 後は同一 = 表示をどう整形しても loop_guard は不変
        assert fp_full == fp_outcome_only


class TestPredictionInRecentEventsLine:
    """[予測: ...] が expected_result から行に付く / 無ければ付かない。"""

    def _entry(self, *, expected_result=None, success=True):
        return ActionResultEntry(
            occurred_at=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc),
            action_summary=format_action_summary("spot_graph_interact", _FULL_ARGS),
            result_summary="古い祭壇を調べた。石は冷たく、何も起きなかった。",
            success=success,
            error_code=None if success else "BLOCKED",
            tool_name="spot_graph_interact",
            expected_result=expected_result,
        )

    def test_prediction_label_appears_from_expected_result(self) -> None:
        """expected_result があれば [予測: ...] が行に出る。"""
        line = format_action_result_line_for_recent_events(
            self._entry(expected_result="祭壇から封印の手がかりが得られる")
        )
        assert "[予測: 祭壇から封印の手がかりが得られる]" in line
        # 「行動 → 予測 → 結果」の順
        assert line.index("[行動]") < line.index("[予測:") < line.index("[結果]")

    def test_no_prediction_label_when_expected_result_absent(self) -> None:
        """expected_result が None なら [予測: ...] は出ない。"""
        line = format_action_result_line_for_recent_events(self._entry(expected_result=None))
        assert "[予測:" not in line

    def test_prediction_label_on_failure_line(self) -> None:
        """失敗行にも [予測: ...] が付く。"""
        line = format_action_result_line_for_recent_events(
            self._entry(expected_result="開くはず", success=False)
        )
        assert "[予測: 開くはず]" in line
        assert "[失敗]" in line

    def test_action_line_has_no_subjective_json_noise(self) -> None:
        """行動行に intention/emotion_hint の生 JSON が出ない (inner_thought は残る)。"""
        line = format_action_result_line_for_recent_events(
            self._entry(expected_result="x")
        )
        assert "intention" not in line
        assert "emotion_hint" not in line
        assert "inner_thought" in line

"""action_summary の表示整形 (#552 PR-A 再実装)。

行動ログ (直近の出来事) の action_summary から主観入力 (intention /
expected_result / emotion_hint / reason) の生 JSON ノイズを落とし、inner_thought と
結果に効く args は残す共有 sanitizer。expected_result は chunk_encoding 側で
``[予測: ...]`` として別表記するので、ここでは隠す (二重表示を避ける)。
"""

from ai_rpg_world.application.llm.llm_argument_fingerprint import (
    build_argument_fingerprint,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    ACTION_SUMMARY_HIDDEN_FIELDS,
    format_action_summary_for_display,
)


_FULL_ARGS = {
    "object_label": "OBJ1",
    "action_name": "inspect",
    "inner_thought": "何か手がかりがあるはずだ",
    "intention": "祭壇の封印の手がかりを探す",
    "expected_result": "祭壇から封印の手がかりが得られる",
    "emotion_hint": "curiosity",
}


class TestFormatActionSummaryForDisplay:
    """主観ノイズを落とし inner_thought と outcome args を残す。"""

    def test_hides_subjective_noise_keeps_inner_thought_and_outcome_args(self) -> None:
        """intention/expected_result/emotion_hint は出ず、inner_thought と outcome は残る。"""
        out = format_action_summary_for_display("interact", _FULL_ARGS)
        assert "object_label" in out
        assert "OBJ1" in out
        assert "action_name" in out
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

    def test_hidden_fields_set_is_the_four_subjective_inputs(self) -> None:
        """隠すのは reason / intention / expected_result / emotion_hint の4つ (inner_thought は含まない)。"""
        assert ACTION_SUMMARY_HIDDEN_FIELDS == frozenset(
            {"reason", "intention", "expected_result", "emotion_hint"}
        )
        assert "inner_thought" not in ACTION_SUMMARY_HIDDEN_FIELDS

    def test_reason_is_hidden(self) -> None:
        """reason (主に spot_graph_wait の任意理由) は action JSON から落とす。

        wait の result_summary 側に「理由: ...」が残るので情報は消えにくい。
        将来 outcome-affecting な reason が出たら再検討する。
        """
        out = format_action_summary_for_display("wait", {"reason": "様子を見る"})
        assert out == "wait を実行しました。"

    def test_no_args_returns_bare_summary(self) -> None:
        """args が空なら tool 名だけ。"""
        assert (
            format_action_summary_for_display("wait", None)
            == "wait を実行しました。"
        )

    def test_only_subjective_args_collapses_to_bare_summary(self) -> None:
        """outcome args が無く主観だけなら、落とした結果 tool 名だけになる。"""
        out = format_action_summary_for_display(
            "noop_tool", {"intention": "x", "emotion_hint": "neutral"}
        )
        assert out == "noop_tool を実行しました。"

    def test_does_not_mutate_input_args(self) -> None:
        """入力 args を破壊しない (sanitizer は新 dict を作る / immutable)。"""
        args = dict(_FULL_ARGS)
        format_action_summary_for_display("interact", args)
        assert args == _FULL_ARGS

    def test_fingerprint_is_independent_of_display(self) -> None:
        """loop_guard 用 fingerprint は raw args から計算され、表示整形に影響されない。"""
        fp_full = build_argument_fingerprint(_FULL_ARGS)
        fp_outcome_only = build_argument_fingerprint(
            {"object_label": "OBJ1", "action_name": "inspect"}
        )
        # narrative strip 後は同一 = 表示をどう整形しても loop_guard は不変
        assert fp_full == fp_outcome_only

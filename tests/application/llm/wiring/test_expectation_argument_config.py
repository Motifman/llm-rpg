"""行動の tool に予期の引数を付ける設定を profile から入れ、組めない組み合わせを起動前に落とす (#1441)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)

_ON = {
    "TYPED_JUDGMENT_PROVIDER": "stub",
    "EXPECTATION_SETTLEMENT_ENABLED": "1",
    "PREDICTION_CONTEXT_ID_ENABLED": "1",
    "LLM_EXPECTED_RESULT_POLICY": "off",
    "EXPECTATION_ARGUMENT_ENABLED": "1",
}


def _config(**values: str) -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.from_mapping(values=values)


class TestTheProfileChoosesTheExpectationArgument:
    """有効化と期限のターン数が profile から入り、run_start の記録に残ることを保証する。"""

    def test_expectation_argument_is_off_unless_the_profile_asks_for_it(self) -> None:
        """何も書かなければ予期の引数は付かず、期限のターン数は 1 以上の既定値になる。"""
        config = _config()

        assert config.expectation_argument_enabled is False
        assert config.expectation_undated_term_turns >= 1
        assert config.expectation_dated_term_turns >= 1

    def test_the_profile_sets_the_terms_and_they_reach_run_start(self) -> None:
        """期限のターン数を書くと解決済み設定に載り、run_start に残る trace 表現にも出る。"""
        config = _config(
            **_ON,
            EXPECTATION_UNDATED_TERM_TURNS="3",
            EXPECTATION_DATED_TERM_TURNS="12",
        )

        trace = config.to_trace_dict()
        assert trace["expectation_argument_enabled"] is True
        assert trace["expectation_undated_term_turns"] == 3
        assert trace["expectation_dated_term_turns"] == 12


class TestUnusableCombinationsFailBeforeTheRun:
    """予期を積んでも清算も帰属もされない組み合わせを、run の前に ValueError で落とすことを保証する。"""

    def test_enabling_without_settlement_fails(self) -> None:
        """清算が off のまま予期の引数を有効にすると、積んだ予期が閉じられず増え続けるので ValueError を投げる。"""
        values = {**_ON, "EXPECTATION_SETTLEMENT_ENABLED": "0"}

        with pytest.raises(ValueError, match="EXPECTATION_SETTLEMENT_ENABLED"):
            _config(**values)

    def test_enabling_without_prediction_context_fails(self) -> None:
        """プロンプトに載った信念と想起を記録する台帳が off のまま有効にすると、頭にあった信念が常に空になるので ValueError を投げる。"""
        values = {**_ON, "PREDICTION_CONTEXT_ID_ENABLED": "0"}

        with pytest.raises(ValueError, match="PREDICTION_CONTEXT_ID_ENABLED"):
            _config(**values)

    @pytest.mark.parametrize("policy", ["optional", "required"])
    def test_enabling_with_expected_result_fails(self, policy: str) -> None:
        """expected_result を出す設定と同時に有効にすると、予測を書く欄が 2 つ並ぶので ValueError を投げる。"""
        values = {**_ON, "LLM_EXPECTED_RESULT_POLICY": policy}

        with pytest.raises(ValueError, match="LLM_EXPECTED_RESULT_POLICY"):
            _config(**values)

    @pytest.mark.parametrize(
        "key", ["EXPECTATION_UNDATED_TERM_TURNS", "EXPECTATION_DATED_TERM_TURNS"]
    )
    def test_non_positive_term_fails(self, key: str) -> None:
        """期限のターン数に 0 を書くと ValueError を投げる。"""
        with pytest.raises(ValueError, match=key):
            _config(**_ON, **{key: "0"})

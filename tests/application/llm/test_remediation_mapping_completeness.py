"""``DEFAULT_REMEDIATION_BY_ERROR_CODE`` に本番で使われている error_code が
全て登録されている (Y_after_pr639_640 後続、PR-γ)。

## なぜ

``get_remediation(code)`` は未登録 code に対しては汎用フォールバック
「エラー内容を確認し、別の行動を選んでください。」を返す。これでは
LLM が具体的に何を直せばいいか分からず、次アクションを選べない。

Explore agent audit で、以下 5 code は本番の executor から
``LlmCommandResultDto(error_code=...)`` に埋め込まれているが、
``remediation_mapping.py`` に未登録だった:

- ``INVALID_STATE`` (episodic recall 等の 5 箇所)
- ``UNSUPPORTED_TOOL`` (未配線 tool の 3 箇所 + typo 救済 fallback)
- ``ATTACK_FAILED`` (attack orchestrator 失敗)
- ``EXHAUSTED`` (疲労限界で重い tool block)
- ``INTERACTION_PRECONDITION_FAILED`` (gather 等の precondition 未達)

本 PR で 5 code 分の具体的 remediation を追加する。LLM が「対処:」欄を
読んで次アクションを選べるようにする。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.remediation_mapping import (
    DEFAULT_REMEDIATION_BY_ERROR_CODE,
    get_remediation,
)


class TestNewlyAddedRemediationCodes:
    """PR-γ で追加した 5 code に具体的な remediation がある。"""

    @pytest.mark.parametrize(
        "code",
        [
            "INVALID_STATE",
            "UNSUPPORTED_TOOL",
            "ATTACK_FAILED",
            "EXHAUSTED",
            "INTERACTION_PRECONDITION_FAILED",
        ],
    )
    def test_code_mapping(self, code: str) -> None:
        """code が mapping に登録されている。"""
        assert code in DEFAULT_REMEDIATION_BY_ERROR_CODE, (
            f"{code} が remediation_mapping に未登録。汎用フォールバック "
            "「エラー内容を確認し...」に落ちて LLM が対処を選べない"
        )

    def test_exhausted_remediation_wait(self) -> None:
        """疲労限界で重い tool が block されているケース → 回復手段を示唆。"""
        msg = get_remediation("EXHAUSTED")
        assert "wait" in msg or "回復" in msg or "食事" in msg or "食べる" in msg

    def test_interaction_precondition_failed_remediation_object_state(self) -> None:
        """gather の枯渇 / 既に開けた箱の再操作 → object 状態の再確認を示唆。"""
        msg = get_remediation("INTERACTION_PRECONDITION_FAILED")
        assert "状態" in msg or "object" in msg.lower() or "オブジェクト" in msg

    def test_unsupported_tool_remediation_tool(self) -> None:
        """typo / 未配線 tool の呼び出し → 有効 tool 一覧の確認を示唆。"""
        msg = get_remediation("UNSUPPORTED_TOOL")
        assert (
            "tool" in msg.lower()
            or "ツール" in msg
            or "利用可能" in msg
        )

    def test_attack_failed_remediation_target_state(self) -> None:
        """attack が失敗 → 対象状態 (死骸 / 逃走 / 距離) の確認を示唆。"""
        msg = get_remediation("ATTACK_FAILED")
        assert "対象" in msg or "状態" in msg or "モンスター" in msg

    def test_invalid_state_remediation(self) -> None:
        """内部整合性違反系。LLM は再試行するか別の tool を選ぶかの判断が必要。"""
        msg = get_remediation("INVALID_STATE")
        assert "一時" in msg or "再試" in msg or "別" in msg

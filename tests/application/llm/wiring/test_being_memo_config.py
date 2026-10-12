"""メモ帳と引数 memo を有効にする設定を profile から入れ、古いメモの道具と並ぶ組み合わせを起動前に落とす (#1628)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


def _config(**values: str) -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.from_mapping(values=values)


class TestTheProfileChoosesTheMemoBook:
    """メモ帳は既定で off で、profile で有効にすると run_start の記録に残ることを保証する。"""

    def test_memo_book_is_off_unless_the_profile_asks_for_it(self) -> None:
        """何も書かなければメモ帳は無効で、今のメモの道具は有効のまま。"""
        config = _config()

        assert (config.being_memo_enabled, config.memo_tools_enabled) == (False, True)

    def test_enabling_with_the_old_memo_tools_off_reaches_run_start(self) -> None:
        """今のメモの道具を止めてメモ帳を有効にすると、解決済み設定と run_start の記録に載る。"""
        config = _config(BEING_MEMO_ENABLED="1", MEMO_TOOLS_ENABLED="false")

        assert config.to_trace_dict()["being_memo_enabled"] is True

    def test_enabling_beside_the_old_memo_tools_fails(self) -> None:
        """今のメモの道具を残したままメモ帳を有効にすると、書く口とメモの欄が 2 つずつ並ぶので ValueError を投げる。"""
        with pytest.raises(ValueError, match="MEMO_TOOLS_ENABLED"):
            _config(BEING_MEMO_ENABLED="1")

    def test_for_tests_rejects_the_same_combination(self) -> None:
        """from_mapping を通らない組み立てでも、同じ組み合わせを ValueError で落とす。"""
        with pytest.raises(ValueError, match="MEMO_TOOLS_ENABLED"):
            ResolvedLlmRuntimeConfig.for_tests(being_memo_enabled=True)

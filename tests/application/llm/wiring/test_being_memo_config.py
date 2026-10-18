"""メモ帳と引数 memo を有効にする設定を profile から入れることを保証する (#1628)。"""

from __future__ import annotations

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


def _config(**values: str) -> ResolvedLlmRuntimeConfig:
    return ResolvedLlmRuntimeConfig.from_mapping(values=values)


class TestTheProfileChoosesTheMemoBook:
    """メモ帳は既定で off で、profile で有効にすると run_start の記録に残ることを保証する。"""

    def test_memo_book_is_off_unless_the_profile_asks_for_it(self) -> None:
        """何も書かなければメモ帳は無効。"""
        config = _config()

        assert config.being_memo_enabled is False

    def test_enabling_reaches_run_start(self) -> None:
        """BEING_MEMO_ENABLED=1 と書くと、解決済み設定と run_start の記録に載る。"""
        config = _config(BEING_MEMO_ENABLED="1")

        assert config.to_trace_dict()["being_memo_enabled"] is True

    def test_for_tests_accepts_the_memo_book(self) -> None:
        """from_mapping を通らない組み立てでも、メモ帳だけを有効にした設定を組める。"""
        config = ResolvedLlmRuntimeConfig.for_tests(being_memo_enabled=True)

        assert config.being_memo_enabled is True

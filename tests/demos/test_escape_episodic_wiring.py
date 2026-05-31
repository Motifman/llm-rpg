"""``demos/escape_game/escape_episodic_wiring.py`` の単体テスト (Issue #283 後続)。

検証:
- ``is_episodic_enabled`` の env 解釈
- ``build_scenario_noun_matcher`` がシナリオから固有名詞を拾う
- ``build_escape_episodic_stack`` が chunk_coordinator + passive_recall +
  noun_matcher を組み立てて返す
- ``create_escape_game_runtime`` が env=0/未設定で episodic_stack=None を
  維持し、env=1 で stack を構築する (configurable on/off の確認)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from demos.escape_game.escape_episodic_wiring import (
    build_escape_episodic_stack,
    build_scenario_noun_matcher,
    is_episodic_enabled,
)


class TestIsEpisodicEnabled:
    """``LLM_EPISODIC_ENABLED`` の env 解釈。"""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("1", True),
            ("true", True),
            ("True", True),
            ("YES", True),
            ("yes", True),
            ("on", True),
            ("0", False),
            ("false", False),
            ("", False),
            ("garbage", False),
        ],
    )
    def test_各種文字列の解釈(self, raw: str, expected: bool) -> None:
        env = {"LLM_EPISODIC_ENABLED": raw}
        assert is_episodic_enabled(env) is expected

    def test_未設定なら_False(self) -> None:
        assert is_episodic_enabled({}) is False


class TestBuildScenarioNounMatcher:
    """シナリオ → 固有名詞 matcher 抽出 (env=1 で構築された runtime から検証)。"""

    def test_spot_と_character_の名前が登録される(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """env を有効化して runtime を作り、内部の matcher を直接調べる。"""
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        from demos.escape_game.escape_game_runtime import create_escape_game_runtime

        scenario_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "scenarios"
            / "forbidden_library_demo.json"
        )
        runtime = create_escape_game_runtime(scenario_path)
        matcher = runtime._episodic_stack.noun_matcher

        # spot 名 (forbidden_library_demo に存在する) → place_spot cue
        result_spot = matcher.find_in_text("閲覧室に戻る")
        assert any(m.axis == "place_spot" for m in result_spot)
        # character 名 → entity cue
        result_char = matcher.find_in_text("リンが手記を読んだ")
        assert any(m.axis == "entity" for m in result_char)


class TestEscapeGameRuntimeEpisodicSwitch:
    """``create_escape_game_runtime`` が env で episodic を on/off 切替する。"""

    def test_env_未設定なら_episodic_stack_は_None(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LLM_EPISODIC_ENABLED", raising=False)
        from demos.escape_game.escape_game_runtime import create_escape_game_runtime

        scenario_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "scenarios"
            / "forbidden_library_demo.json"
        )
        runtime = create_escape_game_runtime(scenario_path)
        assert runtime._episodic_stack is None

    def test_env_1_なら_episodic_stack_が組み立てられる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        from demos.escape_game.escape_game_runtime import create_escape_game_runtime

        scenario_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "scenarios"
            / "forbidden_library_demo.json"
        )
        runtime = create_escape_game_runtime(scenario_path)
        assert runtime._episodic_stack is not None
        # 主要 3 要素が揃っている
        assert runtime._episodic_stack.chunk_coordinator is not None
        assert runtime._episodic_stack.passive_recall is not None
        assert runtime._episodic_stack.noun_matcher is not None

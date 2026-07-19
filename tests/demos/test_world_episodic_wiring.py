"""``demos/world_runtime/world_episodic_wiring.py`` の単体テスト (Issue #283 後続)。

検証:
- ``is_episodic_enabled`` の env 解釈
- ``build_scenario_noun_matcher`` がシナリオから固有名詞を拾う
- ``build_world_episodic_stack`` が chunk_coordinator + passive_recall +
  noun_matcher を組み立てて返す
- ``create_world_runtime`` が runtime_config で episodic_stack の有無を
  切り替える
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_episodic_wiring import (
    build_world_episodic_stack,
    build_scenario_noun_matcher,
    is_episodic_enabled,
    is_episodic_subjective_enabled,
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
    def test_string(self, raw: str, expected: bool) -> None:
        """各種文字列の解釈。"""
        env = {"LLM_EPISODIC_ENABLED": raw}
        assert is_episodic_enabled(env) is expected

    def test_unset_false(self) -> None:
        """未設定なら False。"""
        assert is_episodic_enabled({}) is False


class TestIsEpisodicSubjectiveEnabled:
    """``LLM_EPISODIC_SUBJECTIVE_ENABLED`` の env 解釈。**既定 True**。

    第22回実験以降「エピソード記憶を使うときは LLM 補完も既定で走らせたい」
    方針になったため、明示的に OFF にしたいときだけ falsy 値を指定する。
    """

    def test_unset_true_default(self) -> None:
        """key 自体が無いとき既定 ON。"""
        assert is_episodic_subjective_enabled({}) is True

    def test_empty_string_true_default(self) -> None:
        """空文字は「key だけ設定されたが値なし」と同じ扱いで既定 ON。"""
        assert is_episodic_subjective_enabled({"LLM_EPISODIC_SUBJECTIVE_ENABLED": ""}) is True

    @pytest.mark.parametrize("raw", ["0", "false", "False", "no", "NO", "off"])
    def test_off_string_false(self, raw: str) -> None:
        """明示的 off 文字列で False。"""
        assert is_episodic_subjective_enabled({"LLM_EPISODIC_SUBJECTIVE_ENABLED": raw}) is False

    @pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on"])
    def test_string_true(self, raw: str) -> None:
        """明示的 on 文字列で True。"""
        assert is_episodic_subjective_enabled({"LLM_EPISODIC_SUBJECTIVE_ENABLED": raw}) is True

    def test_value_true_default(self) -> None:
        """誤設定で機能が消えるより、on 側に倒して通知する方が安全。"""
        assert is_episodic_subjective_enabled({"LLM_EPISODIC_SUBJECTIVE_ENABLED": "garbage"}) is True


class TestBuildScenarioNounMatcher:
    """シナリオ → 固有名詞 matcher 抽出 (config で構築された runtime から検証)。"""

    def test_spot_character_name(self) -> None:
        """config で有効化して runtime を作り、内部の matcher を直接調べる。"""
        from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
            ResolvedLlmRuntimeConfig,
        )
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

        scenario_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "scenarios"
            / "forbidden_library_demo.json"
        )
        runtime = create_world_runtime(
            scenario_path,
            config=ResolvedLlmRuntimeConfig.for_tests(episodic_enabled=True),
        )
        matcher = runtime._episodic_stack.noun_matcher

        # spot 名 (forbidden_library_demo に存在する) → place_spot cue
        result_spot = matcher.find_in_text("閲覧室に戻る")
        assert any(m.axis == "place_spot" for m in result_spot)
        # character 名 → entity cue
        result_char = matcher.find_in_text("リンが手記を読んだ")
        assert any(m.axis == "entity" for m in result_char)


class TestWorldRuntimeEpisodicSwitch:
    """``create_world_runtime`` が config で episodic を on/off 切替する。"""

    def test_config_unspecified_episodic_stack_none(self) -> None:
        """config 未指定なら episodic stack は None。"""
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

        scenario_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "scenarios"
            / "forbidden_library_demo.json"
        )
        runtime = create_world_runtime(scenario_path)
        assert runtime._episodic_stack is None

    def test_config_episodic_stack_built(self) -> None:
        """config で有効化すると episodic stack が組み立てられる。"""
        from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
            ResolvedLlmRuntimeConfig,
        )
        from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

        scenario_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "scenarios"
            / "forbidden_library_demo.json"
        )
        runtime = create_world_runtime(
            scenario_path,
            config=ResolvedLlmRuntimeConfig.for_tests(episodic_enabled=True),
        )
        assert runtime._episodic_stack is not None
        # 主要 3 要素が揃っている
        assert runtime._episodic_stack.chunk_coordinator is not None
        assert runtime._episodic_stack.passive_recall is not None
        assert runtime._episodic_stack.noun_matcher is not None

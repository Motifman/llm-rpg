"""world_runtime runtime の semantic フラグ配線の統合テスト (#526 後続)。

`SEMANTIC_LLM_GIST_ENABLED` で world_runtime でも semantic memory (学びを作る
promotion) を on/off できることを検証する。学びを prompt に出す【関連する学び】は
#1631 で消した。

LLM は呼ばない (LLM_CLIENT=stub なので gist service は組まれない)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

# 循環 import 回避の warm-up。
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from tests.runtime_config_helpers import episodic_config, runtime_config

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _build_runtime(config=None):
    from ai_rpg_world.application.world_runtime.world_runtime import (
        create_world_runtime,
    )

    return create_world_runtime(_SCENARIO_PATH, config=config or runtime_config())


class TestWorldRuntimeSemanticFlagOff:
    """フラグ未設定なら従来どおり semantic は配線されない (後方互換)。"""

    def test_semantic_absent_when_flags_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runtime = _build_runtime(episodic_config())
        stack = runtime._episodic_stack
        assert stack is not None
        assert stack.episodic_semantic_promotion is None
        assert stack.semantic_memory_store is None


class TestWorldRuntimeSemanticFlagOn:
    """SEMANTIC_LLM_GIST_ENABLED で semantic が配線される。"""

    def test_semantic_wired_when_gist_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """フラグ ON で promotion / store が配線される。"""
        runtime = _build_runtime(episodic_config(semantic_llm_gist_enabled=True))
        stack = runtime._episodic_stack
        assert stack is not None
        # 学びを作る promotion hook も配線される (これが無いと store が空のまま)
        assert stack.episodic_semantic_promotion is not None
        assert stack.semantic_memory_store is not None

    def test_link_service_wired_to_prompt_builder_for_recall_strengthening(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """semantic ON のとき、想起→強化 (recall_count 加算 / CO_RECALL リンク /
        ヘブ則強化) を担う link service が prompt builder まで配線される。

        これが欠けると想起は成立しても recall_count が永遠に 0 のままになり、
        昇格ゲート (recall_count>=3) を誰も超えられず、学びが 1 件も生まれない
        (全機能 ON 実験 memory_full_002 で発覚した静かな失敗)。
        """
        runtime = _build_runtime(episodic_config(semantic_llm_gist_enabled=True))
        stack = runtime._episodic_stack
        assert stack.link_service is not None
        builder = runtime._get_or_build_default_prompt_builder()
        assert builder._episodic_memory_link_service is stack.link_service

    def test_semantic_on_exposes_memory_link_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """semantic ON では昇格根拠の memory_link_store も公開される
        (semantic entries だけ保存され link graph が空 fallback になるのを防ぐ)。"""
        runtime = _build_runtime(episodic_config(semantic_llm_gist_enabled=True))
        assert runtime._episodic_stack.memory_link_store is not None
        # snapshot stub が semantic store と memory_link_store の両方を拾う
        from scripts.run_scenario_experiment import _wiring_stub_from_world_runtime

        stub = _wiring_stub_from_world_runtime(runtime)
        assert stub.semantic_memory_store is not None
        assert stub.memory_link_store is not None


class TestWorldRuntimeSemanticConfigWins:
    """create_world_runtime(config=...) が semantic 設定の単一入口になる。"""

    def test_config_on_beats_env_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """config で gist を有効にすると semantic が配線される。"""
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )

        cfg = episodic_config(semantic_llm_gist_enabled=True)
        runtime = create_world_runtime(_SCENARIO_PATH, config=cfg)
        assert runtime._episodic_stack.semantic_memory_store is not None

    def test_config_off_beats_env_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """config で gist を無効にすると semantic は配線されない。"""
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )

        cfg = episodic_config(semantic_llm_gist_enabled=False)
        runtime = create_world_runtime(_SCENARIO_PATH, config=cfg)
        assert runtime._episodic_stack.semantic_memory_store is None


"""escape_game runtime の semantic フラグ配線の統合テスト (#526 後続)。

`SEMANTIC_PASSIVE_TOP_K` / `SEMANTIC_LLM_GIST_ENABLED` で escape_game でも
semantic memory (学びを作る promotion + 出す passive recall) を on/off できる
ことを検証する。従来 escape_game は semantic 層を持たず、実験経路で予測→学習
ループが閉じ切らなかった。

LLM は呼ばない (gist OFF = 決定論 / passive recall は store を読むだけ)。
"""

from __future__ import annotations

# 循環 import 回避の warm-up。
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _build_runtime(monkeypatch: pytest.MonkeyPatch):
    from ai_rpg_world.application.escape_game.escape_game_runtime import (
        create_escape_game_runtime,
    )

    return create_escape_game_runtime(_SCENARIO_PATH)


def _resolve_player_id(runtime, name: str) -> PlayerId:
    for spawn in runtime.scenario.player_spawns:
        if spawn.name == name:
            return PlayerId(spawn.player_id)
    raise AssertionError(f"player {name!r} not found")


class TestEscapeGameSemanticFlagOff:
    """フラグ未設定なら従来どおり semantic は配線されない (後方互換)。"""

    def test_semantic_absent_when_flags_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.delenv("SEMANTIC_PASSIVE_TOP_K", raising=False)
        monkeypatch.delenv("SEMANTIC_LLM_GIST_ENABLED", raising=False)
        runtime = _build_runtime(monkeypatch)
        stack = runtime._episodic_stack
        assert stack is not None
        assert stack.semantic_passive_recall is None
        assert stack.semantic_passive_top_k == 0
        assert stack.episodic_semantic_promotion is None
        assert stack.semantic_memory_store is None


class TestEscapeGameSemanticFlagOn:
    """SEMANTIC_PASSIVE_TOP_K>0 で semantic が配線され、学びが prompt に戻る。"""

    def test_semantic_wired_when_top_k_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """フラグ ON で passive recall / promotion / store が配線される。"""
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("SEMANTIC_PASSIVE_TOP_K", "3")
        monkeypatch.delenv("SEMANTIC_LLM_GIST_ENABLED", raising=False)
        runtime = _build_runtime(monkeypatch)
        stack = runtime._episodic_stack
        assert stack is not None
        assert stack.semantic_passive_recall is not None
        assert stack.semantic_passive_top_k == 3
        # 学びを作る promotion hook も配線される (これが無いと store が空のまま)
        assert stack.episodic_semantic_promotion is not None
        assert stack.semantic_memory_store is not None

    def test_seeded_learning_surfaces_in_prompt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """semantic store にある学びが【関連する学び】section に戻る
        (= white-box 注入なしでループの「学び→次の予測」が閉じる)。"""
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("SEMANTIC_PASSIVE_TOP_K", "3")
        runtime = _build_runtime(monkeypatch)
        rin_id = _resolve_player_id(runtime, "リン")
        being = runtime._aux_being_resolver.resolve_being_id(
            runtime._aux_being_default_world_id, rin_id
        )
        assert being is not None
        runtime._episodic_stack.semantic_memory_store.add_by_being(
            being,
            SemanticMemoryEntry(
                entry_id="sem-flag-1",
                player_id=int(rin_id.value),
                text="SEMANTIC_FLAG_MARKER: ノアは機嫌が悪いと無視する",
                evidence_episode_ids=("ep-1",),
                confidence=0.7,
                created_at=datetime.now(timezone.utc) - timedelta(hours=1),
                importance_score=8,
                tags=("ノア",),
            ),
        )
        prompt = runtime.build_full_prompt(rin_id)
        user = "\n".join(
            m.get("content", "")
            for m in prompt.get("messages", [])
            if m.get("role") == "user"
        )
        assert "【関連する学び】" in user
        assert "SEMANTIC_FLAG_MARKER" in user

    def test_semantic_on_exposes_memory_link_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """semantic ON では昇格根拠の memory_link_store も公開される
        (semantic entries だけ保存され link graph が空 fallback になるのを防ぐ)。"""
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("SEMANTIC_PASSIVE_TOP_K", "3")
        runtime = _build_runtime(monkeypatch)
        assert runtime._episodic_stack.memory_link_store is not None
        # snapshot stub が semantic store と memory_link_store の両方を拾う
        from scripts.run_scenario_experiment import _wiring_stub_from_escape_runtime

        stub = _wiring_stub_from_escape_runtime(runtime)
        assert stub.semantic_memory_store is not None
        assert stub.memory_link_store is not None


class TestEscapeGameSemanticConfigWins:
    """create_escape_game_runtime(config=...) の semantic 設定が env に勝つ
    (HIGH: silent config drift 防止)。短期記憶 (TestConfigInjection) と同じ契約。"""

    def _cfg(self, **overrides):
        from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
            ResolvedLlmRuntimeConfig,
        )

        return ResolvedLlmRuntimeConfig.for_tests(**overrides)

    def test_config_on_beats_env_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env で semantic OFF でも config で top_k=3 なら配線される。"""
        from ai_rpg_world.application.escape_game.escape_game_runtime import (
            create_escape_game_runtime,
        )

        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.delenv("SEMANTIC_PASSIVE_TOP_K", raising=False)
        cfg = self._cfg(semantic_passive_top_k=3)
        runtime = create_escape_game_runtime(_SCENARIO_PATH, config=cfg)
        assert runtime._episodic_stack.semantic_passive_top_k == 3
        assert runtime._episodic_stack.semantic_passive_recall is not None

    def test_config_off_beats_env_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """env で semantic ON でも config で top_k=0 なら配線されない。"""
        from ai_rpg_world.application.escape_game.escape_game_runtime import (
            create_escape_game_runtime,
        )

        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("SEMANTIC_PASSIVE_TOP_K", "5")
        cfg = self._cfg(semantic_passive_top_k=0)
        runtime = create_escape_game_runtime(_SCENARIO_PATH, config=cfg)
        assert runtime._episodic_stack.semantic_passive_top_k == 0
        assert runtime._episodic_stack.semantic_passive_recall is None

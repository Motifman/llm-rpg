"""world_runtime runtime の semantic フラグ配線の統合テスト (#526 後続)。

`SEMANTIC_PASSIVE_TOP_K` / `SEMANTIC_LLM_GIST_ENABLED` で world_runtime でも
semantic memory (学びを作る promotion + 出す passive recall) を on/off できる
ことを検証する。従来 world_runtime は semantic 層を持たず、実験経路で予測→学習
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


def _resolve_player_id(runtime, name: str) -> PlayerId:
    for spawn in runtime.scenario.player_spawns:
        if spawn.name == name:
            return PlayerId(spawn.player_id)
    raise AssertionError(f"player {name!r} not found")


class TestWorldRuntimeSemanticFlagOff:
    """フラグ未設定なら従来どおり semantic は配線されない (後方互換)。"""

    def test_semantic_absent_when_flags_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runtime = _build_runtime(episodic_config())
        stack = runtime._episodic_stack
        assert stack is not None
        assert stack.semantic_passive_recall is None
        assert stack.semantic_passive_top_k == 0
        assert stack.episodic_semantic_promotion is None
        assert stack.semantic_memory_store is None


class TestWorldRuntimeSemanticFlagOn:
    """SEMANTIC_PASSIVE_TOP_K>0 で semantic が配線され、学びが prompt に戻る。"""

    def test_semantic_wired_when_top_k_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """フラグ ON で passive recall / promotion / store が配線される。"""
        runtime = _build_runtime(episodic_config(semantic_passive_top_k=3))
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
        runtime = _build_runtime(episodic_config(semantic_passive_top_k=3))
        rin_id = _resolve_player_id(runtime, "リン")
        being = runtime.aux_being_resolver.resolve_being_id(
            runtime.aux_being_default_world_id, rin_id
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

    def test_link_service_wired_to_prompt_builder_for_recall_strengthening(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """semantic ON のとき、想起→強化 (recall_count 加算 / CO_RECALL リンク /
        ヘブ則強化) を担う link service が prompt builder まで配線される。

        これが欠けると想起は成立しても recall_count が永遠に 0 のままになり、
        昇格ゲート (recall_count>=3) を誰も超えられず、学びが 1 件も生まれない
        (全機能 ON 実験 memory_full_002 で発覚した静かな失敗)。
        """
        runtime = _build_runtime(episodic_config(semantic_passive_top_k=3))
        stack = runtime._episodic_stack
        assert stack.link_service is not None
        builder = runtime._get_or_build_default_prompt_builder()
        assert builder._episodic_memory_link_service is stack.link_service

    def test_semantic_on_exposes_memory_link_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """semantic ON では昇格根拠の memory_link_store も公開される
        (semantic entries だけ保存され link graph が空 fallback になるのを防ぐ)。"""
        runtime = _build_runtime(episodic_config(semantic_passive_top_k=3))
        assert runtime._episodic_stack.memory_link_store is not None
        # snapshot stub が semantic store と memory_link_store の両方を拾う
        from scripts.run_scenario_experiment import _wiring_stub_from_world_runtime

        stub = _wiring_stub_from_world_runtime(runtime)
        assert stub.semantic_memory_store is not None
        assert stub.memory_link_store is not None


class TestWorldRuntimeSemanticConfigWins:
    """create_world_runtime(config=...) が semantic 設定の単一入口になる。"""

    def test_config_on_beats_env_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """config で top_k=3 なら semantic が配線される。"""
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )

        cfg = episodic_config(semantic_passive_top_k=3)
        runtime = create_world_runtime(_SCENARIO_PATH, config=cfg)
        assert runtime._episodic_stack.semantic_passive_top_k == 3
        assert runtime._episodic_stack.semantic_passive_recall is not None

    def test_config_off_beats_env_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """config で top_k=0 なら semantic は配線されない。"""
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )

        cfg = episodic_config(semantic_passive_top_k=0)
        runtime = create_world_runtime(_SCENARIO_PATH, config=cfg)
        assert runtime._episodic_stack.semantic_passive_top_k == 0
        assert runtime._episodic_stack.semantic_passive_recall is None


class TestWorldRuntimeReinterpretationSnapshotSurface:
    """U3/#558 MEDIUM-2: reinterpretation ON のとき snapshot stub が journal を拾う
    (= save/load で再解釈 journal を silent に失わない / 自己の継続性)。"""

    def test_stub_exposes_reinterpretation_journal_when_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """reinterpretation ON の runtime から stub が journal を expose する。"""
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )
        from scripts.run_scenario_experiment import _wiring_stub_from_world_runtime

        cfg = episodic_config(episodic_reinterpretation_enabled=True)
        runtime = create_world_runtime(_SCENARIO_PATH, config=cfg)
        assert runtime._episodic_stack.reinterpretation_journal is not None

        stub = _wiring_stub_from_world_runtime(runtime)
        # journal は reinterpretation ON で常に非 None (空でも save 対象)。
        assert stub.episodic_reinterpretation_journal_store is not None
        assert (
            stub.episodic_reinterpretation_journal_store
            is runtime._episodic_stack.reinterpretation_journal
        )

    def test_stub_journal_none_when_reinterpretation_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """reinterpretation OFF では stub の journal は None (従来どおり)。"""
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )
        from scripts.run_scenario_experiment import _wiring_stub_from_world_runtime

        cfg = episodic_config()
        runtime = create_world_runtime(_SCENARIO_PATH, config=cfg)
        stub = _wiring_stub_from_world_runtime(runtime)
        assert stub.episodic_reinterpretation_journal_store is None
        assert stub.episodic_recall_buffer_store is None

"""U7 (予測誤差統一設計 / 無意識コンテキスト): world_runtime を通した provider
配線を end-to-end で確認する。

``UNCONSCIOUS_CONTEXT_ENABLED`` フラグが ``create_world_runtime`` を通して
非同期 chunk 主観補完経路 (``ThreadPoolEpisodicSubjectiveScheduler`` が保持する
``EpisodicChunkSubjectiveFieldsService``) まで届き、実際の semantic store から
belief top-K を引けることを検証する。単一注入 (service 内 1 箇所) の設計上、
coordinator / scheduler 自体には手を入れていないので、この配線が壊れると
無意識コンテキストは静かに機能しなくなる (= 本テストがその安全網)。

LLM は呼ばない。``LLM_CLIENT=litellm`` はダミー API key で ``LiteLLMClient``
インスタンスを作るためだけに使う (構築時点では通信しない)。provider の実行は
``_service._unconscious_context_provider`` を直接呼ぶ形で検証し、非同期
スレッドプールの完了待ちに依存しない決定論的なテストにする。
"""

from __future__ import annotations

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


def _enable_litellm_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """subjective service (= LiteLLMClient 前提) を wire するための最小 env。

    実 API は呼ばない。ダミー key + model は ``LiteLLMClient`` を構築できる
    ようにするためだけ (PR #444 の timeout smoke と同じ手法)。
    """
    monkeypatch.setenv("LLM_CLIENT", "litellm")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")


def _resolve_player_id(runtime, name: str) -> PlayerId:
    for spawn in runtime.scenario.player_spawns:
        if spawn.name == name:
            return PlayerId(spawn.player_id)
    raise AssertionError(f"player {name!r} not found")


def _build_runtime(monkeypatch: pytest.MonkeyPatch):
    from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

    return create_world_runtime(_SCENARIO_PATH)


class TestUnconsciousContextWiringFlagOn:
    def test_semantic_stack_は_top_k_未指定でも強制的に組まれる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """belief top-K を読むには semantic_memory_store が要るため、
        SEMANTIC_PASSIVE_TOP_K=0 のままでも UNCONSCIOUS_CONTEXT_ENABLED だけで
        semantic スタックが組まれる (= _semantic_enabled 強制の確認)。"""
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("UNCONSCIOUS_CONTEXT_ENABLED", "1")
        monkeypatch.delenv("SEMANTIC_PASSIVE_TOP_K", raising=False)
        monkeypatch.delenv("SEMANTIC_LLM_GIST_ENABLED", raising=False)

        runtime = _build_runtime(monkeypatch)
        stack = runtime._episodic_stack
        assert stack is not None
        assert stack.semantic_memory_store is not None
        # top_k 自体は 0 のまま (= 【関連する学び】section は出さない、無意識
        # コンテキストとは独立した knob であることの確認)。
        assert stack.semantic_passive_top_k == 0

    def test_subjective_service_に_flagとproviderが届く(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("UNCONSCIOUS_CONTEXT_ENABLED", "1")
        _enable_litellm_client(monkeypatch)

        runtime = _build_runtime(monkeypatch)
        stack = runtime._episodic_stack
        assert stack is not None
        scheduler = stack.subjective_completion_scheduler
        assert scheduler is not None, (
            "LLM_CLIENT=litellm なのに subjective scheduler が wire されていない"
        )
        service = scheduler._service
        assert service._unconscious_context_enabled is True
        assert service._unconscious_context_provider is not None

    def test_provider_が実際に_semantic_store_から_belief_を引ける(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """holder 経由の遅延解決が正しく機能し、seed した belief が provider
        経由で「## いまの自分」相当のテキストとして返ること。"""
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("UNCONSCIOUS_CONTEXT_ENABLED", "1")
        _enable_litellm_client(monkeypatch)

        runtime = _build_runtime(monkeypatch)
        stack = runtime._episodic_stack
        assert stack is not None
        rin_id = _resolve_player_id(runtime, "リン")
        being = runtime._aux_being_resolver.resolve_being_id(
            runtime._aux_being_default_world_id, rin_id
        )
        assert being is not None
        stack.semantic_memory_store.add_by_being(
            being,
            SemanticMemoryEntry(
                entry_id="unconscious-ctx-1",
                player_id=int(rin_id.value),
                text="UNCONSCIOUS_CONTEXT_MARKER: 書架Aにはよく罠がある",
                evidence_episode_ids=("ep-1",),
                confidence=0.75,
                created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
                importance_score=7,
                tags=("書架A",),
            ),
        )

        service = stack.subjective_completion_scheduler._service
        text = service._unconscious_context_provider(int(rin_id.value), ())

        assert "UNCONSCIOUS_CONTEXT_MARKER: 書架Aにはよく罠がある" in text
        assert "確信度: 0.75" in text


class TestUnconsciousContextWiringFlagOff:
    """flag OFF (default) では従来どおり provider が呼ばれる余地すら無い。"""

    def test_flag_未設定なら_service_のunconscious_context_enabledはFalse(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.delenv("UNCONSCIOUS_CONTEXT_ENABLED", raising=False)
        _enable_litellm_client(monkeypatch)

        runtime = _build_runtime(monkeypatch)
        stack = runtime._episodic_stack
        assert stack is not None
        scheduler = stack.subjective_completion_scheduler
        assert scheduler is not None
        service = scheduler._service
        assert service._unconscious_context_enabled is False
        assert service._unconscious_context_provider is None

    def test_flag_OFFなら_semantic_top_k_0のまま_semantic_stackは組まれない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.delenv("UNCONSCIOUS_CONTEXT_ENABLED", raising=False)
        monkeypatch.delenv("SEMANTIC_PASSIVE_TOP_K", raising=False)
        monkeypatch.delenv("SEMANTIC_LLM_GIST_ENABLED", raising=False)
        monkeypatch.delenv("BELIEF_CONSOLIDATION_ENABLED", raising=False)

        runtime = _build_runtime(monkeypatch)
        stack = runtime._episodic_stack
        assert stack is not None
        assert stack.semantic_memory_store is None

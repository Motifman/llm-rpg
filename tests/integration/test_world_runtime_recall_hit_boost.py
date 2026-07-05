"""U9b (予測誤差統一設計 部品5・想起の信用割り当て): world_runtime を通した

的中側 sidecar (recall_success_store) の配線を end-to-end で確認する。

``RECALL_HIT_BOOST_ENABLED`` フラグが ``create_world_runtime`` を通して
同期経路 (``EpisodicChunkCoordinator``)、非同期経路
(``ThreadPoolEpisodicSubjectiveScheduler``)、passive_recall retrieval
service の 3 箇所に届くことを固定する (U9a の
``test_world_runtime_error_driven_reinterpretation.py`` と同粒度)。

LLM は呼ばない (stub client)。flag は default OFF (共通規約 §0) なので
各テストで明示的に ON にする。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _enable_common_memory_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """想起の信用割り当てが実際に流れるための前提 flag 一式を ON にする。

    - LLM_EPISODIC_ENABLED: episodic stack (chunk_coordinator) を組む前提
    - PREDICTION_CONTEXT_ID_ENABLED: U1 (recall と prediction を紐付ける土台)
    - LLM_EPISODIC_REINTERPRETATION_ENABLED: 段1 (recall_buffer を組む前提。
      completion 未設定でも build_episodic_stack 自体は recall_buffer を
      作る。prompt が実際に覗くかは completion 有無に依る)
    """
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("PREDICTION_CONTEXT_ID_ENABLED", "1")
    monkeypatch.setenv("LLM_EPISODIC_REINTERPRETATION_ENABLED", "1")


class TestWorldRuntimeRecallHitBoostWiring:
    def test_flag_ON_で_chunk_coordinator_と_passive_recall_に届く(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_common_memory_flags(monkeypatch)
        monkeypatch.setenv("RECALL_HIT_BOOST_ENABLED", "1")

        runtime = create_world_runtime(_SCENARIO_PATH)
        stack = runtime._episodic_stack
        assert stack is not None

        # 的中側 sidecar が構築されている。
        assert stack.recall_success_store is not None

        # 同期経路 (chunk_coordinator) に store + flag が届いている。
        assert stack.chunk_coordinator._recall_success_store is stack.recall_success_store
        assert stack.chunk_coordinator._recall_hit_boost_enabled is True

        # passive_recall retrieval にも同一 store + strength が届いている。
        assert (
            stack.passive_recall._recall_success_store is stack.recall_success_store
        )
        assert stack.passive_recall._hit_boost_strength > 0

    def test_flag_OFF_既定なら不活性で_recall_success_store_はNone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_common_memory_flags(monkeypatch)
        monkeypatch.delenv("RECALL_HIT_BOOST_ENABLED", raising=False)

        runtime = create_world_runtime(_SCENARIO_PATH)
        stack = runtime._episodic_stack
        assert stack is not None

        assert stack.recall_success_store is None
        assert stack.chunk_coordinator._recall_success_store is None
        assert stack.chunk_coordinator._recall_hit_boost_enabled is False
        assert stack.passive_recall._recall_success_store is None

    def test_recall_hit_boost_ON_でも_reinterpretation_無効なら_recall_success_storeは作られるが対象が無い(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM_EPISODIC_REINTERPRETATION_ENABLED が無いと recall_buffer 自体が
        組まれないため、的中側 store は構築されても record_hit 対象の
        recall observation が無く安全に縮退する (本 flag 単独では実害無し)。
        """
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("PREDICTION_CONTEXT_ID_ENABLED", "1")
        monkeypatch.delenv("LLM_EPISODIC_REINTERPRETATION_ENABLED", raising=False)
        monkeypatch.setenv("RECALL_HIT_BOOST_ENABLED", "1")

        runtime = create_world_runtime(_SCENARIO_PATH)
        stack = runtime._episodic_stack
        assert stack is not None
        assert stack.reinterpretation_coordinator is None
        # recall_buffer 自体が組まれないため chunk_coordinator の
        # recall_buffer_store は None (U9a と同じ縮退)。
        assert stack.chunk_coordinator._recall_buffer_store is None

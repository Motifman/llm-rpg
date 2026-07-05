"""U4 (予測誤差統一設計 部品3): world_runtime を通した attribution + CONFIRMATION
配線を end-to-end で確認する。

``BELIEF_ATTRIBUTION_ENABLED`` フラグが ``create_world_runtime`` を通して
同期経路 (``EpisodicChunkCoordinator``) と固着 coordinator
(``BeliefConsolidationCoordinator``) の両方に届くことを固定する。
``ThreadPoolEpisodicSubjectiveScheduler`` などへの配線がキーワード文字列
一致依存なので、将来リファクタで配線が取りこぼされたときに構造的に検出
できる安全網 (U1 の ``test_world_runtime_prediction_context_id.py`` と同粒度)。

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
    """attribution が実際に流れるための前提 flag 一式を ON にする。

    - LLM_EPISODIC_ENABLED: episodic stack (chunk_coordinator) を組む前提
    - PREDICTION_CONTEXT_ID_ENABLED: U1 (belief_ids を流す土台)
    - BELIEF_EVIDENCE_ENABLED / BELIEF_CONSOLIDATION_ENABLED: evidence buffer
      + 固着 coordinator を組む前提
    """
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("PREDICTION_CONTEXT_ID_ENABLED", "1")
    monkeypatch.setenv("BELIEF_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("BELIEF_CONSOLIDATION_ENABLED", "1")


class TestWorldRuntimeBeliefAttributionWiring:
    def test_flag_ON_で_chunk_coordinator_と_固着coordinator_に_attribution_が届く(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_common_memory_flags(monkeypatch)
        monkeypatch.setenv("BELIEF_ATTRIBUTION_ENABLED", "1")

        runtime = create_world_runtime(_SCENARIO_PATH)
        stack = runtime._episodic_stack
        assert stack is not None

        # 同期経路 (chunk_coordinator) に flag が届いている。
        assert stack.chunk_coordinator._belief_attribution_enabled is True

        # 固着 coordinator が構築され、CONFIRMATION 節が system prompt に載る
        # (= attribution flag が coordinator まで届いた証拠)。
        coordinator = stack.belief_consolidation_coordinator
        assert coordinator is not None
        assert "confirmation" in coordinator._system_prompt

    def test_flag_OFF_なら_attribution_は_不活性で_confirmation節も出ない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_common_memory_flags(monkeypatch)
        monkeypatch.delenv("BELIEF_ATTRIBUTION_ENABLED", raising=False)

        runtime = create_world_runtime(_SCENARIO_PATH)
        stack = runtime._episodic_stack
        assert stack is not None

        assert stack.chunk_coordinator._belief_attribution_enabled is False

        coordinator = stack.belief_consolidation_coordinator
        assert coordinator is not None
        # OFF なら固着 prompt は pre-U4 と byte 一致 (CONFIRMATION 節なし)。
        assert "confirmation" not in coordinator._system_prompt

    def test_attribution_ON_でも_episodic_無効なら_stack_は_None(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM_EPISODIC_ENABLED が無ければそもそも stack を組まない
        (attribution flag 単独では副作用を持たないことの確認)。"""
        monkeypatch.delenv("LLM_EPISODIC_ENABLED", raising=False)
        monkeypatch.setenv("BELIEF_ATTRIBUTION_ENABLED", "1")

        runtime = create_world_runtime(_SCENARIO_PATH)
        assert runtime._episodic_stack is None

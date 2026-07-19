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
from tests.runtime_config_helpers import belief_consolidation_config, runtime_config

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _common_memory_config(**overrides):
    """attribution が実際に流れるための前提設定一式を作る。"""
    return belief_consolidation_config(
        prediction_context_id_enabled=True,
        **overrides,
    )


class TestWorldRuntimeBeliefAttributionWiring:
    def test_flag_chunk_coordinator_attribution(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """flagON で chunkcoordinator と固着 coordinator に attribution が届く。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=_common_memory_config(belief_attribution_enabled=True),
        )
        stack = runtime._episodic_stack
        assert stack is not None

        # 同期経路 (chunk_coordinator) に flag が届いている。
        assert stack.chunk_coordinator._belief_attribution_enabled is True

        # 固着 coordinator が構築され、CONFIRMATION 節が system prompt に載る
        # (= attribution flag が coordinator まで届いた証拠)。
        coordinator = stack.belief_consolidation_coordinator
        assert coordinator is not None
        assert "confirmation" in coordinator._system_prompt

    def test_flag_off_attribution_confirmation_not_rendered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """flagOFF なら attribution は不活性で confirmation 節も出ない。"""
        runtime = create_world_runtime(_SCENARIO_PATH, config=_common_memory_config())
        stack = runtime._episodic_stack
        assert stack is not None

        assert stack.chunk_coordinator._belief_attribution_enabled is False

        coordinator = stack.belief_consolidation_coordinator
        assert coordinator is not None
        # OFF なら固着 prompt は pre-U4 と byte 一致 (CONFIRMATION 節なし)。
        assert "confirmation" not in coordinator._system_prompt

    def test_attribution_episodic_stack_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM_EPISODIC_ENABLED が無ければそもそも stack を組まない
        (attribution flag 単独では副作用を持たないことの確認)。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=runtime_config(belief_attribution_enabled=True),
        )
        assert runtime._episodic_stack is None

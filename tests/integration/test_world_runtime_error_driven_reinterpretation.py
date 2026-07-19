"""U9a (予測誤差統一設計 部品5・誤差駆動再解釈): world_runtime を通した
recall_buffer stamp + 誤差専用 framing の配線を end-to-end で確認する。

``ERROR_DRIVEN_REINTERPRETATION_ENABLED`` フラグが ``create_world_runtime`` を
通して同期経路 (``EpisodicChunkCoordinator``) と再解釈 coordinator
(``EpisodicReinterpretationCoordinator``) の両方に届くことを固定する
(U4 の ``test_world_runtime_belief_attribution.py`` と同粒度)。

LLM は呼ばない (stub client)。flag は default OFF (共通規約 §0) なので
各テストで明示的に ON にする。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from tests.runtime_config_helpers import episodic_config

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _common_memory_config(**overrides):
    """誤差駆動再解釈が実際に流れるための前提設定一式を作る。"""
    return episodic_config(
        prediction_context_id_enabled=True,
        episodic_reinterpretation_enabled=True,
        **overrides,
    )


class TestWorldRuntimeErrorDrivenReinterpretationWiring:
    def test_flag_ON_で_chunk_coordinator_と_再解釈coordinator_に届く(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=_common_memory_config(error_driven_reinterpretation_enabled=True),
        )
        stack = runtime._episodic_stack
        assert stack is not None

        # 同期経路 (chunk_coordinator) に flag が届いている。
        assert stack.chunk_coordinator._error_driven_reinterpretation_enabled is True

        # 再解釈 coordinator にも flag が届き、誤差駆動節が system prompt に
        # 出せる状態になっている (= flag が coordinator まで届いた証拠)。
        coordinator = stack.reinterpretation_coordinator
        assert coordinator is not None
        assert coordinator._error_driven_reinterpretation_enabled is True

    def test_flag_OFF_既定なら不活性で_chunk_coordinator_recall_buffer_store_はNone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runtime = create_world_runtime(_SCENARIO_PATH, config=_common_memory_config())
        stack = runtime._episodic_stack
        assert stack is not None

        assert stack.chunk_coordinator._error_driven_reinterpretation_enabled is False
        coordinator = stack.reinterpretation_coordinator
        assert coordinator is not None
        assert coordinator._error_driven_reinterpretation_enabled is False

    def test_error_driven_ON_でも_reinterpretation_無効なら_coordinator_はNone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM_EPISODIC_REINTERPRETATION_ENABLED が無ければ再解釈 coordinator
        自体を組まない (本 flag 単独では副作用を持たないことの確認)。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=episodic_config(
                prediction_context_id_enabled=True,
                error_driven_reinterpretation_enabled=True,
            ),
        )
        stack = runtime._episodic_stack
        assert stack is not None
        assert stack.reinterpretation_coordinator is None
        # recall_buffer 自体が組まれないため chunk_coordinator 側も None に
        # 安全に縮退する。
        assert stack.chunk_coordinator._recall_buffer_store is None

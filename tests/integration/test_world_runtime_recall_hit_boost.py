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
from tests.runtime_config_helpers import episodic_config

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _common_memory_config(**overrides):
    """想起の信用割り当てが実際に流れるための前提設定一式を作る。"""
    return episodic_config(
        prediction_context_id_enabled=True,
        episodic_reinterpretation_enabled=True,
        **overrides,
    )


class TestWorldRuntimeRecallHitBoostWiring:
    def test_flag_chunk_coordinator_passive_recall(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """flag ON で chunk coordinator と passive recall に届く。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=_common_memory_config(recall_hit_boost_enabled=True),
        )
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

    def test_flag_off_default_recall_success_store_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """flag OFF 既定なら不活性で recall success store はNone。"""
        runtime = create_world_runtime(_SCENARIO_PATH, config=_common_memory_config())
        stack = runtime._episodic_stack
        assert stack is not None

        assert stack.recall_success_store is None
        assert stack.chunk_coordinator._recall_success_store is None
        assert stack.chunk_coordinator._recall_hit_boost_enabled is False
        assert stack.passive_recall._recall_success_store is None

    def test_recall_success_store_exists_without_targets_when_reinterpretation_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM_EPISODIC_REINTERPRETATION_ENABLED が無いと recall_buffer 自体が
        組まれないため、的中側 store は構築されても record_hit 対象の
        recall observation が無く安全に縮退する (本 flag 単独では実害無し)。
        """
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=episodic_config(
                prediction_context_id_enabled=True,
                recall_hit_boost_enabled=True,
            ),
        )
        stack = runtime._episodic_stack
        assert stack is not None
        assert stack.reinterpretation_coordinator is None
        # recall_buffer 自体が組まれないため chunk_coordinator の
        # recall_buffer_store は None (U9a と同じ縮退)。
        assert stack.chunk_coordinator._recall_buffer_store is None

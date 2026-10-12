"""U9a (予測誤差統一設計 部品5・誤差駆動再解釈): world_runtime を通した
recall_buffer stamp + 誤差専用 framing の配線を end-to-end で確認する。

``ERROR_DRIVEN_REINTERPRETATION_ENABLED`` フラグが ``create_world_runtime`` を
通して、再解釈 coordinator (``EpisodicReinterpretationCoordinator``) に届く
ことを固定する。確定した予期を想起へ返す受け取る側 (#1443) は #1631 で消した。外れを想起に
書き添える書き手はもう無いので、このフラグを有効にしても書き添えは起きない。再解釈を消す段で、
フラグと一緒に消す。

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
    def test_flag_chunk_coordinator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """flag ON で再解釈 coordinator に届く。stub client では想起の記録が prompt に
        組まれないので、recall_buffer は組まれない。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=_common_memory_config(error_driven_reinterpretation_enabled=True),
        )
        stack = runtime._episodic_stack
        assert stack is not None

        assert stack.recall_buffer_store is None

        # 再解釈 coordinator にも flag が届き、誤差駆動節が system prompt に
        # 出せる状態になっている (= flag が coordinator まで届いた証拠)。
        coordinator = stack.reinterpretation_coordinator
        assert coordinator is not None
        assert coordinator._error_driven_reinterpretation_enabled is True

    def test_flag_off_default_chunk_coordinator_recall_buffer_store_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """flag OFF 既定なら、再解釈 coordinator に誤差駆動の flag は届かない。"""
        runtime = create_world_runtime(_SCENARIO_PATH, config=_common_memory_config())
        stack = runtime._episodic_stack
        assert stack is not None

        coordinator = stack.reinterpretation_coordinator
        assert coordinator is not None
        assert coordinator._error_driven_reinterpretation_enabled is False

    def test_error_driven_reinterpretation_coordinator_none(
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

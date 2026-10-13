"""U9b (予測誤差統一設計 部品5・想起の信用割り当て): world_runtime を通した

的中側 sidecar (recall_success_store) の配線を end-to-end で確認する。

``RECALL_HIT_BOOST_ENABLED`` フラグが ``create_world_runtime`` を通して、
passive_recall retrieval service に届くことを固定する。確定した予期を想起へ
返す受け取る側 (#1443) は #1631 で消した。的中の回数を足す書き手はもう無いので、このフラグを
有効にしても回数は増えない。想起の部品を消す段で、フラグと一緒に消す。

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
        episodic_reinterpretation_enabled=True,
        **overrides,
    )


class TestWorldRuntimeRecallHitBoostWiring:
    def test_flag_chunk_coordinator_passive_recall(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """flag ON で、的中側 sidecar が組まれ、passive recall に届く。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=_common_memory_config(recall_hit_boost_enabled=True),
        )
        stack = runtime._episodic_stack
        assert stack is not None

        # 的中側 sidecar が構築されている。
        assert stack.recall_success_store is not None


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
        assert stack.passive_recall._recall_success_store is None

    def test_recall_success_store_exists_without_targets_when_reinterpretation_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM_EPISODIC_REINTERPRETATION_ENABLED が無いと、再解釈 coordinator は
        組まれないが、的中側 sidecar は組まれる。
        """
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=episodic_config(
                recall_hit_boost_enabled=True,
            ),
        )
        stack = runtime._episodic_stack
        assert stack is not None
        assert stack.reinterpretation_coordinator is None

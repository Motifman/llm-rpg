"""LLM 配線は、LLM の呼び出し口を明示して渡さないと組めない。

既定でスタブを入れていたので、本番の配線で渡し忘れても、エージェントが黙って
スタブで動いた。渡し忘れは組み立ての時点で止める。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_DRILL = Path(__file__).resolve().parents[5] / "data" / "scenarios" / "station_drill.json"


def test_wiring_without_llm_client_cannot_be_built() -> None:
    """llm_client を渡さずに配線を組むと TypeError で止まり、スタブで動き出さない。"""
    runtime = create_world_runtime(_DRILL)

    with pytest.raises(TypeError, match="llm_client"):
        _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
        )

"""``wait`` の結果文を、エージェントが世界の中で読める言葉だけで書く (#1562)。"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)


def _build_executor(*, runtime) -> SpotGraphToolExecutor:
    services = SpotGraphWorldServices(
        interaction=MagicMock(),
        exploration=MagicMock(),
        world_flags=MagicMock(as_frozen_set=MagicMock(return_value=frozenset())),
        game_end_evaluator=MagicMock(),
        exploration_progress=MagicMock(),
        movement=MagicMock(),
        simulation=None,
    )
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
        speech_service=None,
        runtime=runtime,
    )


class TestWaitResultMessage:
    """``SpotGraphToolExecutor._wait`` の結果文に、世界の tick の番号が出ないことを保証する。"""

    def test_wait_result_does_not_mention_world_tick(self) -> None:
        """世界の tick が 20 のときに待っても、結果文に ``tick`` の語も番号 20 も出ない。"""
        runtime = MagicMock()
        runtime.do_wait.return_value = 20
        executor = _build_executor(runtime=runtime)

        result = executor._wait(1, {"inner_thought": "様子を見る"})

        assert result.success
        assert "tick" not in result.message
        assert "20" not in result.message

    def test_wait_result_keeps_the_reason(self) -> None:
        """理由を添えて待ったら、結果文にその理由が残る。"""
        runtime = MagicMock()
        runtime.do_wait.return_value = 20
        executor = _build_executor(runtime=runtime)

        result = executor._wait(1, {"reason": "足音が遠ざかるのを待つ", "inner_thought": "静かに"})

        assert "足音が遠ざかるのを待つ" in result.message

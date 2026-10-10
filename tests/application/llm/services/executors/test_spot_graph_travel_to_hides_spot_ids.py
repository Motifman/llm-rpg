"""travel_to の結果の文に、内部のスポット番号が出ないことを保証する。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_TRAVEL_TO
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SpotTravelUnreachableException,
)


def _build_executor(*, runtime, spot_graph_repository=None) -> SpotGraphToolExecutor:
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
        runtime=runtime,
        spot_graph_repository=spot_graph_repository,
    )


def _runtime(*, do_move) -> SimpleNamespace:
    return SimpleNamespace(
        id_mapper=SimpleNamespace(get_str=lambda kind, value: f"spot_{value}"),
        do_move=do_move,
    )


def _run_travel_to(executor: SpotGraphToolExecutor, destination: int):
    handler = executor.get_handlers()[TOOL_NAME_SPOT_GRAPH_TRAVEL_TO]
    return handler(1, {"destination_spot_id": destination, "inner_thought": "行く"})


class TestTravelToMessageHidesSpotIds:
    """travel_to が成功しても失敗しても、エージェントに返る文にスポット番号を含めない。"""

    def test_unreachable_exception_message_reaches_agent_unchanged_with_error_code(self) -> None:
        """移動サービスの到達不能の例外は、文を変えずに失敗の結果へ写り、error_code が付く。"""
        def _raise_unreachable(*args, **kwargs):
            raise SpotTravelUnreachableException("その先へは行けない。")

        executor = _build_executor(runtime=_runtime(do_move=_raise_unreachable))

        result = _run_travel_to(executor, 19)

        assert result.success is False
        assert result.message == "その先へは行けない。"
        assert result.error_code == "WORLD_GRAPH.SPOT_TRAVEL_UNREACHABLE"

    def test_destination_name_lookup_failure_does_not_fall_back_to_spot_id(self) -> None:
        """移動を始めたあと行き先の名前が引けなくても、成功の文に番号を出さない。"""
        broken_repository = MagicMock()
        broken_repository.find_graph.side_effect = RuntimeError("graph unavailable")
        executor = _build_executor(
            runtime=_runtime(do_move=lambda *args, **kwargs: None),
            spot_graph_repository=broken_repository,
        )

        result = _run_travel_to(executor, 19)

        assert result.success is True
        assert result.message == "目的地へ移動しました。"

    def test_without_spot_graph_repository_success_message_does_not_use_spot_id(self) -> None:
        """行き先の名前を引く手段が無い構成でも、成功の文に番号を出さず「目的地」と書く。"""
        executor = _build_executor(runtime=_runtime(do_move=lambda *args, **kwargs: None))

        result = _run_travel_to(executor, 19)

        assert result.success is True
        assert result.message == "目的地へ移動しました。"

"""LLM 実行方式に関わらず、自分の 1 wave を短期記憶の 1 ターンにする。"""

from types import SimpleNamespace

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.player.services.player_life_query import (
    PlayerLifeQuery,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
    _WorldLlmTurnTrigger,
)


class _RuntimeStub:
    """実行方式の設定だけを持つ runtime 代役。"""

    _episodic_stack = None

    def __init__(self, workers: int) -> None:
        self._runtime_config = SimpleNamespace(llm_turn_parallel_workers=workers)
        self._player_life_query = PlayerLifeQuery(
            player_status_repository=None,
            player_outcome_registry=None,
        )


class _WiringStub:
    """serial / parallel の両入口を成功させ、共有 memory を公開する。"""

    def __init__(self, workers: int) -> None:
        self.runtime = _RuntimeStub(workers)
        self.short_term_memory = DefaultSlidingWindowMemory(
            turn_cap=10,
            compact_turn_count=5,
        )

    def run_turn(self, player_id: PlayerId) -> LlmCommandResultDto:
        return LlmCommandResultDto(success=True, message="完了した。")

    def run_phase_a(self, player_id: PlayerId) -> PlayerId:
        return player_id

    def run_phase_b(self, phase_a: PlayerId) -> LlmCommandResultDto:
        return LlmCommandResultDto(success=True, message="完了した。")


def _run_two_players(*, workers: int) -> _WiringStub:
    wiring = _WiringStub(workers)
    trigger = _WorldLlmTurnTrigger(wiring=wiring)
    trigger.schedule_turn(PlayerId(1))
    trigger.schedule_turn(PlayerId(2))

    trigger.run_scheduled_turns()

    return wiring


def test_serial_execution_closes_one_turn_per_player() -> None:
    """直列経路は実行した各 player のターンを 1 回ずつ閉じる。"""
    wiring = _run_two_players(workers=0)

    store = wiring.short_term_memory._event_store
    assert store.completed_turn_count(PlayerId(1)) == 1
    assert store.completed_turn_count(PlayerId(2)) == 1


def test_parallel_execution_closes_one_turn_per_player() -> None:
    """並列 Phase A / 直列 Phase B 経路も各 player のターンを 1 回ずつ閉じる。"""
    wiring = _run_two_players(workers=2)

    store = wiring.short_term_memory._event_store
    assert store.completed_turn_count(PlayerId(1)) == 1
    assert store.completed_turn_count(PlayerId(2)) == 1

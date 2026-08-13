"""LLM 実行方式に関わらず、自分の 1 wave を短期記憶の 1 ターンにする。"""

from hashlib import sha256
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


class _GamePhaseStoreStub:
    """会議中かどうかだけを返す軽量なフェーズ store。"""

    def __init__(self, meeting: bool) -> None:
        self._meeting = meeting

    def is_meeting(self) -> bool:
        return self._meeting


class _RuntimeStub:
    """実行方式の設定だけを持つ runtime 代役。"""

    _episodic_stack = None

    def __init__(self, workers: int, *, meeting: bool = False) -> None:
        self._runtime_config = SimpleNamespace(llm_turn_parallel_workers=workers)
        self._game_phase_store = _GamePhaseStoreStub(meeting)
        self._player_life_query = PlayerLifeQuery(
            player_status_repository=None,
            player_outcome_registry=None,
        )


class _WiringStub:
    """serial / parallel の両入口を成功させ、共有 memory を公開する。"""

    def __init__(self, workers: int, *, meeting: bool = False) -> None:
        self.runtime = _RuntimeStub(workers, meeting=meeting)
        self.short_term_memory = DefaultSlidingWindowMemory(
            turn_cap=10,
            compact_turn_count=5,
        )
        self.spoken: list[str] = []
        self.prompt_snapshots: dict[int, str] = {}
        self.system_hashes: dict[int, str] = {}
        self.toolset_hashes: dict[int, str] = {}

    def _build_prompt(self, player_id: PlayerId) -> str:
        system = "同じ不変の system prompt"
        toolset = '[{"name":"speak"}]'
        self.system_hashes[player_id.value] = sha256(system.encode()).hexdigest()
        self.toolset_hashes[player_id.value] = sha256(toolset.encode()).hexdigest()
        prompt = " / ".join(self.spoken)
        self.prompt_snapshots[player_id.value] = prompt
        return prompt

    def run_turn(self, player_id: PlayerId) -> LlmCommandResultDto:
        self._build_prompt(player_id)
        self.spoken.append(f"player-{player_id.value} の同 tick 発言")
        return LlmCommandResultDto(success=True, message="完了した。")

    def run_phase_a(self, player_id: PlayerId) -> tuple[PlayerId, str]:
        return player_id, self._build_prompt(player_id)

    def run_phase_b(
        self, phase_a: tuple[PlayerId, str]
    ) -> LlmCommandResultDto:
        player_id, _prompt = phase_a
        self.spoken.append(f"player-{player_id.value} の同 tick 発言")
        return LlmCommandResultDto(success=True, message="完了した。")


def _run_two_players(*, workers: int, meeting: bool = False) -> _WiringStub:
    wiring = _WiringStub(workers, meeting=meeting)
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


def test_meeting_runs_serially_so_later_prompt_contains_same_tick_speech() -> None:
    """会議では後に話す者が、同じ world tick の先行発言を読んでから話す。"""
    wiring = _run_two_players(workers=4, meeting=True)

    first, second = list(wiring.prompt_snapshots)
    assert f"player-{first} の同 tick 発言" in wiring.prompt_snapshots[second]


def test_free_roam_keeps_wave_parallel_prompts_isolated_within_the_tick() -> None:
    """自由時間は wave 並列を保ち、同 tick の他者行動を Phase A に混ぜない。"""
    wiring = _run_two_players(workers=4, meeting=False)

    assert all(prompt == "" for prompt in wiring.prompt_snapshots.values())


def test_meeting_serialization_does_not_change_system_or_toolset_prefixes() -> None:
    """逐次化は実行順だけを変え、system prompt と toolset の sha256 を変えない。"""
    free_roam = _run_two_players(workers=4, meeting=False)
    meeting = _run_two_players(workers=4, meeting=True)

    assert set(free_roam.system_hashes.values()) == set(
        meeting.system_hashes.values()
    )
    assert set(free_roam.toolset_hashes.values()) == set(
        meeting.toolset_hashes.values()
    )

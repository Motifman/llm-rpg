"""LLM の実行方式 (逐次・並列) と会議かどうかで、同じ tick の他者の行動がプロンプトに混ざらず、プレフィックスも変わらないことを保証する。"""

from hashlib import sha256
from types import SimpleNamespace

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
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

    def __init__(
        self,
        workers: int,
        *,
        meeting: bool = False,
    ) -> None:
        self._runtime_config = SimpleNamespace(
            llm_turn_parallel_workers=workers,
        )
        self._game_phase_store = _GamePhaseStoreStub(meeting)
        self._player_life_query = PlayerLifeQuery(
            player_status_repository=None,
            player_outcome_registry=None,
        )

    def current_tick(self) -> int:
        return 0


class _WiringStub:
    """serial / parallel の両入口を成功させ、共有 memory を公開する。"""

    def __init__(
        self,
        workers: int,
        *,
        meeting: bool = False,
    ) -> None:
        self.runtime = _RuntimeStub(
            workers,
            meeting=meeting,
        )
        self.spoken: list[str] = []
        self.finished_turns: list[int] = []
        self.prompt_snapshots: dict[int, str] = {}
        self.system_hashes: dict[int, str] = {}
        self.toolset_hashes: dict[int, str] = {}

    def _build_prompt(self, player_id: PlayerId) -> str:
        system = "同じ不変の system prompt"
        # 実 runtime と同じく toolset はフェーズで変わるが、worker 数では
        # 変わらない。会議と自由時間を同一視する空振り試験を避ける。
        toolset = (
            '[{"name":"speak"},{"name":"vote"}]'
            if self.runtime._game_phase_store.is_meeting()
            else '[{"name":"speak"},{"name":"travel_to"}]'
        )
        self.system_hashes[player_id.value] = sha256(system.encode()).hexdigest()
        self.toolset_hashes[player_id.value] = sha256(toolset.encode()).hexdigest()
        prompt = " / ".join(self.spoken)
        self.prompt_snapshots[player_id.value] = prompt
        return prompt

    def run_turn(self, player_id: PlayerId) -> LlmCommandResultDto:
        self._build_prompt(player_id)
        self.spoken.append(f"player-{player_id.value} の同 tick 発言")
        self.finished_turns.append(player_id.value)
        return LlmCommandResultDto(success=True, message="完了した。")

    def run_phase_a(self, player_id: PlayerId) -> tuple[PlayerId, str]:
        return player_id, self._build_prompt(player_id)

    def run_phase_b(self, phase_a: tuple[PlayerId, str]) -> LlmCommandResultDto:
        player_id, _prompt = phase_a
        self.spoken.append(f"player-{player_id.value} の同 tick 発言")
        self.finished_turns.append(player_id.value)
        return LlmCommandResultDto(success=True, message="完了した。")


def _run_two_players(
    *,
    workers: int,
    meeting: bool = False,
) -> _WiringStub:
    wiring = _WiringStub(
        workers,
        meeting=meeting,
    )
    trigger = _WorldLlmTurnTrigger(wiring=wiring)
    trigger.schedule_turn(PlayerId(1))
    trigger.schedule_turn(PlayerId(2))

    trigger.run_scheduled_turns()

    return wiring


@pytest.mark.parametrize("workers", [0, 2])
def test_each_scheduled_player_finishes_exactly_one_turn(workers: int) -> None:
    """直列でも並列でも、予定した各 player の 1 手を 1 回だけ最後まで処理する。Being の短期記憶のターンは、その 1 手の処理 (run_phase_b) の終わりで閉じる (design_decisions D1824-21)。"""
    wiring = _run_two_players(workers=workers)

    assert sorted(wiring.finished_turns) == [1, 2]


def test_meeting_keeps_wave_parallel() -> None:
    """会議でも wave 並列を保ち、同 tick 発言を互いに見せない。"""
    wiring = _run_two_players(
        workers=4,
        meeting=True,
    )

    assert all(prompt == "" for prompt in wiring.prompt_snapshots.values())


def test_free_roam_keeps_wave_parallel_prompts_isolated_within_the_tick() -> None:
    """自由時間は並列を保ち、同 tick の他者行動を混ぜない。"""
    wiring = _run_two_players(
        workers=4,
        meeting=False,
    )

    assert all(prompt == "" for prompt in wiring.prompt_snapshots.values())


def test_worker_count_does_not_change_prefixes_within_the_same_phase() -> None:
    """同じフェーズなら逐次・並列を変えても system と toolset の sha256 は同じ。"""
    serial_meeting = _run_two_players(workers=1, meeting=True)
    configured_parallel_meeting = _run_two_players(workers=4, meeting=True)
    serial_free_roam = _run_two_players(workers=1, meeting=False)
    parallel_free_roam = _run_two_players(workers=4, meeting=False)

    assert set(serial_meeting.system_hashes.values()) == set(configured_parallel_meeting.system_hashes.values())
    assert set(serial_meeting.toolset_hashes.values()) == set(configured_parallel_meeting.toolset_hashes.values())
    assert set(serial_free_roam.system_hashes.values()) == set(parallel_free_roam.system_hashes.values())
    assert set(serial_free_roam.toolset_hashes.values()) == set(parallel_free_roam.toolset_hashes.values())
    # フェーズ境界では実物どおり toolset が変わる。この変更は #8 の
    # worker 切替とは別で、キャッシュ不変を主張しない。
    assert set(serial_meeting.toolset_hashes.values()) != set(serial_free_roam.toolset_hashes.values())

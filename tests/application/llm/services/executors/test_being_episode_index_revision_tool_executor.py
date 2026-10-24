from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.application.being.acting_being import ActingBeing
from ai_rpg_world.application.llm.services.executors.being_episode_index_revision_tool_executor import (
    BeingEpisodeIndexRevisionToolExecutor,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_EPISODE_REVISE_INDEX
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.memory_turn_clock import (
    MemoryTurnReader,
)
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import (
    InMemoryEpisodeRepository,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeConflictException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

ADA = BeingId("being_ada")
ACTING = ActingBeing(player_id=PlayerId(1), being_id=ADA)


class _Turn(MemoryTurnReader):
    def __init__(self, turn: int) -> None:
        self.turn = turn

    def current_turn(self, being_id: BeingId) -> int:
        return self.turn


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        self.events: list[tuple[str, int | None, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any):  # type: ignore[override]
        self.events.append((kind, player_id, payload))
        return super().record(kind, tick=tick, player_id=player_id, **payload)


def _episode() -> Episode:
    return Episode.write(
        being_id=ADA,
        episode_id="00000100-0000-4000-8000-000000000000",
        environment_name="島",
        written_turn=1,
        index=EpisodeIndex(summary="金庫の番号を探した", recall_when="金庫の話が出たとき"),
        body="棚の紙に 4 桁が書いてあった。",
    )


def _unchanged(stored: Episode | None, episode: Episode) -> bool:
    return stored is not None and (stored.index, stored.index_history) == (episode.index, episode.index_history)


class _RefusingRepository(InMemoryEpisodeRepository):
    def save(self, episode: Episode) -> None:
        raise EpisodeConflictException("refused")


def _executor(turn: int = 5, repository: InMemoryEpisodeRepository | None = None):
    repository = repository or InMemoryEpisodeRepository()
    episode = _episode()
    repository.add(episode)
    recorder = _Recorder()
    executor = BeingEpisodeIndexRevisionToolExecutor(
        repository=repository,
        turn_reader=_Turn(turn),
        trace_recorder_provider=lambda: recorder,
        current_tick_provider=lambda: 7,
    )
    return executor, repository, recorder, episode


def _run(executor: BeingEpisodeIndexRevisionToolExecutor, arguments: dict[str, Any]):
    return executor.get_handlers()[TOOL_NAME_EPISODE_REVISE_INDEX](ACTING, arguments)


def _traces(recorder: _Recorder) -> list[dict[str, Any]]:
    return [p for k, _, p in recorder.events if k == TraceEventKind.EPISODE_INDEX_REVISION]


class TestRevisingTheIndex:
    """目次を直すツールが、呼び名の目次を新しい 2 つの文に替え、前の目次を履歴に残すことを保証する。"""

    def test_replaces_the_index_and_keeps_the_previous_one_with_the_turn(self) -> None:
        """呼び名と新しい目次を渡すと目次が替わり、前の目次が直したターンと一緒に履歴に入り、本文は変わらない。"""
        executor, repository, _, episode = _executor(turn=6)

        result = _run(executor, {"handle": episode.handle, "about": "金庫を開けた", "recall_when": "鍵の掛かった箱を見たとき"})

        assert result.success is True
        stored = repository.find_by_handle(ADA, episode.handle)
        assert stored is not None
        assert stored.index == EpisodeIndex(summary="金庫を開けた", recall_when="鍵の掛かった箱を見たとき")
        assert [(r.previous, r.revised_turn) for r in stored.index_history] == [(episode.index, 6)]
        assert stored.body == episode.body

    def test_the_result_shows_the_new_line(self) -> None:
        """結果の文に、直したあとの目次の一行を返す。"""
        executor, _, _, episode = _executor()

        result = _run(executor, {"handle": episode.handle, "about": "金庫を開けた", "recall_when": "箱を見たとき"})

        assert result.message == f"[{episode.handle}] の目次を直した: 金庫を開けた — 思い出すとき: 箱を見たとき"

    def test_too_long_text_is_cut_to_the_limit_and_traced(self) -> None:
        """40 字を超えた文は 40 字に切り詰めて保存し、切り詰める前の長さを trace に残す。"""
        executor, repository, recorder, episode = _executor()

        _run(executor, {"handle": episode.handle, "about": "あ" * 45, "recall_when": "箱を見たとき"})

        stored = repository.find_by_handle(ADA, episode.handle)
        assert stored is not None and stored.index.summary == "あ" * 40
        [payload] = _traces(recorder)
        assert payload["truncated"] == {"about": 45}

    def test_unknown_handle_changes_nothing(self) -> None:
        """知らない呼び名を渡すと、どの記録も変えず、その記憶は無いと返す。"""
        executor, repository, recorder, episode = _executor()

        result = _run(executor, {"handle": "ep_ffffff", "about": "金庫を開けた", "recall_when": "箱を見たとき"})

        assert result.success is False
        assert "ep_ffffff" in result.message
        assert _unchanged(repository.find_by_handle(ADA, episode.handle), episode)
        assert [(p["outcome"], p["reject_reason"]) for p in _traces(recorder)] == [("rejected", "unknown_handle")]

    @pytest.mark.parametrize(
        "arguments",
        [
            pytest.param({"about": "金庫を開けた", "recall_when": "箱を見たとき"}, id="no_handle"),
            pytest.param({"handle": "  ", "about": "金庫を開けた", "recall_when": "箱を見たとき"}, id="blank_handle"),
            pytest.param({"handle": "ep_000001", "recall_when": "箱を見たとき"}, id="no_about"),
            pytest.param({"handle": "ep_000001", "about": "金庫を開けた", "recall_when": "  "}, id="blank_recall_when"),
            pytest.param({"handle": "ep_000001", "about": 3, "recall_when": "箱を見たとき"}, id="not_a_string"),
        ],
    )
    def test_malformed_arguments_are_rejected(self, arguments: dict[str, Any]) -> None:
        """呼び名・どんな記憶か・どんな時に思い出すかのどれかが空や文字列でなければ、何も変えずに INVALID_ARGUMENT を返す。"""
        executor, repository, recorder, episode = _executor()

        result = _run(executor, arguments)

        assert (result.success, result.error_code) == (False, "INVALID_ARGUMENT")
        assert _unchanged(repository.find_by_handle(ADA, episode.handle), episode)
        assert [(p["outcome"], p["reject_reason"]) for p in _traces(recorder)] == [("rejected", "malformed")]

    def test_a_refused_save_is_reported_as_a_failure(self) -> None:
        """保存がドメインの決まりで断られたら、手番を止めずに INVALID_STATE を返し、失敗の型を trace に残す。"""
        executor, _, recorder, episode = _executor(repository=_RefusingRepository())

        result = _run(executor, {"handle": episode.handle, "about": "金庫を開けた", "recall_when": "箱を見たとき"})

        assert (result.success, result.error_code) == (False, "INVALID_STATE")
        [payload] = _traces(recorder)
        assert (payload["outcome"], payload["error_type"]) == ("failed", "EpisodeConflictException")


class TestRevisionTrace:
    """目次を直すたびに、前と後の目次が trace に 1 件残ることを保証する。"""

    def test_records_before_and_after(self) -> None:
        """直すと、呼び名・ターン数・前の目次・後の目次・切り詰めの有無を残す。"""
        executor, _, recorder, episode = _executor(turn=4)

        _run(executor, {"handle": episode.handle, "about": "金庫を開けた", "recall_when": "箱を見たとき"})

        [payload] = _traces(recorder)
        assert payload == {
            "being_id": ADA.value,
            "outcome": "revised",
            "handle": episode.handle,
            "turn": 4,
            "before": {"about": "金庫の番号を探した", "recall_when": "金庫の話が出たとき"},
            "after": {"about": "金庫を開けた", "recall_when": "箱を見たとき"},
            "truncated": {},
        }

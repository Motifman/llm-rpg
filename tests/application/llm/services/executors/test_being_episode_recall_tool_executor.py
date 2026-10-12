from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.application.being.acting_being import ActingBeing
from ai_rpg_world.application.llm.services.executors.being_episode_recall_tool_executor import (
    UNKNOWN_EPISODE_TEXT,
    BeingEpisodeRecallToolExecutor,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_EPISODE_RECALL
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.memory_turn_clock import (
    MemoryTurnReader,
)
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import (
    InMemoryEpisodeRepository,
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


def _episode(number: int, *, summary: str = "金庫の番号を探した", body: str = "棚の紙に 4 桁が書いてあった。") -> Episode:
    return Episode.write(
        episode_id=f"{number:06x}00-0000-4000-8000-000000000000",
        environment_name="島",
        written_turn=1,
        index=EpisodeIndex(summary=summary, recall_when="金庫の話が出たとき"),
        body=body,
    )


def _executor(*episodes: Episode, turn: int = 5, max_handles: int = 3):
    repository = InMemoryEpisodeRepository()
    for episode in episodes:
        repository.add(ADA, episode)
    recorder = _Recorder()
    executor = BeingEpisodeRecallToolExecutor(
        repository=repository,
        turn_reader=_Turn(turn),
        max_handles=max_handles,
        trace_recorder_provider=lambda: recorder,
        current_tick_provider=lambda: 7,
    )
    return executor, repository, recorder


def _run(executor: BeingEpisodeRecallToolExecutor, arguments: dict[str, Any]):
    return executor.get_handlers()[TOOL_NAME_EPISODE_RECALL](ACTING, arguments)


def _recall_traces(recorder: _Recorder) -> list[dict[str, Any]]:
    return [p for k, _, p in recorder.events if k == TraceEventKind.EPISODE_RECALL]


class TestRecallingEpisodes:
    """呼び出しのツールが、呼び名ごとに本文を返し、知らない呼び名だけを「思い出せない」にすることを保証する。"""

    def test_returns_each_body_under_its_handle_and_summary(self) -> None:
        """呼び名を 2 件渡すと、渡した順に、呼び名とどんな記憶かの下にそれぞれの本文を返す。"""
        first = _episode(1, summary="金庫の番号を探した", body="棚の紙に 4 桁が書いてあった。")
        second = _episode(2, summary="浜で火を起こした", body="流木が湿っていて苦労した。")
        executor, _, _ = _executor(first, second)

        result = _run(executor, {"handles": [second.handle, first.handle]})

        assert result.success is True
        assert result.message == (
            f"[{second.handle}] 浜で火を起こした\n  流木が湿っていて苦労した。\n"
            f"[{first.handle}] 金庫の番号を探した\n  棚の紙に 4 桁が書いてあった。"
        )

    def test_recalling_counts_up_and_records_the_turn(self) -> None:
        """呼び出したエピソードは、呼び出した回数が 1 増え、最後に呼び出した時がいまの Being のターン数になる。"""
        episode = _episode(1)
        executor, repository, _ = _executor(episode, turn=9)

        _run(executor, {"handles": [episode.handle]})

        stored = repository.find_by_handle(ADA, episode.handle)
        assert stored is not None
        assert (stored.recall_count, stored.last_recalled_turn) == (1, 9)

    def test_unknown_handle_is_not_remembered_while_the_others_are_returned(self) -> None:
        """知らない呼び名には「そのような記憶は思い出せない」と返し、ほかの呼び名は通常どおり本文を返す。"""
        episode = _episode(1)
        executor, _, _ = _executor(episode)

        result = _run(executor, {"handles": ["ep_ffffff", episode.handle]})

        assert result.success is True
        assert result.message.splitlines() == [
            f"[ep_ffffff] {UNKNOWN_EPISODE_TEXT}",
            f"[{episode.handle}] 金庫の番号を探した",
            "  棚の紙に 4 桁が書いてあった。",
        ]
        assert UNKNOWN_EPISODE_TEXT == "そのような記憶は思い出せない。"

    def test_more_handles_than_the_limit_recalls_nothing(self) -> None:
        """上限 M 件より多い呼び名を渡すと、どれも呼び出さず、上限を添えて失敗を返す。"""
        episodes = [_episode(n) for n in range(1, 4)]
        executor, repository, _ = _executor(*episodes, max_handles=2)

        result = _run(executor, {"handles": [e.handle for e in episodes]})

        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"
        assert "2 件まで" in result.message
        assert all(e.recall_count == 0 for e in repository.list_by_being(ADA))

    def test_the_same_handle_twice_counts_once_toward_the_limit(self) -> None:
        """同じ呼び名を重ねて渡しても 1 件と数え、上限の内なら呼び出す。"""
        episode = _episode(1)
        executor, repository, _ = _executor(episode, max_handles=1)

        result = _run(executor, {"handles": [episode.handle, episode.handle]})

        assert result.success is True
        stored = repository.find_by_handle(ADA, episode.handle)
        assert stored is not None and stored.recall_count == 1

    @pytest.mark.parametrize(
        "arguments",
        [
            pytest.param({}, id="missing"),
            pytest.param({"handles": []}, id="empty"),
            pytest.param({"handles": "ep_000001"}, id="bare_string"),
            pytest.param({"handles": [1]}, id="not_a_string"),
            pytest.param({"handles": ["  "]}, id="blank"),
        ],
    )
    def test_malformed_handles_are_rejected_with_how_to_write_them(self, arguments: dict[str, Any]) -> None:
        """呼び名が配列の文字列として読めなければ、書き方を添えて INVALID_ARGUMENT を返す。"""
        executor, _, recorder = _executor(_episode(1))

        result = _run(executor, arguments)

        assert result.success is False
        assert result.error_code == "INVALID_ARGUMENT"
        assert "【思い出せる出来事】" in result.message
        assert [p["outcome"] for p in _recall_traces(recorder)] == ["rejected"]


class TestRecallTrace:
    """呼び出しのたびに、呼び名と見つかったかが trace に 1 件残ることを保証する。"""

    def test_records_handles_found_and_counts(self) -> None:
        """呼び出すと、渡した呼び名・呼び名ごとの見つかったか・呼び出したあとの回数・ターン数が残る。"""
        episode = _episode(1)
        executor, _, recorder = _executor(episode, turn=4)

        _run(executor, {"handles": [episode.handle, "ep_ffffff"]})

        [payload] = _recall_traces(recorder)
        assert payload == {
            "being_id": ADA.value,
            "outcome": "recalled",
            "turn": 4,
            "requested": [episode.handle, "ep_ffffff"],
            "results": [
                {"handle": episode.handle, "found": True, "recall_count": 1},
                {"handle": "ep_ffffff", "found": False, "recall_count": None},
            ],
        }

    def test_records_why_it_was_rejected(self) -> None:
        """上限を超えて断ったときは、理由と渡した呼び名と上限を残す。"""
        executor, _, recorder = _executor(_episode(1), max_handles=1)

        _run(executor, {"handles": ["ep_000001", "ep_000002"]})

        [payload] = _recall_traces(recorder)
        assert (payload["outcome"], payload["reject_reason"], payload["max_handles"]) == ("rejected", "too_many", 1)
        assert payload["requested"] == ["ep_000001", "ep_000002"]

"""メモ帳を有効にした runtime で、環境の tool に添えた引数 memo が 1 手のうちにメモ帳へ当たることを保証する (#1628)。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_rpg_world.application.llm.services.action_summary_format import (
    format_action_summary_for_display,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.world_llm_turn.memo_turn import (
    WRITING_FAILED_TEXT,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_WAIT
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.being.domain.memo_book import KIND_LIMITS, MemoBook, MemoKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring
from tests.application.being.expectation.support import (
    RecordingTraceRecorder,
    ScriptedJudgmentPort,
)

_DRILL = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
_ME = PlayerId(1)


def _game(memo: Any, *, enabled: bool = True) -> tuple[Any, _WorldLlmWiring, RecordingTraceRecorder]:
    config = ResolvedLlmRuntimeConfig.for_tests(
        being_memo_enabled=enabled, memo_tools_enabled=not enabled
    )
    runtime = create_world_runtime(_DRILL, config=config)
    recorder = RecordingTraceRecorder()
    runtime.set_trace_recorder(recorder)
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=StubLlmClient(
            {"name": TOOL_NAME_SPOT_GRAPH_WAIT, "arguments": {"inner_thought": "様子を見る", "memo": memo}}
        ),
        typed_judgment_port=ScriptedJudgmentPort(),
    )
    return runtime, wiring, recorder


def _book(runtime: Any) -> MemoBook:
    acting = runtime._acting_being_for(_ME)
    return runtime._being_memo_store.get(acting.being_id)


def _turn(wiring: _WorldLlmWiring) -> Any:
    return wiring.run_phase_b(wiring.run_phase_a(_ME))


class TestMemoArgumentInATurn:
    """引数 memo の操作が、行動を止めずに、その手のターン数と環境の名前でメモ帳に当たることを保証する。"""

    def test_memo_written_with_wait_lands_in_the_book(self) -> None:
        """待つ行動に添えたやることは、行動が通ったうえで、その手のターン数と環境の名前を持ってメモ帳に入る。"""
        runtime, wiring, _ = _game([{"do": "add", "kind": "todo", "text": "事務所で鍵を取る"}])

        result = _turn(wiring)

        (memo,) = _book(runtime).memos
        acting = runtime._acting_being_for(_ME)
        assert result.success
        assert (memo.kind, memo.text) == (MemoKind.TODO, "事務所で鍵を取る")
        assert memo.written_turn == runtime._memory_turn_clock.current_turn(acting.being_id)
        assert memo.environment_name == runtime.environment_name_for(_ME)

    def test_a_broken_operation_is_returned_but_the_others_land(self) -> None:
        """崩れた操作は理由を結果の文に添えて返し、同じ行動のほかの操作はメモ帳に入る。"""
        runtime, wiring, recorder = _game(
            [{"do": "add", "kind": "fact", "text": "鍵は事務所にある"}, {"do": "add", "kind": "person", "text": "駅長は鍵に詳しい"}]
        )

        result = _turn(wiring)

        assert [m.text for m in _book(runtime).memos] == ["駅長は鍵に詳しい"]
        assert "[メモ] 次の操作は書けませんでした。" in result.message
        assert "1 件目: 分かったこと (fact) には source" in result.message
        (event,) = recorder.payloads(TraceEventKind.BEING_MEMO)
        assert [(r["index"], r["reason"]) for r in event["rejected"]] == [(0, "missing_provenance")]
        assert [(a["index"], a["do"], a["text"]) for a in event["applied"]] == [(1, "add", "駅長は鍵に詳しい")]

    def test_limit_reached_is_returned_with_the_kind(self) -> None:
        """やることが上限のときに足すと、上限であることと直し方を結果の文で返し、元の値を trace に残す。"""
        operation = {"do": "add", "kind": "todo", "text": "もう一つ"}
        runtime, wiring, recorder = _game([operation])
        acting = runtime._acting_being_for(_ME)
        book = MemoBook.empty()
        for n in range(KIND_LIMITS[MemoKind.TODO]):
            book = book.add(
                memo_id=f"{n:06x}aa-1d2e-4f00-8a00-000000000000",
                kind=MemoKind.TODO,
                text=f"用事{n}",
                provenance=None,
                turn=0,
                environment_name="駅",
            )
        runtime._being_memo_store.save(acting.being_id, book)

        result = _turn(wiring)

        assert "やることが上限 (5 件) です。消すか書き換えてください。" in result.message
        (event,) = recorder.payloads(TraceEventKind.BEING_MEMO)
        assert event["rejected"] == [{"index": 0, "reason": "limit_reached", "raw": operation, "detail": None}]

    def test_removed_memo_is_traced(self) -> None:
        """消す操作は、消したメモの分類と文を trace に残す。"""
        runtime, wiring, recorder = _game([{"do": "remove", "id": "m_3f2a7b"}])
        acting = runtime._acting_being_for(_ME)
        runtime._being_memo_store.save(
            acting.being_id,
            MemoBook.empty().add(
                memo_id="3f2a7b9c-1d2e-4f00-8a00-000000000001",
                kind=MemoKind.TODO,
                text="鍵を取る",
                provenance=None,
                turn=0,
                environment_name="駅",
            ),
        )

        _turn(wiring)

        assert _book(runtime) == MemoBook.empty()
        (event,) = recorder.payloads(TraceEventKind.BEING_MEMO)
        assert event["applied"][0] | {"provenance": None} == {
            "index": 0, "do": "remove", "handle": "m_3f2a7b", "kind": "todo", "text": "鍵を取る", "provenance": None
        }

    def test_memo_is_not_read_when_the_book_is_disabled(self) -> None:
        """メモ帳を無効にした設定では、引数 memo を書いても読まず、メモ帳にも trace にも何も残さない。"""
        runtime, wiring, recorder = _game([{"do": "add", "kind": "todo", "text": "鍵"}], enabled=False)

        _turn(wiring)

        assert _book(runtime) == MemoBook.empty()
        assert recorder.payloads(TraceEventKind.BEING_MEMO) == []

    def test_memo_book_is_shown_every_turn_with_all_headings(self) -> None:
        """メモ帳を有効にした設定では、メモが無くても 1 ターン目のプロンプトに【メモ】と 3 つの分類の見出しが出る。"""
        _, wiring, _ = _game(None)

        phase_a = wiring.run_phase_a(_ME)

        user = phase_a.prompt["messages"][-1]["content"]
        assert "【メモ】\nやること:\n  (なし)\n分かったこと:\n  (なし)\n人について:\n  (なし)" in user

    def test_completion_hint_reads_todos_from_the_book(self) -> None:
        """メモ帳を有効にした設定では、済んだかの知らせがメモ帳のやることを見て、行動と重なるやることを知らせる。"""
        runtime, wiring, _ = _game(None)
        acting = runtime._acting_being_for(_ME)
        runtime._being_memo_store.save(
            acting.being_id,
            MemoBook.empty().add(
                memo_id="3f2a7b9c-1d2e-4f00-8a00-000000000001",
                kind=MemoKind.TODO,
                text="事務所で鍵を取る",
                provenance=None,
                turn=0,
                environment_name="駅",
            ),
        )
        service = wiring.memo_completion_hint_service
        assert service is not None
        service.judgment_port = None

        hint = service.detect(acting.being_id, "事務所で鍵を取る", "鍵を手に入れた").hint

        assert hint is not None and hint.memo.content == "事務所で鍵を取る"

    def test_writing_failure_is_returned_and_traced_without_stopping_the_action(self) -> None:
        """メモ帳へ書く途中で失敗しても行動は通り、書けなかったことを結果の文で返し、理由を trace に残す。"""
        runtime, wiring, recorder = _game([{"do": "add", "kind": "todo", "text": "鍵"}])

        def broken(player_id: PlayerId) -> str:
            raise RuntimeError("environment is gone")

        runtime.environment_name_for = broken

        result = _turn(wiring)

        assert result.success
        assert WRITING_FAILED_TEXT in result.message
        (event,) = recorder.payloads(TraceEventKind.BEING_MEMO)
        assert (event["skipped_reason"], event["error"]) == ("writing_failed", "RuntimeError: environment is gone")

    def _hinted(self, *, added_in_the_same_call: bool) -> str:
        summary = format_action_summary_for_display(TOOL_NAME_SPOT_GRAPH_WAIT, {"inner_thought": "様子を見る"})
        memo = [{"do": "add", "kind": "todo", "text": summary}] if added_in_the_same_call else None
        runtime, wiring, _ = _game(memo)
        if not added_in_the_same_call:
            acting = runtime._acting_being_for(_ME)
            runtime._being_memo_store.save(
                acting.being_id,
                MemoBook.empty().add(
                    memo_id="3f2a7b9c-1d2e-4f00-8a00-000000000001",
                    kind=MemoKind.TODO,
                    text=summary,
                    provenance=None,
                    turn=0,
                    environment_name="駅",
                ),
            )
        service = wiring.memo_completion_hint_service
        assert service is not None
        service.judgment_port = None
        return _turn(wiring).message

    def test_todo_written_before_gets_a_hint_when_the_action_matches(self) -> None:
        """前の手で書いたやることと同じ行動をすると、済んだかもしれないと知らせる。"""
        assert "は済んだかもしれません" in self._hinted(added_in_the_same_call=False)

    def test_todo_added_in_the_same_call_gets_no_hint(self) -> None:
        """同じ行動に添えて足したやることは、行動の文と重なっても、済んだのではと知らせない。"""
        assert "は済んだかもしれません" not in self._hinted(added_in_the_same_call=True)

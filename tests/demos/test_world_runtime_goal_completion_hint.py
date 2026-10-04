"""目的の達成 hint が、行動の結果の文と trace まで届く (#1448)。

service が正しい hint を返すことと、**行動の結果にその hint が添えられること**は
別の事実である。本番と同じ入口 (``GameRuntimeManager.create_session``) から
session を組み、``run_turn`` の結果と trace を見る。

hint のあとに本人が ``goal_outcome`` で申告したかを数えられるよう、判断の
trace には ``goal_id`` と ``being_id`` を載せる。``GOAL_RESOLUTION`` と
同じ鍵で突き合わせる。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from tests.demos._world_runtime_helpers import (
    create_world_runtime_session as _create_session,
)
from tests.runtime_config_helpers import episodic_config

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    Question,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.goal_completion_hint_service import (
    GoalCompletionHintService,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    MemoCompletionHintService,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_ORIGIN_SELF,
    GOAL_STATUS_ACTIVE,
    GoalEntry,
)

_GOAL_TEXT = "閲覧室へ行く"
_GOAL_HINT = f"[hint] 目的「{_GOAL_TEXT}」は達成したかもしれない。"


class _FixedPort(ITypedJudgmentPort):
    """どの質問にも同じ確率を返す。問われた回数を数える。"""

    def __init__(
        self,
        probability: float = 0.9,
        *,
        raises: bool = False,
        raises_unexpected: bool = False,
    ) -> None:
        self.calls: list[Mapping[str, Question]] = []
        self.states: list[Any] = []
        self._probability = probability
        self._raises = raises
        self._raises_unexpected = raises_unexpected

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        self.calls.append(questions)
        self.states.append(state)
        if self._raises_unexpected:
            raise RuntimeError("port bug")
        if self._raises:
            raise TypedJudgmentUnavailableException(
                "down", error_code="TYPED_JUDGMENT_TIMEOUT"
            )
        return {
            name: JudgmentResult(
                value=self._probability,
                probabilities={},
                confidence=None,
                source=JudgmentSource.JEV,
                latency_ms=80.0,
            )
            for name in questions
        }


class _CapturingRecorder:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind: str, **payload: Any) -> None:
        self.records.append((kind, dict(payload)))

    def goal_judgments(self) -> list[dict[str, Any]]:
        return [
            payload
            for kind, payload in self.records
            if kind == TraceEventKind.TYPED_JUDGMENT
            and payload.get("question") == "goal_achieved"
        ]


def _config(*, goal_hint_enabled: bool = True) -> ResolvedLlmRuntimeConfig:
    # goal store は episodic stack と一緒に組まれる。
    return episodic_config(
        typed_judgment_provider="stub",
        typed_judgment_goal_hint_enabled=goal_hint_enabled,
        goal_store_enabled=True,
        goal_revision_enabled=True,
    )


def _session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    port: ITypedJudgmentPort | None,
    *,
    goal_hint_enabled: bool = True,
    goal_texts: Sequence[str] = (_GOAL_TEXT,),
) -> tuple[Any, Any, str, _CapturingRecorder]:
    """自分で立てた目的を持つ session を組み、判断ポートを ``port`` に差し替える。"""
    state = _create_session(
        monkeypatch,
        tmp_path,
        runtime_config=_config(goal_hint_enabled=goal_hint_enabled),
    )
    runtime = state.runtime
    player_id = runtime.get_player_ids()[0]
    being_id = runtime._acting_being_for(player_id).being_id
    for index, text in enumerate(goal_texts, start=1):
        runtime._goal_journal_store.add_by_being(
            being_id,
            GoalEntry(
                goal_id=f"goal-self-{index}",
                player_id=int(player_id.value),
                text=text,
                status=GOAL_STATUS_ACTIVE,
                locked=False,
                origin=GOAL_ORIGIN_SELF,
                created_tick=0,
                created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            ),
        )
    if port is not None:
        state.llm_wiring.goal_completion_hint_service = GoalCompletionHintService(
            runtime._goal_journal_store, judgment_port=port, min_probability=0.7
        )
    recorder = _CapturingRecorder()
    runtime.set_trace_recorder(recorder)
    return state, player_id, str(being_id.value), recorder


def _act(state: Any, player_id: Any, name: str, arguments: dict[str, Any]) -> Any:
    state.llm_wiring.llm_client = StubLlmClient(
        tool_call_to_return={"name": name, "arguments": arguments}
    )
    return state.llm_wiring.run_turn(player_id)


class TestTheHintReachesTheResult:
    """確率が閾値以上なら、行動の結果の文に hint が添えられることを保証する。"""

    def test_a_likely_goal_is_hinted_in_the_result(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """確率 0.9 で閾値 0.7 なら、結果の文に目的の hint と goal_outcome が付く。"""
        state, player_id, _, _ = _session(monkeypatch, tmp_path, _FixedPort(0.9))

        result = _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        assert _GOAL_HINT in result.message
        assert "goal_outcome で記録する" in result.message

    def test_the_hint_reaches_the_action_result_trace(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """trace の action_result にも hint を添えた結果の文が残る。"""
        state, player_id, _, recorder = _session(
            monkeypatch, tmp_path, _FixedPort(0.9)
        )

        _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        (action_result,) = [
            payload for kind, payload in recorder.records if kind == "action_result"
        ]
        assert _GOAL_HINT in action_result["result_summary"]

    def test_an_unlikely_goal_leaves_the_result_unchanged(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """確率 0.2 で閾値 0.7 なら、Jev は問われるが結果の文に hint は付かない。"""
        port = _FixedPort(0.2)
        state, player_id, _, _ = _session(monkeypatch, tmp_path, port)

        result = _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        assert len(port.calls) == 1
        assert "[hint] 目的" not in result.message

    def test_the_goal_store_is_left_as_it_was(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """hint を出しても、目的の store は前後で同じ (状態・文・件数とも)。清算するのは本人。"""
        state, player_id, _, _ = _session(monkeypatch, tmp_path, _FixedPort(0.99))
        store = state.runtime._goal_journal_store
        being = state.runtime._acting_being_for(player_id).being_id
        before = store.list_all_by_being(being)

        result = _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        assert _GOAL_HINT in result.message
        assert store.list_all_by_being(being) == before

    def test_every_likely_goal_gets_its_own_hint(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """目的が 2 件とも閾値以上なら、Jev は 1 回だけ呼ばれ、2 件の hint が結果の文に付き、判断の trace も 2 件残る。"""
        port = _FixedPort(0.9)
        state, player_id, _, recorder = _session(
            monkeypatch, tmp_path, port, goal_texts=(_GOAL_TEXT, "書庫で休む")
        )

        result = _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        assert len(port.calls) == 1
        assert _GOAL_HINT in result.message
        assert "[hint] 目的「書庫で休む」は達成したかもしれない。" in result.message
        assert len(recorder.goal_judgments()) == 2

    def test_the_judgment_sees_the_result_without_the_memo_hint(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """memo の hint も付く行動では、Jev に渡す結果の文に memo の hint は入らず、結果の文は memo、目的の順に hint が並ぶ。"""
        port = _FixedPort(0.9)
        state, player_id, _, _ = _session(monkeypatch, tmp_path, port)
        state.llm_wiring.memo_completion_hint_service = MemoCompletionHintService(
            memo_store=state.runtime._todo_store
        )
        _act(state, player_id, "memo_add", {"content": "閲覧室へ移動する"})

        result = _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        (judged_state,) = port.states
        assert "[hint]" not in judged_state["result"]
        memo_at = result.message.index("[hint] memo")
        goal_at = result.message.index(_GOAL_HINT)
        assert memo_at < goal_at


class TestTheJudgmentIsTraced:
    """目的ごとの判断と縮退の理由が trace に残ることを保証する。"""

    def test_each_goal_judgment_is_traced_with_keys_to_match_the_resolution(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """判断ごとに確率・閾値・hint を出したか・goal_id・being_id が残る。"""
        state, player_id, being_id, recorder = _session(
            monkeypatch, tmp_path, _FixedPort(0.9)
        )

        _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        (judgment,) = recorder.goal_judgments()
        assert judgment["goal_id"] == "goal-self-1"
        assert judgment["being_id"] == being_id
        assert judgment["player_id"] == int(player_id.value)
        assert judgment["probability"] == pytest.approx(0.9)
        assert judgment["min_confidence"] == pytest.approx(0.7)
        assert judgment["accepted"] is True
        assert judgment["unavailable_reason"] is None
        assert judgment["tool_name"] == "travel_to"

    def test_an_unavailable_judgment_gives_no_hint_and_traces_the_reason(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Jev が例外を投げたら hint を出さず、理由を 1 件 trace に残す。"""
        state, player_id, _, recorder = _session(
            monkeypatch, tmp_path, _FixedPort(raises=True)
        )

        result = _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        assert "[hint] 目的" not in result.message
        (judgment,) = recorder.goal_judgments()
        assert judgment["unavailable_reason"] == "TYPED_JUDGMENT_TIMEOUT"
        assert judgment["accepted"] is False
        assert judgment["probability"] is None

    def test_an_unexpected_error_gives_no_hint_and_traces_its_type(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """判断の途中で想定外の例外が出ても、行動は壊れず hint を出さず、例外の型を理由に trace に残す。"""
        state, player_id, _, recorder = _session(
            monkeypatch, tmp_path, _FixedPort(raises_unexpected=True)
        )

        result = _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        assert result.success is True
        assert "[hint] 目的" not in result.message
        (judgment,) = recorder.goal_judgments()
        assert judgment["unavailable_reason"] == "UNEXPECTED:RuntimeError"


class TestWhenNotToAsk:
    """問う意味の無い行動では Jev を呼ばないことを保証する。"""

    @pytest.mark.parametrize("outcome", ["achieved", "abandoned"])
    def test_an_action_that_settles_the_goal_is_not_asked(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: str
    ) -> None:
        """行動と同時に goal_outcome (achieved / abandoned) を書いたなら、本人が清算しているので問わない。"""
        port = _FixedPort(0.9)
        state, player_id, _, _ = _session(monkeypatch, tmp_path, port)

        result = _act(
            state,
            player_id,
            "travel_to",
            {"destination_label": "閲覧室", "goal_outcome": outcome},
        )

        assert port.calls == []
        assert "[hint] 目的" not in result.message

    def test_an_action_that_rewrites_the_goal_is_not_asked(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """行動と同時に goal_update で目的を言い直したなら、古い目的は問わない。"""
        port = _FixedPort(0.9)
        state, player_id, _, _ = _session(monkeypatch, tmp_path, port)

        _act(
            state,
            player_id,
            "travel_to",
            {"destination_label": "閲覧室", "goal_update": "書庫の奥を調べる"},
        )

        assert port.calls == []

    def test_a_blank_goal_update_is_still_asked(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """goal_update が空白だけなら目的は言い直されないので、問う。"""
        port = _FixedPort(0.9)
        state, player_id, _, _ = _session(monkeypatch, tmp_path, port)

        _act(
            state,
            player_id,
            "travel_to",
            {"destination_label": "閲覧室", "goal_update": "  "},
        )

        assert len(port.calls) == 1

    def test_a_failed_action_is_not_asked(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """行動が失敗したなら、目的は進んでいないので問わない。"""
        port = _FixedPort(0.9)
        state, player_id, _, _ = _session(monkeypatch, tmp_path, port)

        result = _act(state, player_id, "travel_to", {"destination_label": "存在しない部屋"})

        assert result.success is False
        assert port.calls == []

    def test_a_memo_tool_is_not_asked(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """memo の操作は goal_outcome を持たない tool なので問わない。"""
        port = _FixedPort(0.9)
        state, player_id, _, _ = _session(monkeypatch, tmp_path, port)

        result = _act(state, player_id, "memo_add", {"content": "閲覧室へ行く"})

        assert result.success is True
        assert port.calls == []


class TestDisabledLeavesTheResultAlone:
    """無効なときは結果の文が変わらないことを保証する。"""

    def test_a_disabled_goal_hint_leaves_the_result_unchanged(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """profile で有効にしていなければ、hint の service は無く結果の文に hint が付かない。"""
        state, player_id, _, recorder = _session(
            monkeypatch, tmp_path, None, goal_hint_enabled=False
        )

        result = _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        assert state.llm_wiring.goal_completion_hint_service is None
        assert "[hint] 目的" not in result.message
        assert recorder.goal_judgments() == []


class TestTheSkipIsTraced:
    """判断を見送った理由が、being ごとに理由が変わったときだけ trace に残ることを保証する (#1512)。"""

    @staticmethod
    def _skips(recorder: _CapturingRecorder) -> list[str]:
        return [
            payload["skipped_reason"]
            for payload in recorder.goal_judgments()
            if payload.get("skipped_reason") is not None
        ]

    def test_a_goal_the_scenario_locked_is_traced_as_the_reason_to_skip(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """シナリオが固定した目的しか無ければ、Jev は呼ばれず、見送りの理由 only_locked_goals が being_id つきで 1 件残る。"""
        port = _FixedPort(0.9)
        state, player_id, being_id, recorder = _session(
            monkeypatch, tmp_path, port, goal_texts=()
        )

        _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        assert port.calls == []
        (skip,) = recorder.goal_judgments()
        assert skip["skipped_reason"] == "only_locked_goals"
        assert skip["being_id"] == being_id
        assert skip["accepted"] is False
        assert skip["probability"] is None
        assert skip["unavailable_reason"] is None

    def test_the_same_reason_is_traced_only_once(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """同じ理由で 2 回続けて見送ったら、trace に残るのは最初の 1 件だけ。"""
        state, player_id, _, recorder = _session(
            monkeypatch, tmp_path, _FixedPort(0.9), goal_texts=()
        )

        _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})
        _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        assert self._skips(recorder) == ["only_locked_goals"]

    def test_a_changed_reason_is_traced_again(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """失敗した行動、memo、失敗した行動と理由が変わるたびに 1 件ずつ残る。"""
        state, player_id, _, recorder = _session(monkeypatch, tmp_path, _FixedPort(0.9))

        _act(state, player_id, "travel_to", {"destination_label": "存在しない部屋"})
        _act(state, player_id, "memo_add", {"content": "閲覧室へ行く"})
        _act(state, player_id, "travel_to", {"destination_label": "存在しない部屋"})

        assert self._skips(recorder) == [
            "action_failed",
            "goal_outcome_not_offered",
            "action_failed",
        ]

    def test_the_same_reason_after_a_judgment_is_traced_again(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """見送り、判断、同じ理由での見送りと続いたら、見送りは 2 件とも残る。間に判断があれば理由は途切れている。"""
        state, player_id, _, recorder = _session(monkeypatch, tmp_path, _FixedPort(0.2))

        _act(state, player_id, "travel_to", {"destination_label": "存在しない部屋"})
        _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})
        _act(state, player_id, "travel_to", {"destination_label": "存在しない部屋"})

        assert self._skips(recorder) == ["action_failed", "action_failed"]

    def test_an_action_that_settles_the_goal_is_traced_as_the_reason_to_skip(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """行動と同時に goal_outcome を書いたら、見送りの理由 goal_settled_by_action が残る。"""
        state, player_id, _, recorder = _session(monkeypatch, tmp_path, _FixedPort(0.9))

        _act(
            state,
            player_id,
            "travel_to",
            {"destination_label": "閲覧室", "goal_outcome": "achieved"},
        )

        assert self._skips(recorder) == ["goal_settled_by_action"]

    def test_a_judged_action_leaves_no_skip(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """問える目的があって判断したなら、判断の trace に skipped_reason は None で載る。"""
        state, player_id, _, recorder = _session(monkeypatch, tmp_path, _FixedPort(0.9))

        _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        (judgment,) = recorder.goal_judgments()
        assert judgment["skipped_reason"] is None
        assert judgment["goal_id"] == "goal-self-1"


class TestTheLockedGoalsAreNoticedAtStartup:
    """目的の知らせを有効にしたのに初期目的が固定されるプレイヤーがいれば、起動時に警告と trace を残すことを保証する (#1512)。"""

    @staticmethod
    def _notices(recorder: _CapturingRecorder) -> list[dict[str, Any]]:
        return [
            payload
            for kind, payload in recorder.records
            if kind == TraceEventKind.NOTE
            and payload.get("topic") == "goal_completion_hint"
        ]

    def test_locked_initial_goals_are_noted_once_when_the_trace_starts(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """勝敗条件のあるシナリオで有効にすると、recorder を差し込んだ時点で固定されるプレイヤーを並べた note が 1 件残る。差し直しても増えない。"""
        state = _create_session(monkeypatch, tmp_path, runtime_config=_config())
        runtime = state.runtime
        recorder = _CapturingRecorder()

        runtime.set_trace_recorder(recorder)
        runtime.set_trace_recorder(recorder)

        (notice,) = self._notices(recorder)
        assert notice["locked_player_ids"] == [
            int(pid.value) for pid in runtime.get_player_ids()
        ]
        assert notice["all_players_locked"] is True

    def test_locked_initial_goals_are_warned_when_the_runtime_is_built(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """勝敗条件のあるシナリオで有効にすると、session を組んだ時点で warning が出る。"""
        with caplog.at_level("WARNING"):
            _create_session(monkeypatch, tmp_path, runtime_config=_config())

        assert any(
            "TYPED_JUDGMENT_GOAL_HINT_ENABLED" in record.getMessage()
            for record in caplog.records
            if record.levelname == "WARNING"
        )

    def test_unlocked_initial_goals_leave_no_note(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """どのプレイヤーの初期目的も固定されないなら、note は残らない。"""
        state = _create_session(monkeypatch, tmp_path, runtime_config=_config())
        runtime = state.runtime
        monkeypatch.setattr(runtime, "_resolve_player_goal_locked", lambda _pid: False)
        recorder = _CapturingRecorder()

        runtime.set_trace_recorder(recorder)

        assert self._notices(recorder) == []

    def test_a_disabled_goal_hint_leaves_no_note(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """目的の知らせを有効にしていなければ、固定された目的があっても note は残らない。"""
        state = _create_session(
            monkeypatch, tmp_path, runtime_config=_config(goal_hint_enabled=False)
        )
        recorder = _CapturingRecorder()

        state.runtime.set_trace_recorder(recorder)

        assert self._notices(recorder) == []

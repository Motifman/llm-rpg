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

    def __init__(self, probability: float = 0.9, *, raises: bool = False) -> None:
        self.calls: list[Mapping[str, Question]] = []
        self._probability = probability
        self._raises = raises

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        self.calls.append(questions)
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
) -> tuple[Any, Any, str, _CapturingRecorder]:
    """自分で立てた目的を 1 件持つ session を組み、判断ポートを ``port`` に差し替える。"""
    state = _create_session(
        monkeypatch,
        tmp_path,
        runtime_config=_config(goal_hint_enabled=goal_hint_enabled),
    )
    runtime = state.runtime
    player_id = runtime.get_player_ids()[0]
    being_id = runtime._acting_being_for(player_id).being_id
    runtime._goal_journal_store.add_by_being(
        being_id,
        GoalEntry(
            goal_id="goal-self-1",
            player_id=int(player_id.value),
            text=_GOAL_TEXT,
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

    def test_the_hinted_goal_stays_active(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """hint を出しても、目的は active のまま残る。清算するのは本人。"""
        state, player_id, being_id, _ = _session(
            monkeypatch, tmp_path, _FixedPort(0.99)
        )

        _act(state, player_id, "travel_to", {"destination_label": "閲覧室"})

        goals = state.runtime._goal_journal_store.list_all_by_being(
            state.runtime._acting_being_for(player_id).being_id
        )
        (goal,) = [goal for goal in goals if goal.goal_id == "goal-self-1"]
        assert goal.status == GOAL_STATUS_ACTIVE


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


class TestWhenNotToAsk:
    """問う意味の無い行動では Jev を呼ばないことを保証する。"""

    def test_an_action_that_settles_the_goal_is_not_asked(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """行動と同時に goal_outcome を書いたなら、本人が清算しているので問わない。"""
        port = _FixedPort(0.9)
        state, player_id, _, _ = _session(monkeypatch, tmp_path, port)

        result = _act(
            state,
            player_id,
            "travel_to",
            {"destination_label": "閲覧室", "goal_outcome": "achieved"},
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

    def test_a_memo_tool_is_not_asked(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """memo の操作は goal_outcome を持たない tool なので問わない。"""
        port = _FixedPort(0.9)
        state, player_id, _, _ = _session(monkeypatch, tmp_path, port)

        _act(state, player_id, "memo_add", {"content": "閲覧室へ行く"})

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

"""U5 (MEMO_DISTILL) の配線が executor 作り直しで失われないことを固定する。

回帰対象の silent failure: ``create_world_runtime`` は memo_distill transcriber
を ``_todo_tool_executor`` に setter 注入していたが、``set_trace_recorder``
(実験 run が build 後に必ず呼ぶ) が ``_todo_tool_executor`` を作り直すため、
transcriber が静かに失われ、実験 run で memo_done があっても MEMO_DISTILL
evidence が 0 件になっていた。

修正: transcriber を ``runtime._memo_distill_transcriber`` に保持し、
``_wire_auxiliary_tool_stack`` が executor を作り直すたびに再適用する。

LLM は呼ばない (stub client)。flag は default ON だが、配線前提を明示するため
各テストで設定を固定する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ai_rpg_world.application.trace import NullTraceRecorder
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMO_ADD,
    TOOL_NAME_MEMO_DONE,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import (
    EpisodeAction,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import (
    EpisodeLocation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import (
    EpisodeSource,
)
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.runtime_config_helpers import episodic_config

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _memo_distill_config():
    # MEMO_DISTILL の transcriber が構築される前提: episodic + 証拠 buffer (U2)。
    return episodic_config(
        belief_evidence_enabled=True,
        memo_distill_enabled=True,
    )


def _episode(episode_id: str) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=1,
        occurred_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(),
        action=EpisodeAction(tool_name="memo_add"),
        who=(),
        what="w",
        why=None,
        observed="o",
        expected=None,
        outcome="ok",
        prediction_error=None,
        felt=None,
        interpreted=None,
        cues=(),
    )


class TestWorldRuntimeMemoDistillRewire:
    def test_transcriber_wired_after_build(self) -> None:
        runtime = create_world_runtime(_SCENARIO_PATH, config=_memo_distill_config())
        assert runtime._memo_distill_transcriber is not None
        assert runtime._todo_tool_executor is not None
        # memo executor 実体にも届いている。
        assert runtime._todo_tool_executor._memo_distill_transcriber is not None

    def test_transcriber_survives_set_trace_recorder_rebuild(self) -> None:
        """set_trace_recorder は _todo_tool_executor を作り直すが、

        memo_distill transcriber は再適用されて生き残る (回帰の核心)。"""
        runtime = create_world_runtime(_SCENARIO_PATH, config=_memo_distill_config())
        executor_before = runtime._todo_tool_executor
        assert executor_before is not None
        assert executor_before._memo_distill_transcriber is not None

        # 実験 run と同じく build 後に trace recorder を差し込む → 作り直し。
        runtime.set_trace_recorder(NullTraceRecorder())

        executor_after = runtime._todo_tool_executor
        assert executor_after is not None
        # 作り直しで別インスタンスになっている (前提の確認)。
        assert executor_after is not executor_before
        # それでも transcriber は再適用されている (修正が効いている)。
        assert executor_after._memo_distill_transcriber is not None

    def test_flag_off_keeps_transcriber_none(self) -> None:
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=episodic_config(memo_distill_enabled=False),
        )
        assert runtime._memo_distill_transcriber is None
        if runtime._todo_tool_executor is not None:
            assert runtime._todo_tool_executor._memo_distill_transcriber is None

    def test_memo_done_creates_memo_distill_belief_evidence(self) -> None:
        """runtime 配線後の memo_done が MEMO_DISTILL の BeliefEvidence を実際に積む。"""
        runtime = create_world_runtime(_SCENARIO_PATH, config=_memo_distill_config())
        assert runtime._todo_tool_executor is not None
        assert runtime._episodic_stack is not None
        buffer_store = runtime._episodic_stack.belief_evidence_buffer_store
        assert buffer_store is not None

        being_id = runtime._aux_being_resolver.resolve_being_id(
            runtime._aux_being_default_world_id,
            PlayerId(1),
        )
        assert being_id is not None
        runtime._episodic_stack.episode_store.put_by_being(
            being_id,
            _episode("ep-memo-anchor"),
        )
        add_result = runtime.run_llm_auxiliary_tool(
            PlayerId(1),
            TOOL_NAME_MEMO_ADD,
            {"content": "夜明けに山頂へ向かう計画を維持する"},
        )
        assert add_result.success is True
        memo_id = runtime._todo_store.list_uncompleted_by_being(being_id)[0].id

        done_result = runtime.run_llm_auxiliary_tool(
            PlayerId(1),
            TOOL_NAME_MEMO_DONE,
            {"memo_ids": [memo_id]},
        )

        assert done_result.success is True
        evidences = buffer_store.list_all_by_being(being_id)
        assert len(evidences) == 1
        assert evidences[0].source_kind == BeliefEvidenceSourceKind.MEMO_DISTILL
        assert "夜明けに山頂へ向かう計画を維持する" in evidences[0].text

"""短期記憶は要約の要約 (L5) を作らず、【自己像と世界観】も出さない (#1824)。

長い期間の流れはエピソードの目次が受け持つ。要約は 3 世代まで残し、あふれた分は
捨てる。L5 を持っていた古い snapshot も読み込めて、L5 は捨てられる。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ai_rpg_world.application.being.world_subsystems.short_term_memory_codec import (
    ShortTermMemorySubsystemCodec,
    UnifiedRecentEventStoreSubsystemCodec,
)
from ai_rpg_world.application.llm.services.summarizing_short_term_memory import (
    SummarizingShortTermMemory,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_PID = PlayerId(7)
_NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)
_REPO_ROOT = Path(__file__).resolve().parents[4]

_OLD_L5 = {
    "summary_id": "l5-old",
    "player_id": 7,
    "generation_index": 2,
    "generated_at": _NOW.isoformat(),
    "self_image": "探索者カイ",
    "world_view": "火を絶やしてはならない島",
    "is_fallback": False,
}


class _Recorder:
    def __init__(self) -> None:
        self.kinds: list[str] = []

    def record(self, kind: str, **payload: Any) -> None:
        self.kinds.append(kind)


def _obs(prose: str) -> ObservationEntry:
    return ObservationEntry(occurred_at=_NOW, output=ObservationOutput(prose=prose, structured={}))


def _compact_generations(memory: SummarizingShortTermMemory, player_id: PlayerId, count: int) -> None:
    for generation in range(count):
        memory.append(player_id, _obs(f"出来事 {generation}"))
        for _ in range(memory._turn_cap):
            memory.complete_turn(player_id)


class TestNoLongSummaryIsMade:
    """要約が 3 世代を超えてあふれても、要約の要約を作らないことを保証する。"""

    def test_overflowing_generations_make_no_long_summary(self) -> None:
        """要約が 5 世代分たまると古い 2 世代は捨てられ、要約の要約の trace は出ない。"""
        recorder = _Recorder()
        memory = SummarizingShortTermMemory(
            turn_cap=2,
            compact_turn_count=1,
            trace_recorder_provider=lambda: recorder,
        )

        _compact_generations(memory, _PID, 5)

        assert len(memory._mid_generations(_PID.value)) == 3
        assert TraceEventKind.SHORT_TERM_MEMORY_COMPACTED in recorder.kinds
        assert "short_term_long_summary_generated" not in recorder.kinds


class TestThePromptHasNoSelfImageSection:
    """1 ターンのプロンプトに【自己像と世界観】が出ないことを保証する。"""

    def test_prompt_after_overflow_shows_recent_flow_but_not_self_image(self) -> None:
        """要約が 4 世代分たまったあとのプロンプトに、【最近の流れ】は出て【自己像と世界観】は出ない。"""
        import tests.demos.test_disabled_memory_parts_vanish_from_the_prompt as capture

        scenario, mapping = capture._profile_mapping("smoke_stub")
        runtime = capture.create_world_runtime(
            scenario,
            config=capture.ResolvedLlmRuntimeConfig.from_mapping({**mapping, **capture._OFFLINE}),
        )
        player_id = PlayerId(1)
        _compact_generations(runtime._short_term_memory, player_id, 4)
        client = capture._PromptCaptureClient()

        capture._WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=client,
            typed_judgment_port=capture.ScriptedJudgmentPort(),
        ).run_phase_a(player_id)

        prompt = "\n".join(str(message["content"]) for message in client.messages)
        assert "【最近の流れ】" in prompt
        assert "【自己像と世界観】" not in prompt


class TestOldSnapshotsWithLongSummaries:
    """要約の要約を持つ古い snapshot を読み込んでも落ちず、要約の要約は捨てられることを保証する。"""

    def test_short_term_memory_codec_drops_old_long_summaries(self) -> None:
        """ShortTermMemorySubsystemCodec は、古い snapshot の long_summaries を読み飛ばし、要約は戻す。書き出しには持たない。"""
        src = SummarizingShortTermMemory(turn_cap=2, compact_turn_count=1)
        _compact_generations(src, _PID, 1)
        captured = ShortTermMemorySubsystemCodec().capture(SimpleNamespace(_short_term_memory=src))
        old = {
            **captured,
            "long_summaries": [{"player_id": 7, "summary": _OLD_L5}],
            "long_gen_indices": [{"player_id": 7, "index": 2}],
        }
        dst = SummarizingShortTermMemory(turn_cap=2, compact_turn_count=1)

        ShortTermMemorySubsystemCodec().restore(SimpleNamespace(_short_term_memory=dst), old)

        assert "long_summaries" not in captured
        assert "long_gen_indices" not in captured
        assert len(dst._mid_generations(_PID.value)) == 1
        assert not hasattr(dst, "_long")

    def test_unified_recent_event_codec_drops_old_long_summaries(self) -> None:
        """UnifiedRecentEventStoreSubsystemCodec も、古い snapshot の long_summaries を読み飛ばし、書き出しには持たない。"""
        src = SummarizingShortTermMemory(turn_cap=2, compact_turn_count=1)
        _compact_generations(src, _PID, 1)
        src_runtime = SimpleNamespace(_short_term_memory=src, _recent_event_store=src._event_store)
        captured = UnifiedRecentEventStoreSubsystemCodec().capture(src_runtime)
        old = {
            **captured,
            "long_summaries": [{"player_id": 7, "summary": _OLD_L5}],
            "long_gen_indices": [{"player_id": 7, "index": 2}],
        }
        dst = SummarizingShortTermMemory(turn_cap=2, compact_turn_count=1)

        UnifiedRecentEventStoreSubsystemCodec().restore(
            SimpleNamespace(_short_term_memory=dst, _recent_event_store=dst._event_store), old
        )

        assert "long_summaries" not in captured
        assert "long_gen_indices" not in captured
        assert len(dst._mid_generations(_PID.value)) == 1
        assert not hasattr(dst, "_long")

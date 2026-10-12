"""記憶のターン数の数え手が、証拠と信念を作る部品まで届くことを保証する (#1452)。

配線はキーワード引数の受け渡しで繋がっているので、途中で別の数え手を渡すと、
1 手ごとにターン数を進めても証拠と信念のターン数が 0 のまま残る。
LLM は呼ばない。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnClock
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import GoalEntry
from tests.runtime_config_helpers import belief_consolidation_config

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


def _runtime():
    return create_world_runtime(
        _SCENARIO_PATH,
        config=belief_consolidation_config(
        ),
    )


class TestMemoryTurnReaderWiring:
    """runtime が持つ 1 つの数え手を、証拠と信念を作る部品が共有することを保証する。"""

    def test_runtime_owns_one_memory_turn_counter(self) -> None:
        """固着パスを組んだ runtime は、記憶のターン数の数え手を 1 つ持つ。"""
        runtime = _runtime()

        assert isinstance(runtime._memory_turn_clock, MemoryTurnClock)

    def test_all_evidence_and_belief_makers_read_the_runtime_counter(self) -> None:
        """固める処理・クラスタ昇格・chunk の証拠の転記が、どれも runtime の数え手を読む。"""
        runtime = _runtime()
        counter = runtime._memory_turn_clock
        stack = runtime._episodic_stack

        readers = {
            "consolidation": stack.belief_consolidation_coordinator._memory_turn_reader,
            "promotion": stack.episodic_semantic_promotion.memory_turn_reader,
            "chunk_evidence": stack.chunk_coordinator._belief_evidence_transcriber._memory_turn_reader,
        }

        assert {name: reader is counter for name, reader in readers.items()} == {
            name: True for name in readers
        }

    def test_evidence_takes_turn_advanced_on_the_runtime_counter(self) -> None:
        """runtime の数え手でターン数を 3 進めると、そのあと転記した目的の達成の証拠は observed_turn=3 を持つ。"""
        runtime = _runtime()
        being_id = BeingId("being_w1_p1")
        for _ in range(3):
            runtime._memory_turn_clock.advance_turn(being_id)
        transcriber = runtime._episodic_stack.chunk_coordinator._belief_evidence_transcriber
        goal = GoalEntry(
            goal_id="goal-1",
            player_id=1,
            text="山頂で狼煙を上げる",
            status="active",
            locked=False,
            origin="scenario",
            created_tick=0,
            created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )

        evidence = transcriber.record_goal_resolution(
            being_id,
            goal,
            outcome="achieved",
            occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        )

        assert evidence is not None
        assert evidence.observed_turn == 3

"""短期記憶の要約を、流れと気分だけを持つ【ここまでのいきさつ】として作る (#1824)。

出来事そのものはエピソードが持ち、やることはメモ帳が持つ。いきさつは、直近 20 ターン
より前の流れと、そのときの気分だけを持つ。言われた予定を、済んだことに書き換えない
(#1584)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from ai_rpg_world.application.being.world_subsystems.short_term_memory_codec import (
    ShortTermMemorySubsystemCodec,
)
from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)
from ai_rpg_world.application.llm.services.short_term_memory_summary_service import (
    ShortTermMemorySummaryService,
)
from ai_rpg_world.application.llm.services.summarizing_short_term_memory import (
    SummarizingShortTermMemory,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_PID = PlayerId(7)
_NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)
_SEPARATE_SAID_FROM_DONE = "「誰が何をすると言ったか」と「誰が何をしたか」を分けて書く"


class _Port:
    """要約の LLM の代わり。古い形の応答 (unresolved つき) を返し、送られた messages を残す。"""

    def __init__(self) -> None:
        self.messages: list[list[dict[str, Any]]] = []

    def complete_short_term_summary_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        self.messages.append(messages)
        return {
            "compressed_activity": "見張り台でノアと合流し、北の坑道を調べた",
            "emotional_summary": "少し不安",
            "unresolved": ["崩れた坑道の先を確かめる"],
        }


def _obs(prose: str) -> ObservationEntry:
    return ObservationEntry(occurred_at=_NOW, output=ObservationOutput(prose=prose, structured={}))


def _run_turns(memory: SummarizingShortTermMemory, count: int) -> None:
    for turn in range(count):
        memory.append(_PID, _obs(f"turn-{turn}"))
        memory.complete_turn(_PID)


class TestTheBackstoryHoldsOnlyFlowAndMood:
    """20 ターンたまると、古い 10 ターン分から、流れと気分だけを持ついきさつが作られることを保証する。"""

    def test_twenty_turns_make_a_backstory_with_flow_and_mood_only(self) -> None:
        """既定の 20 ターンで畳むと、いきさつが 1 つでき、流れと気分を持ち、片付いていないことの項目は持たない。"""
        memory = SummarizingShortTermMemory(summary_service=ShortTermMemorySummaryService(_Port()))

        _run_turns(memory, 20)

        (backstory,) = memory._mid_generations(_PID.value)
        assert backstory.compressed_activity == "見張り台でノアと合流し、北の坑道を調べた"
        assert backstory.emotional_summary == "少し不安"
        assert not hasattr(backstory, "unresolved")

    def test_unresolved_from_the_llm_does_not_reach_the_prompt(self) -> None:
        """LLM が unresolved を返しても、いきさつにも、プロンプトに出す文にも入らない。"""
        memory = SummarizingShortTermMemory(summary_service=ShortTermMemorySummaryService(_Port()))

        _run_turns(memory, 20)
        text = memory.get_mid_summary_text(_PID)

        assert "見張り台でノアと合流し" in text
        assert "崩れた坑道の先を確かめる" not in text
        assert "未解決" not in text

    def test_the_oldest_ten_turns_still_go_to_the_episode_writing(self) -> None:
        """既定の 20 ターンで畳むと、古い 10 ターン分は、これまでどおり書き起こしの聞き手にも渡る。"""
        received: list[list[str]] = []
        memory = SummarizingShortTermMemory(
            summary_service=ShortTermMemorySummaryService(_Port()),
            on_compacted=lambda pid, entries: received.append([entry.payload.output.prose for entry in entries]),
        )

        _run_turns(memory, 20)

        assert received == [[f"turn-{turn}" for turn in range(10)]]


class TestTheBackstoryInstruction:
    """いきさつを作る指示が、言われた予定と実際にしたことを分けて書かせることを保証する。"""

    def test_instruction_separates_what_was_said_from_what_was_done(self) -> None:
        """要約の LLM に送る指示に、言われた予定と実際にしたことを分けて書く旨と、言われた約束を一覧にせず流れの中に書く旨が入り、片付いていないことの欄は求めない。"""
        port = _Port()
        memory = SummarizingShortTermMemory(summary_service=ShortTermMemorySummaryService(port))

        _run_turns(memory, 20)

        (messages,) = port.messages
        system = messages[0]["content"]
        assert _SEPARATE_SAID_FROM_DONE in system
        assert "「誰が何をすると言った」として流れの中に書く" in system
        assert '"unresolved"' not in system


class TestTheBackstoryHeading:
    """いきさつがプロンプトに【ここまでのいきさつ】の見出しで出ることを保証する。"""

    def test_backstory_is_shown_under_its_own_heading(self) -> None:
        """いきさつの文があると【ここまでのいきさつ】の見出しで出て、【最近の流れ】の見出しは出ない。"""
        text = SectionBasedContextFormatStrategy().format(
            current_state_text="現在地: 見張り台",
            recent_events_text="- 直近の出来事",
            mid_summary_text="[最新] 北の坑道を調べた",
        )

        assert "【ここまでのいきさつ】\n[最新] 北の坑道を調べた" in text
        assert "【最近の流れ】" not in text

    def test_empty_backstory_hides_the_heading(self) -> None:
        """いきさつが空のとき、【ここまでのいきさつ】は見出しごと出ない。"""
        text = SectionBasedContextFormatStrategy().format(
            current_state_text="現在地: 見張り台",
            recent_events_text="- 直近の出来事",
            mid_summary_text="",
        )

        assert "【ここまでのいきさつ】" not in text


class TestOldSnapshotsWithUnresolved:
    """片付いていないこと (unresolved) を持つ古い snapshot を読み込んでも落ちず、その欄が捨てられることを保証する。"""

    def test_old_unresolved_is_dropped_and_the_backstory_is_restored(self) -> None:
        """古い snapshot の要約に unresolved があっても読み込め、流れと気分は戻り、書き出しには unresolved を持たない。"""
        src = SummarizingShortTermMemory(summary_service=ShortTermMemorySummaryService(_Port()))
        _run_turns(src, 20)
        captured = ShortTermMemorySubsystemCodec().capture(SimpleNamespace(_short_term_memory=src))
        old = dict(captured)
        old["mid_summaries"] = [
            {
                **group,
                "summaries": [
                    {**summary, "unresolved": ["崩れた坑道の先を確かめる"]} for summary in group["summaries"]
                ],
            }
            for group in captured["mid_summaries"]
        ]
        dst = SummarizingShortTermMemory()

        ShortTermMemorySubsystemCodec().restore(SimpleNamespace(_short_term_memory=dst), old)

        (restored,) = dst._mid_generations(_PID.value)
        assert restored.compressed_activity == "見張り台でノアと合流し、北の坑道を調べた"
        assert restored.emotional_summary == "少し不安"
        assert not hasattr(restored, "unresolved")
        assert all("unresolved" not in summary for group in captured["mid_summaries"] for summary in group["summaries"])

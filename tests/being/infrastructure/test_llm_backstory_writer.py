from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.short_term_memory import Backstory, Perception
from ai_rpg_world.being.infrastructure.llm_backstory_writer import (
    FLOW_MAX_CHARS,
    MOOD_MAX_CHARS,
    NOTHING_HAPPENED_FLOW,
    SYSTEM_PROMPT,
    LlmBackstoryWriter,
)


def _seen(turn: int, body: str) -> Perception:
    return Perception(
        turn=turn,
        observation=Observation(
            body=body,
            route=SeenOrHeard(),
            time=ObservedTime(display="1日目 朝"),
            subject_is_self=False,
            subject_name=UNKNOWN,
            source=UNKNOWN,
            place=UNKNOWN,
            addressed_to_self=UNKNOWN,
        ),
    )


class _Completion:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[list[dict[str, str]]] = []

    def __call__(self, messages: list[dict[str, str]]) -> Any:
        self.calls.append(messages)
        return self.response


def _write(
    writer: LlmBackstoryWriter,
    *,
    experiences: tuple[Perception, ...] = (_seen(1, "鐘が鳴った"), _seen(2, "扉が開いた")),
    previous: Backstory | None = None,
) -> Backstory:
    return writer.write(
        self_name="エイダ", persona="慎重", experiences=experiences, previous=previous, until_turn=10, written_turn=20
    )


class TestLlmBackstoryWriter:
    """LlmBackstoryWriter が、外す出来事と前のいきさつから LLM に渡す文を組み、応答をいきさつにすることを保証する (design_decisions D1824-12)。"""

    def test_response_becomes_a_backstory_for_the_range(self) -> None:
        """応答の流れと気分が、まとめた範囲の終わり (10) と書いたターン (20) を持ついきさつになる。"""
        writer = LlmBackstoryWriter(
            _Completion({"compressed_activity": "鐘のあと扉が開いた", "emotional_summary": "落ち着かない"})
        )

        assert _write(writer) == Backstory(
            flow="鐘のあと扉が開いた", mood="落ち着かない", written_turn=20, until_turn=10
        )

    def test_messages_carry_the_system_prompt_person_previous_backstory_and_events_in_order(self) -> None:
        """LLM に渡す文は、指示の文面、自分の名前と性格、前のいきさつの流れと気分、出来事を渡した順の【直近の出来事】と同じ行で持つ。"""
        completion = _Completion({"compressed_activity": "流れ"})
        previous = Backstory(flow="坑道で鍵を探した", mood="焦り", written_turn=10, until_turn=0)

        _write(LlmBackstoryWriter(completion), previous=previous)

        ((system, user),) = completion.calls
        assert system == {"role": "system", "content": SYSTEM_PROMPT}
        content = user["content"]
        assert "あなた = エイダ" in content and "あなたの性格 = 慎重" in content
        assert "流れ: 坑道で鍵を探した" in content and "気分: 焦り" in content
        assert content.index("- [1日目 朝] 鐘が鳴った") < content.index("- [1日目 朝] 扉が開いた")

    def test_system_prompt_is_the_same_as_the_current_summary(self) -> None:
        """指示の文面は、今の短期記憶の【ここまでのいきさつ】の要約と同じ文字列である。今の要約を消すまで、2 つがずれないように見る。"""
        from ai_rpg_world.application.llm.services.short_term_memory_summary_service import _SYSTEM_PROMPT

        assert SYSTEM_PROMPT == _SYSTEM_PROMPT

    def test_long_flow_and_mood_are_cut(self) -> None:
        """流れは FLOW_MAX_CHARS 字、気分は MOOD_MAX_CHARS 字までに切る。気分が文字列でなければ空にする。"""
        writer = LlmBackstoryWriter(_Completion({"compressed_activity": "あ" * 400, "emotional_summary": "い" * 200}))
        backstory = _write(writer)
        assert (len(backstory.flow), len(backstory.mood)) == (FLOW_MAX_CHARS, MOOD_MAX_CHARS)

        no_mood = _write(LlmBackstoryWriter(_Completion({"compressed_activity": "流れ", "emotional_summary": 3})))
        assert no_mood.mood == ""

    @pytest.mark.parametrize(
        "response",
        [{"emotional_summary": "気分"}, {"compressed_activity": " "}, ["流れ"]],
        ids=["no-flow", "blank-flow", "not-object"],
    )
    def test_broken_response_is_rejected(self, response: Any) -> None:
        """流れが無い、空白だけ、JSON object でない応答は ValueError。短期記憶はいきさつを待ち続け、遅れたら知らせるので、書き直される。"""
        with pytest.raises(ValueError):
            _write(LlmBackstoryWriter(_Completion(response)))

    def test_range_without_experiences_carries_the_previous_backstory_without_calling(self) -> None:
        """まとめる出来事が無ければ LLM を呼ばず、前のいきさつの流れと気分を引き継ぐ。前のいきさつも無ければ、出来事が無かったと書く。"""
        completion = _Completion({"compressed_activity": "呼ばれないはず"})
        previous = Backstory(flow="坑道で鍵を探した", mood="焦り", written_turn=10, until_turn=0)

        carried = _write(LlmBackstoryWriter(completion), experiences=(), previous=previous)
        empty = _write(LlmBackstoryWriter(completion), experiences=())

        assert completion.calls == []
        assert (carried.flow, carried.mood, carried.until_turn) == ("坑道で鍵を探した", "焦り", 10)
        assert (empty.flow, empty.mood) == (NOTHING_HAPPENED_FLOW, "")

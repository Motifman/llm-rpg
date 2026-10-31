from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.backstory_writer import WrittenBackstory
from ai_rpg_world.being.domain.persona import Persona
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
    persona: Persona = Persona(name="エイダ"),
) -> WrittenBackstory:
    return writer.write(
        persona=persona,
        persona_text="慎重",
        experiences=experiences,
        previous=previous,
        until_turn=10,
        written_turn=20,
    )


class TestLlmBackstoryWriter:
    """LlmBackstoryWriter が、外す出来事と前のいきさつから LLM に渡す文を組み、応答をいきさつにすることを保証する (design_decisions D1824-12)。"""

    def test_response_becomes_a_backstory_for_the_range(self) -> None:
        """応答の流れと気分が、まとめた範囲の終わり (10) と書いたターン (20) を持ついきさつになる。"""
        writer = LlmBackstoryWriter(
            _Completion({"compressed_activity": "鐘のあと扉が開いた", "emotional_summary": "落ち着かない"})
        )

        assert _write(writer) == WrittenBackstory(
            backstory=Backstory(flow="鐘のあと扉が開いた", mood="落ち着かない", written_turn=20, until_turn=10),
            truncated={},
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

    def test_first_person_is_told_after_the_name(self) -> None:
        """一人称が決まっていれば、名前の次の行で一人称を伝える。"""
        completion = _Completion({"compressed_activity": "流れ"})

        _write(LlmBackstoryWriter(completion), persona=Persona(name="エイダ", first_person="わたし"))

        assert "あなた = エイダ\nあなたの一人称 = わたし\n" in completion.calls[0][1]["content"]

    def test_undecided_first_person_is_not_mentioned(self) -> None:
        """一人称が決まっていなければ (None)、一人称について何も書かない。"""
        completion = _Completion({"compressed_activity": "流れ"})

        _write(LlmBackstoryWriter(completion))

        assert "一人称" not in completion.calls[0][1]["content"]

    def test_system_prompt_tells_the_length_limits(self) -> None:
        """指示の文面は、流れ (FLOW_MAX_CHARS 字) と気分 (MOOD_MAX_CHARS 字) の文字数の上限を、定数の数字で伝える。超えると切れることも伝える。"""
        assert f"- ここまでのいきさつは {FLOW_MAX_CHARS} 字まで、いまの気分は {MOOD_MAX_CHARS} 字まで" in SYSTEM_PROMPT
        assert "- 超えた分は途中で切れるので、字数の中で文を終える" in SYSTEM_PROMPT
        assert f"ここまでのいきさつ (2-3 文、{FLOW_MAX_CHARS} 字まで、固有名詞使用)" in SYSTEM_PROMPT
        assert f"今の感情の中核 (1 文、{MOOD_MAX_CHARS} 字まで)" in SYSTEM_PROMPT

    def test_long_flow_and_mood_are_cut_and_reported(self) -> None:
        """流れは FLOW_MAX_CHARS 字、気分は MOOD_MAX_CHARS 字までに切り、切った項目と切る前の長さを truncated に残す。"""
        writer = LlmBackstoryWriter(_Completion({"compressed_activity": "あ" * 400, "emotional_summary": "い" * 200}))

        written = _write(writer)

        assert (len(written.backstory.flow), len(written.backstory.mood)) == (FLOW_MAX_CHARS, MOOD_MAX_CHARS)
        assert written.truncated == {"flow": 400, "mood": 200}

    def test_text_at_the_limit_is_not_reported_as_truncated(self) -> None:
        """ちょうど上限の長さの流れと気分は、切り詰めとして扱わない。上限より 1 字長ければ切り詰める。"""
        at_limit = _write(
            LlmBackstoryWriter(
                _Completion({"compressed_activity": "あ" * FLOW_MAX_CHARS, "emotional_summary": "い" * MOOD_MAX_CHARS})
            )
        )
        over = _write(LlmBackstoryWriter(_Completion({"compressed_activity": "あ" * (FLOW_MAX_CHARS + 1)})))

        assert (at_limit.truncated, over.truncated) == ({}, {"flow": FLOW_MAX_CHARS + 1})

    def test_mood_that_is_not_text_becomes_empty(self) -> None:
        """気分が文字列でなければ空にする。切り詰めとしては扱わない。"""
        written = _write(LlmBackstoryWriter(_Completion({"compressed_activity": "流れ", "emotional_summary": 3})))

        assert (written.backstory.mood, written.truncated) == ("", {})

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
        assert (carried.backstory.flow, carried.backstory.mood, carried.backstory.until_turn) == (
            "坑道で鍵を探した",
            "焦り",
            10,
        )
        assert (empty.backstory.flow, empty.backstory.mood, empty.truncated) == (NOTHING_HAPPENED_FLOW, "", {})

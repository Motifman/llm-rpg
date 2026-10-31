from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.being.domain.episode import EpisodeIndex
from ai_rpg_world.being.domain.episode_writer import EpisodeContent, EpisodeContents
from ai_rpg_world.being.infrastructure.llm_episode_writer import (
    MAX_EPISODES_PER_WRITING,
    SYSTEM_PROMPT,
    EpisodeWritingCompletion,
    LlmEpisodeWriter,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeWritingResponseException,
)

EVENTS = "- 深夜 0:01 [行動] 棚を調べた → 紙を見つけた。\n- 深夜 0:02 金庫が開いた。"


class _Completion(EpisodeWritingCompletion):
    def __init__(self, response: Any) -> None:
        self.response = response
        self.messages: list[list[dict[str, str]]] = []

    def complete_episode_writing_json(self, messages: list[dict[str, str]]) -> Any:
        self.messages.append(messages)
        return self.response


class _Sequence(EpisodeWritingCompletion):
    """呼ばれるたびに、渡した応答を順に返す。"""

    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.messages: list[list[dict[str, str]]] = []

    def complete_episode_writing_json(self, messages: list[dict[str, str]]) -> Any:
        self.messages.append(messages)
        return self.responses.pop(0)


class _Failing(EpisodeWritingCompletion):
    def __init__(self) -> None:
        self.calls = 0

    def complete_episode_writing_json(self, messages: list[dict[str, str]]) -> Any:
        self.calls += 1
        raise RuntimeError("api down")


def _item(
    about: str = "金庫を開けた", recall_when: str = "金庫の話が出たとき", body: str = "紙の番号で金庫が開いた。"
) -> dict[str, str]:
    return {"about": about, "recall_when": recall_when, "body": body}


def _write(completion: EpisodeWritingCompletion, **overrides: Any) -> EpisodeContents:
    fields: dict[str, Any] = {"self_name": "エイダ", "persona": "慎重な錠前師", "events_text": EVENTS}
    fields.update(overrides)
    return LlmEpisodeWriter(completion).write(**fields)


class TestLlmEpisodeWriterMessages:
    """LlmEpisodeWriter が書き起こしの LLM に渡すものを保証する。"""

    def test_user_message_carries_name_persona_and_events(self) -> None:
        """本人の名前・人物像・範囲の出来事を、書き起こしの指示とは別の user の文に入れる。"""
        completion = _Completion({"episodes": []})

        _write(completion)

        system, user = completion.messages[0]
        assert system["role"] == "system"
        assert user["role"] == "user"
        assert "あなた = エイダ" in user["content"]
        assert "あなたの人物像 = 慎重な錠前師" in user["content"]
        assert EVENTS in user["content"]

    def test_system_prompt_asks_for_one_scene_per_episode_and_to_choose_scenes(self) -> None:
        """書き起こしの指示は、1 件に 1 つの場面だけを書くことと、上限 (MAX_EPISODES_PER_WRITING 件) を超えるなら思い出す値打ちのある場面を選び、ほかは書かないことを伝える。流れは別に残ることも伝える。"""
        assert "1 件には 1 つの場面だけを書く" in SYSTEM_PROMPT
        assert (
            f"{MAX_EPISODES_PER_WRITING} 件を超えるときは、あとで思い出す値打ちのある場面を選び、ほかは書かない"
            in SYSTEM_PROMPT
        )
        assert "流れは別に残る" in SYSTEM_PROMPT

    def test_blank_persona_is_left_out(self) -> None:
        """人物像が空なら、人物像の行を出さない。"""
        completion = _Completion({"episodes": []})

        _write(completion, persona="  ")

        assert "人物像" not in completion.messages[0][1]["content"]

    def test_system_prompt_does_not_depend_on_the_input(self) -> None:
        """書き起こしの指示は入力によらず同じ文で、名前も出来事も入らない。"""
        first = _Completion({"episodes": []})
        second = _Completion({"episodes": []})

        _write(first)
        _write(second, self_name="カイ", events_text="- 雨が降った。")

        assert first.messages[0][0] == second.messages[0][0]
        assert "エイダ" not in first.messages[0][0]["content"]

    def test_blank_events_are_rejected_before_calling(self) -> None:
        """範囲の出来事が空なら、LLM を呼ばずに ValueError を投げる。"""
        completion = _Completion({"episodes": []})

        with pytest.raises(ValueError):
            _write(completion, events_text=" \n")

        assert completion.messages == []


class TestLlmEpisodeWriterContents:
    """LlmEpisodeWriter が応答の各項目を、目次と本文を持つ中身にすることを保証する。"""

    def test_each_item_becomes_a_content_in_order(self) -> None:
        """応答の各項目を、応答の順に、目次と本文を持つ中身にする。"""
        contents = _write(_Completion({"episodes": [_item(about="棚の紙"), _item(about="金庫が開いた")]}))

        assert contents == EpisodeContents(
            contents=(
                EpisodeContent(
                    index=EpisodeIndex(summary="棚の紙", recall_when="金庫の話が出たとき"),
                    body="紙の番号で金庫が開いた。",
                ),
                EpisodeContent(
                    index=EpisodeIndex(summary="金庫が開いた", recall_when="金庫の話が出たとき"),
                    body="紙の番号で金庫が開いた。",
                ),
            ),
            dropped_count=0,
        )

    def test_zero_episodes_is_no_content(self) -> None:
        """何も起きていないとして 0 件が返れば、中身は無い。"""
        assert _write(_Completion({"episodes": []})) == EpisodeContents(contents=(), dropped_count=0)

    def test_items_beyond_the_cap_are_dropped_and_counted(self) -> None:
        """上限 (3 件) を超えた項目は中身にせず、捨てた件数を残す。"""
        items = [_item(about=f"記憶{n}") for n in range(MAX_EPISODES_PER_WRITING + 2)]

        contents = _write(_Completion({"episodes": items}))

        assert MAX_EPISODES_PER_WRITING == 3
        assert ([d.index.summary for d in contents.contents], contents.dropped_count) == (
            ["記憶0", "記憶1", "記憶2"],
            2,
        )

    def test_surrounding_whitespace_is_stripped(self) -> None:
        """各文の前後の空白は落とす。"""
        (content,) = _write(_Completion({"episodes": [_item(about=" 棚の紙\n", body="\n紙があった。 ")]})).contents

        assert (content.index.summary, content.body) == ("棚の紙", "紙があった。")


class TestLlmEpisodeWriterTruncation:
    """LlmEpisodeWriter が上限を超えた文を切り詰め、切り詰めたことを中身に残すことを保証する。"""

    @pytest.mark.parametrize(
        ("field", "limit", "read"),
        [
            ("about", 40, lambda d: d.index.summary),
            ("recall_when", 40, lambda d: d.index.recall_when),
            ("body", 400, lambda d: d.body),
        ],
    )
    def test_over_limit_text_is_cut_to_the_limit(self, field: str, limit: int, read: Any) -> None:
        """上限を超えた文は上限の長さまで切り詰め、切り詰めた項目と元の長さを中身に残す。"""
        (content,) = _write(_Completion({"episodes": [_item(**{field: "あ" * (limit + 5)})]})).contents

        assert read(content) == "あ" * limit
        assert content.truncated == {field: limit + 5}

    def test_text_at_the_limit_is_not_reported_as_truncated(self) -> None:
        """ちょうど上限の長さの文は切り詰めとして扱わない。"""
        (content,) = _write(_Completion({"episodes": [_item(about="あ" * 40, body="い" * 400)]})).contents

        assert content.truncated == {}

    def test_text_one_over_the_limit_is_cut(self) -> None:
        """上限より 1 字長い文は、上限の長さまで切り詰めとして扱う。"""
        (content,) = _write(_Completion({"episodes": [_item(about="あ" * 41)]})).contents

        assert (content.index.summary, content.truncated) == ("あ" * 40, {"about": 41})


class TestLlmEpisodeWriterFailures:
    """LlmEpisodeWriter が呼び出しの失敗と崩れた応答で、中身を 1 件も返さないことを保証する。"""

    def test_completion_error_propagates(self) -> None:
        """LLM の呼び出しが例外を投げたら、そのまま伝える。"""
        with pytest.raises(RuntimeError):
            _write(_Failing())

    @pytest.mark.parametrize(
        "response",
        [
            None,
            [],
            {},
            {"episodes": "金庫"},
            {"episodes": ["金庫"]},
            {"episodes": [_item(), {"about": "金庫", "recall_when": "鍵"}]},
            {"episodes": [_item(), _item(body="  ")]},
            {"episodes": [_item(), _item(recall_when=3)]},  # type: ignore[arg-type]
        ],
    )
    def test_malformed_response_returns_no_content(self, response: Any) -> None:
        """応答の形が 2 回とも崩れていれば、正しい項目があっても 1 件も返さず EpisodeWritingResponseException を投げる。"""
        completion = _Completion(response)

        with pytest.raises(EpisodeWritingResponseException):
            _write(completion)

        assert len(completion.messages) == 2


class TestLlmEpisodeWriterRewrite:
    """LlmEpisodeWriter が、崩れた応答のときに同じ材料で 1 回だけ書き直させることを保証する (design_decisions D1626)。"""

    def test_broken_response_is_written_again_with_the_same_messages(self) -> None:
        """1 回目の応答が崩れていて 2 回目が整っていれば、2 回目の中身を返し、書き直した印を付ける。2 回とも同じ文を渡し、1 回目の正しい項目は拾わない。"""
        completion = _Sequence(
            {"episodes": [_item(about="拾わない"), _item(about=" ")]}, {"episodes": [_item(about="2 回目")]}
        )

        contents = _write(completion)

        assert ([c.index.summary for c in contents.contents], contents.rewritten) == (["2 回目"], True)
        assert len(completion.messages) == 2 and completion.messages[0] == completion.messages[1]

    def test_good_first_response_is_not_rewritten(self) -> None:
        """1 回目の応答が整っていれば、書き直さず、書き直した印も付けない。"""
        completion = _Sequence({"episodes": [_item()]})

        contents = _write(completion)

        assert (len(completion.messages), contents.rewritten) == (1, False)

    def test_second_broken_response_fails_with_both_reasons(self) -> None:
        """2 回目も崩れていれば、それ以上書き直さず、1 回目と 2 回目の理由を添えた EpisodeWritingResponseException を投げる。"""
        completion = _Sequence({"episodes": [_item(about=" ")]}, {"episodes": "金庫"})

        with pytest.raises(EpisodeWritingResponseException, match="about.*episodes list|episodes list.*about"):
            _write(completion)

        assert len(completion.messages) == 2

    def test_call_failure_is_not_rewritten(self) -> None:
        """LLM の呼び出しそのものが失敗したら、書き直さずに (呼び出しは 1 回だけで) そのまま伝える。"""
        completion = _Failing()

        with pytest.raises(RuntimeError):
            _write(completion)

        assert completion.calls == 1

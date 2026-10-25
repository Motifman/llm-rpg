from __future__ import annotations

from typing import Any

import pytest

from ai_rpg_world.being.domain.episode import EpisodeIndex
from ai_rpg_world.being.domain.episode_writer import EpisodeDraft, EpisodeDrafts
from ai_rpg_world.being.infrastructure.llm_episode_writer import (
    MAX_EPISODES_PER_WRITING,
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


class _Failing(EpisodeWritingCompletion):
    def complete_episode_writing_json(self, messages: list[dict[str, str]]) -> Any:
        raise RuntimeError("api down")


def _item(about: str = "金庫を開けた", recall_when: str = "金庫の話が出たとき", body: str = "紙の番号で金庫が開いた。") -> dict[str, str]:
    return {"about": about, "recall_when": recall_when, "body": body}


def _write(completion: EpisodeWritingCompletion, **overrides: Any) -> EpisodeDrafts:
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


class TestLlmEpisodeWriterDrafts:
    """LlmEpisodeWriter が応答の各項目を、目次と本文を持つ下書きにすることを保証する。"""

    def test_each_item_becomes_a_draft_in_order(self) -> None:
        """応答の各項目を、応答の順に、目次と本文を持つ下書きにする。"""
        drafts = _write(_Completion({"episodes": [_item(about="棚の紙"), _item(about="金庫が開いた")]}))

        assert drafts == EpisodeDrafts(
            drafts=(
                EpisodeDraft(index=EpisodeIndex(summary="棚の紙", recall_when="金庫の話が出たとき"), body="紙の番号で金庫が開いた。"),
                EpisodeDraft(index=EpisodeIndex(summary="金庫が開いた", recall_when="金庫の話が出たとき"), body="紙の番号で金庫が開いた。"),
            ),
            dropped_count=0,
        )

    def test_zero_episodes_is_no_draft(self) -> None:
        """何も起きていないとして 0 件が返れば、下書きは無い。"""
        assert _write(_Completion({"episodes": []})) == EpisodeDrafts(drafts=(), dropped_count=0)

    def test_items_beyond_the_cap_are_dropped_and_counted(self) -> None:
        """上限 (3 件) を超えた項目は下書きにせず、捨てた件数を残す。"""
        items = [_item(about=f"記憶{n}") for n in range(MAX_EPISODES_PER_WRITING + 2)]

        drafts = _write(_Completion({"episodes": items}))

        assert MAX_EPISODES_PER_WRITING == 3
        assert ([d.index.summary for d in drafts.drafts], drafts.dropped_count) == (["記憶0", "記憶1", "記憶2"], 2)

    def test_surrounding_whitespace_is_stripped(self) -> None:
        """各文の前後の空白は落とす。"""
        (draft,) = _write(_Completion({"episodes": [_item(about=" 棚の紙\n", body="\n紙があった。 ")]})).drafts

        assert (draft.index.summary, draft.body) == ("棚の紙", "紙があった。")


class TestLlmEpisodeWriterTruncation:
    """LlmEpisodeWriter が上限を超えた文を切り詰め、切り詰めたことを下書きに残すことを保証する。"""

    @pytest.mark.parametrize(
        ("field", "limit", "read"),
        [
            ("about", 40, lambda d: d.index.summary),
            ("recall_when", 40, lambda d: d.index.recall_when),
            ("body", 400, lambda d: d.body),
        ],
    )
    def test_over_limit_text_is_cut_to_the_limit(self, field: str, limit: int, read: Any) -> None:
        """上限を超えた文は上限の長さまで切り詰め、切り詰めた項目と元の長さを下書きに残す。"""
        (draft,) = _write(_Completion({"episodes": [_item(**{field: "あ" * (limit + 5)})]})).drafts

        assert read(draft) == "あ" * limit
        assert draft.truncated == {field: limit + 5}

    def test_text_at_the_limit_is_not_reported_as_truncated(self) -> None:
        """ちょうど上限の長さの文は切り詰めとして扱わない。"""
        (draft,) = _write(_Completion({"episodes": [_item(about="あ" * 40, body="い" * 400)]})).drafts

        assert draft.truncated == {}

    def test_text_one_over_the_limit_is_cut(self) -> None:
        """上限より 1 字長い文は、上限の長さまで切り詰めとして扱う。"""
        (draft,) = _write(_Completion({"episodes": [_item(about="あ" * 41)]})).drafts

        assert (draft.index.summary, draft.truncated) == ("あ" * 40, {"about": 41})


class TestLlmEpisodeWriterFailures:
    """LlmEpisodeWriter が呼び出しの失敗と崩れた応答で、下書きを 1 件も返さないことを保証する。"""

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
    def test_malformed_response_returns_no_draft(self, response: Any) -> None:
        """応答の形が崩れていれば、正しい項目があっても 1 件も返さず EpisodeWritingResponseException を投げる。"""
        with pytest.raises(EpisodeWritingResponseException):
            _write(_Completion(response))

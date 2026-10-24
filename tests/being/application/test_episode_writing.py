from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from ai_rpg_world.being.application.episode_writing import (
    MAX_EPISODES_PER_WRITING,
    EpisodeWriter,
    EpisodeWritingCompletion,
)
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import (
    InMemoryEpisodeRepository,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    EpisodeWritingResponseException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being_ada")
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


def _ids() -> Iterator[str]:
    n = 0
    while True:
        n += 1
        yield f"3f2a7b9c-1d2e-4f00-8a00-{n:012d}"


def _item(about: str = "金庫を開けた", recall_when: str = "金庫の話が出たとき", body: str = "紙の番号で金庫が開いた。") -> dict[str, str]:
    return {"about": about, "recall_when": recall_when, "body": body}


def _writer(completion: EpisodeWritingCompletion, repository: InMemoryEpisodeRepository | None = None) -> tuple[EpisodeWriter, InMemoryEpisodeRepository]:
    repository = repository if repository is not None else InMemoryEpisodeRepository()
    ids = _ids()
    return EpisodeWriter(completion, repository, new_episode_id=lambda: next(ids)), repository


def _write(writer: EpisodeWriter, **overrides: Any):
    fields: dict[str, Any] = {
        "being_id": ADA,
        "self_name": "エイダ",
        "persona": "慎重な錠前師",
        "events_text": EVENTS,
        "environment_name": "地下の金庫室",
        "written_turn": 12,
    }
    fields.update(overrides)
    return writer.write(**fields)


class TestEpisodeWriterMessages:
    """EpisodeWriter が書き起こしの LLM に渡すものを保証する。"""

    def test_user_message_carries_name_persona_and_events(self) -> None:
        """本人の名前・人物像・範囲の出来事を、書き起こしの指示とは別の user の文に入れる。"""
        completion = _Completion({"episodes": []})
        writer, _ = _writer(completion)

        _write(writer)

        system, user = completion.messages[0]
        assert system["role"] == "system"
        assert user["role"] == "user"
        assert "あなた = エイダ" in user["content"]
        assert "あなたの人物像 = 慎重な錠前師" in user["content"]
        assert EVENTS in user["content"]

    def test_environment_name_is_not_shown_to_the_llm(self) -> None:
        """環境の名前は保存するためだけのもので、LLM に渡す文には入れない。"""
        completion = _Completion({"episodes": []})
        writer, _ = _writer(completion)

        _write(writer, environment_name="地下の金庫室")

        assert all("地下の金庫室" not in m["content"] for m in completion.messages[0])

    def test_blank_persona_is_left_out(self) -> None:
        """人物像が空なら、人物像の行を出さない。"""
        completion = _Completion({"episodes": []})
        writer, _ = _writer(completion)

        _write(writer, persona="  ")

        assert "人物像" not in completion.messages[0][1]["content"]

    def test_system_prompt_does_not_depend_on_the_input(self) -> None:
        """書き起こしの指示は入力によらず同じ文で、名前も出来事も入らない。"""
        first = _Completion({"episodes": []})
        second = _Completion({"episodes": []})

        _write(_writer(first)[0])
        _write(_writer(second)[0], self_name="カイ", events_text="- 雨が降った。")

        assert first.messages[0][0] == second.messages[0][0]
        assert "エイダ" not in first.messages[0][0]["content"]

    def test_blank_events_are_rejected_before_calling(self) -> None:
        """範囲の出来事が空なら、LLM を呼ばずに ValueError を投げる。"""
        completion = _Completion({"episodes": []})
        writer, _ = _writer(completion)

        with pytest.raises(ValueError):
            _write(writer, events_text=" \n")

        assert completion.messages == []


class TestEpisodeWriterSaving:
    """EpisodeWriter が応答から作ったエピソードを、Being の記録に足すことを保証する。"""

    def test_each_item_becomes_an_episode_in_order(self) -> None:
        """応答の各項目を、目次と本文を持つエピソードとして、応答の順に保存する。"""
        writer, repository = _writer(_Completion({"episodes": [_item(about="棚の紙"), _item(about="金庫が開いた")]}))

        result = _write(writer)

        saved = repository.list_by_being(ADA)
        assert [e.index.summary for e in saved] == ["棚の紙", "金庫が開いた"]
        assert [w.episode.episode_id for w in result.written] == [e.episode_id for e in saved]
        assert saved[0].index == EpisodeIndex(summary="棚の紙", recall_when="金庫の話が出たとき")
        assert saved[0].body == "紙の番号で金庫が開いた。"

    def test_episode_keeps_environment_name_and_written_turn(self) -> None:
        """エピソードは、渡された環境の名前と書いた時 (Being の記憶のターン数) を持つ。"""
        writer, repository = _writer(_Completion({"episodes": [_item()]}))

        _write(writer, environment_name="港町", written_turn=40)

        (episode,) = repository.list_by_being(ADA)
        assert episode.environment_name == "港町"
        assert episode.written_turn == 40

    def test_zero_episodes_saves_nothing(self) -> None:
        """何も起きていないとして 0 件が返れば、何も保存しない。"""
        writer, repository = _writer(_Completion({"episodes": []}))

        result = _write(writer)

        assert result.written == ()
        assert repository.list_by_being(ADA) == ()

    def test_handles_already_used_by_the_being_are_avoided(self) -> None:
        """その Being がもう使っている呼び名と重なる ID なら、新しい側の呼び名を伸ばす。"""
        repository = InMemoryEpisodeRepository()
        existing = Episode.write(
            episode_id="3f2a7b9c-0000-4f00-8a00-000000000099",
            environment_name="港町",
            written_turn=1,
            index=EpisodeIndex(summary="前の記憶", recall_when="前の話のとき"),
            body="前のこと。",
        )
        repository.add(ADA, existing)
        writer, _ = _writer(_Completion({"episodes": [_item(), _item()]}), repository)

        result = _write(writer)

        assert existing.handle == "ep_3f2a7b"
        assert [w.episode.handle for w in result.written] == ["ep_3f2a7b9", "ep_3f2a7b9c"]

    def test_items_beyond_the_cap_are_dropped_and_counted(self) -> None:
        """上限 (3 件) を超えた項目は保存せず、捨てた件数を結果に残す。"""
        items = [_item(about=f"記憶{n}") for n in range(MAX_EPISODES_PER_WRITING + 2)]
        writer, repository = _writer(_Completion({"episodes": items}))

        result = _write(writer)

        assert MAX_EPISODES_PER_WRITING == 3
        assert [e.index.summary for e in repository.list_by_being(ADA)] == ["記憶0", "記憶1", "記憶2"]
        assert result.dropped_count == 2

    def test_surrounding_whitespace_is_stripped(self) -> None:
        """各文の前後の空白は落として保存する。"""
        writer, repository = _writer(_Completion({"episodes": [_item(about=" 棚の紙\n", body="\n紙があった。 ")]}))

        _write(writer)

        (episode,) = repository.list_by_being(ADA)
        assert episode.index.summary == "棚の紙"
        assert episode.body == "紙があった。"


class TestEpisodeWriterTruncation:
    """EpisodeWriter が上限を超えた文を切り詰めて保存し、切り詰めたことを結果に残すことを保証する。"""

    @pytest.mark.parametrize(
        ("field", "limit", "read"),
        [
            ("about", 40, lambda e: e.index.summary),
            ("recall_when", 40, lambda e: e.index.recall_when),
            ("body", 400, lambda e: e.body),
        ],
    )
    def test_over_limit_text_is_cut_to_the_limit(self, field: str, limit: int, read: Any) -> None:
        """上限を超えた文は上限の長さまで切り詰めて保存し、切り詰めた項目と元の長さを結果に残す。"""
        writer, repository = _writer(_Completion({"episodes": [_item(**{field: "あ" * (limit + 5)})]}))

        result = _write(writer)

        (episode,) = repository.list_by_being(ADA)
        assert read(episode) == "あ" * limit
        assert result.written[0].truncated == {field: limit + 5}

    def test_text_at_the_limit_is_not_reported_as_truncated(self) -> None:
        """ちょうど上限の長さの文は切り詰めとして扱わない。"""
        writer, _ = _writer(_Completion({"episodes": [_item(about="あ" * 40, body="い" * 400)]}))

        result = _write(writer)

        assert result.written[0].truncated == {}


class TestEpisodeWriterFailures:
    """EpisodeWriter が呼び出しの失敗と崩れた応答で、エピソードを 1 件も作らないことを保証する。"""

    def test_completion_error_propagates_and_saves_nothing(self) -> None:
        """LLM の呼び出しが例外を投げたら、そのまま伝え、何も保存しない。"""
        writer, repository = _writer(_Failing())

        with pytest.raises(RuntimeError):
            _write(writer)

        assert repository.list_by_being(ADA) == ()

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
    def test_malformed_response_saves_nothing(self, response: Any) -> None:
        """応答の形が崩れていれば、正しい項目があっても 1 件も保存せず EpisodeWritingResponseException を投げる。"""
        writer, repository = _writer(_Completion(response))

        with pytest.raises(EpisodeWritingResponseException):
            _write(writer)

        assert repository.list_by_being(ADA) == ()

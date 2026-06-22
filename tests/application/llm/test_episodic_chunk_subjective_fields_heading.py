"""EpisodicChunkSubjectiveFieldsService が heading フィールドを LLM に
要求し、出力を episode に書き込み、欠落・失敗時にも壊れないことを保証する。

heading は afterglow index で使う 1 行見出し。新規 LLM コールを増やさず、
既存の interpreted / recall_text と同じ pass でついでに書かせる方針のため、
- system prompt が heading キーを要求していること
- LLM 出力に heading があれば episode.heading に乗ること
- LLM 出力に heading が無くても処理が止まらず heading=None になること
- LLM 出力の heading が長すぎても切り詰めて受けること
- LLM コール自体が失敗しても heading=None で完走すること
の 5 観点をここで押さえる。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.llm.contracts.chunk_encoding import build_chunk_encoding_input
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    EpisodicChunkSubjectiveFieldsService,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _StubSubjectivePort(IEpisodicChunkSubjectiveCompletionPort):
    """LLM 呼び出しを差し替えて、出力を固定値に / 例外に切り替えるためのスタブ。

    既存テスト (test_episodic_chunk_subjective_fields.py) と同じ形で、
    last_messages を保持して system prompt の assert に使えるようにする。
    """

    def __init__(self, outcome: dict[str, Any] | BaseException) -> None:
        self._outcome = outcome
        self.last_messages: list[dict[str, Any]] | None = None

    def complete_episode_subjective_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.last_messages = list(messages)
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome


def _make_encoding() -> Any:
    """heading の検証だけが目的なので、最小構成の chunk を組む。"""
    t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    act = ActionResultEntry(
        occurred_at=t,
        action_summary="待機した",
        result_summary="ok",
        tool_name="world_no_op",
        success=True,
    )
    return build_chunk_encoding_input(PlayerId(1), (), (act,))


class TestSystemPromptIncludesHeading:
    """LLM への指示に heading キーが含まれているかを保証する。

    afterglow index は LLM が書いた heading が無いと「ぼんやり覚えてる」を
    表現できないため、prompt 側でこれを必ず要求する。応答形式の例にも
    heading キーが入っている必要がある。
    """

    def test_system_prompt_lists_heading_as_required_key(self) -> None:
        """system プロンプトの出力 schema の説明に heading キーが含まれる。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {"interpreted": "x", "recall_text": "y", "heading": "h"}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port)
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        assert port.last_messages is not None
        sys_content = next(
            (m["content"] for m in port.last_messages if m.get("role") == "system"),
            "",
        )
        assert "heading" in sys_content


class TestHeadingMergeFromLlmOutput:
    """LLM 出力の heading が merge 後の episode に乗ることを保証する。"""

    def test_llm_heading_is_written_to_episode(self) -> None:
        """LLM が「司書の手記を読んだ」のような見出しを返した場合、
        merge 結果の episode.heading にその文字列がそのまま入る。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {
                "interpreted": "意味付け",
                "recall_text": "想起テキスト",
                "heading": "司書の手記を読んだ — 水の断片語",
            }
        )
        svc = EpisodicChunkSubjectiveFieldsService(port)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.heading == "司書の手記を読んだ — 水の断片語"

    def test_missing_heading_key_leaves_heading_as_none(self) -> None:
        """LLM が heading キーを返さない場合、episode.heading は None になり、
        既存の interpreted / recall_text の処理は止まらない。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r"}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.heading is None
        assert merged.interpreted == "i"
        assert merged.recall_text == "r"

    def test_long_heading_is_truncated(self) -> None:
        """LLM が指示を無視して 30 文字を超える heading を返した場合、
        prompt 表示を太らせず afterglow の視認性を保つため 30 文字に
        切り詰め、末尾に「…」を付けて切れたことを示す。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        long_text = "あ" * 50
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "heading": long_text}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.heading is not None
        assert len(merged.heading) == 30
        assert merged.heading.endswith("…")

    def test_blank_heading_string_becomes_none(self) -> None:
        """LLM が「分からない」のつもりで空文字や空白だけを返した場合、
        SubjectiveEpisode が ValueError を投げないよう、service 層で None に
        正規化してから渡す。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "heading": "   "}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.heading is None

    def test_llm_api_failure_results_in_heading_none(self) -> None:
        """LLM 呼び出し自体が LlmApiCallException で失敗しても、merge は
        既存どおりテンプレ fallback で完走する。heading は LLM 値が必須
        なので fallback では None になる。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            LlmApiCallException("down", error_code="LLM_API_CALL_FAILED")
        )
        svc = EpisodicChunkSubjectiveFieldsService(port)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.heading is None
        # interpreted / recall_text は既存のテンプレ fallback が効くので
        # 非 None のまま (= heading の追加で既存挙動が壊れていない確認)
        assert merged.interpreted is not None
        assert merged.recall_text is not None

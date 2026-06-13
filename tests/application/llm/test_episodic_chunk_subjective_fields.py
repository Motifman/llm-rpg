"""EpisodicChunkSubjectiveFieldsService のマージとフォールバックの検証。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.llm.contracts.chunk_encoding import build_chunk_encoding_input
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import ChunkEpisodeDraftBuilder
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    EpisodicChunkSubjectiveFieldsService,
    compute_template_interpreted,
    compute_template_recall,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _StubSubjectivePort(IEpisodicChunkSubjectiveCompletionPort):
    def __init__(self, outcome: dict[str, Any] | BaseException) -> None:
        self._outcome = outcome
        # 直近の呼び出しで受け取った messages を捕捉してテスト assert に使う
        self.last_messages: list[dict[str, Any]] | None = None

    def complete_episode_subjective_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        self.last_messages = list(messages)
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome


class TestEpisodicChunkSubjectiveFieldsService:
    """LLM が返す interpreted / recall_text のみ草案へ反映され、ルール由来フィールドが不変であること。"""

    def _minimal_encoding(self) -> Any:
        t = datetime(2026, 5, 4, 3, 0, tzinfo=timezone.utc)
        act = ActionResultEntry(
            occurred_at=t,
            action_summary="noop を実行しました。",
            result_summary="何もしませんでした。",
            tool_name="world_no_op",
            success=True,
        )
        return build_chunk_encoding_input(PlayerId(9), (), (act,))

    def test_merge_preserves_observed_and_cues(self) -> None:
        """successful JSON は interpreted / recall のみ更新し observed・cues 等を保持する。"""
        enc = self._minimal_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        svc = EpisodicChunkSubjectiveFieldsService(
            _StubSubjectivePort({"interpreted": "意味付け。", "recall_text": "短い想起。"}),
        )
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="寡黙。", encoding_input=enc
        )
        assert merged.observed == draft.observed
        assert merged.cues == draft.cues
        assert merged.who == draft.who
        assert merged.what == draft.what
        assert merged.outcome == draft.outcome
        assert merged.interpreted == "意味付け。"
        assert merged.recall_text == "短い想起。"

    def test_llm_api_failure_falls_back_to_template(self) -> None:
        """LlmApiCallException はテンプレへ落ち、それでも observed・cues は不変。"""
        enc = self._minimal_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        svc = EpisodicChunkSubjectiveFieldsService(
            _StubSubjectivePort(LlmApiCallException("down", error_code="LLM_API_CALL_FAILED")),
        )
        merged = svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)
        assert merged.observed == draft.observed
        assert merged.cues == draft.cues
        assert merged.interpreted is not None
        assert merged.recall_text is not None
        assert merged.interpreted == draft.what
        first_line = next(
            (ln.strip().lstrip("-").strip() for ln in draft.observed.splitlines() if ln.strip()),
            draft.what,
        )
        assert merged.recall_text == first_line

    def test_non_object_json_uses_template(self) -> None:
        """非 dict 応答でもテンプレへ落ちルール側は不変。"""
        enc = self._minimal_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        svc = EpisodicChunkSubjectiveFieldsService(_StubSubjectivePort(["not", "object"]))
        merged = svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)
        assert merged.observed == draft.observed
        assert merged.cues == draft.cues
        assert merged.interpreted == draft.what

    def test_partial_llm_fields_merge_with_template_for_missing(self) -> None:
        """片方だけ返った場合、欠損側はテンプレで補う。"""
        enc = self._minimal_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        svc = EpisodicChunkSubjectiveFieldsService(
            _StubSubjectivePort({"interpreted": "LLM のみ", "recall_text": ""}),
        )
        merged = svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)
        assert merged.interpreted == "LLM のみ"
        first_line = next(
            (ln.strip().lstrip("-").strip() for ln in draft.observed.splitlines() if ln.strip()),
            draft.what,
        )
        assert merged.recall_text == first_line


class TestSystemPromptPastTense:
    """system プロンプトに過去形を強制する規則が入っていることを検証。

    第21回実験 (Issue #311) で recall_text に「〜しなきゃならない」のような
    現在形・意志形が混入し、思い出として読みづらい例が観測された。これを
    プロンプト側で抑制するための後退防止 (regression) テスト。
    """

    def test_system_prompt_に_recall_text_の_過去形_ルールが_明示されている(self) -> None:
        enc = self._make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "x", "recall_text": "y"})
        svc = EpisodicChunkSubjectiveFieldsService(port)
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)
        assert port.last_messages is not None
        sys_content = next(
            (m["content"] for m in port.last_messages if m.get("role") == "system"),
            "",
        )
        # 過去形を強制する表現が含まれている
        assert "過去形" in sys_content
        # NG 例として現在形・意志形の代表が列挙されている
        assert "しなきゃならない" in sys_content
        assert "しよう" in sys_content
        # OK 例として過去形パターンが提示されている
        assert "〜だった" in sys_content

    def _make_encoding(self):
        t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
        act = ActionResultEntry(
            occurred_at=t,
            action_summary="待機した",
            result_summary="ok",
            tool_name="spot_graph_wait",
        )
        return build_chunk_encoding_input(PlayerId(1), (), (act,))


class TestComputeTemplateHelpers:
    """``compute_template_interpreted`` / ``compute_template_recall`` の純関数挙動。

    ``ChunkEpisodeDraftBuilder`` が draft 構築時に呼び出すため、``SubjectiveEpisode``
    を介さず生文字列で動くことが契約。
    """

    def test_interpreted_は_what_をそのまま返す(self) -> None:
        assert compute_template_interpreted("カイトが入口広間で待機した") == (
            "カイトが入口広間で待機した"
        )

    def test_interpreted_は_前後空白_を_trim(self) -> None:
        assert compute_template_interpreted("  hello  ") == "hello"

    def test_interpreted_は_長すぎる_what_を_省略記号_で切り詰める(self) -> None:
        long_what = "あ" * 800
        out = compute_template_interpreted(long_what)
        assert len(out) <= 700
        assert out.endswith("…")

    def test_recall_は_observed_の_最初の非空行_を_bullet_除去して返す(self) -> None:
        observed = "\n".join([
            "",
            "- [12:00] カイトが入口広間に立った",
            "- [12:01] 風の音が遠くから聞こえた",
        ])
        assert compute_template_recall(observed, what="x") == (
            "[12:00] カイトが入口広間に立った"
        )

    def test_recall_は_observed_が_空_なら_what_に_フォールバック(self) -> None:
        assert compute_template_recall("", what="待機した") == "待機した"
        assert compute_template_recall("   \n   ", what="待機した") == "待機した"

    def test_recall_は_長すぎる_行_を_省略記号_で切り詰める(self) -> None:
        long_line = "あ" * 800
        out = compute_template_recall(long_line, what="x")
        assert len(out) <= 700
        assert out.endswith("…")

"""EpisodicChunkSubjectiveFieldsService の salience 判定 (U6) を検証する。

U6 (予測誤差統一設計 §2 U6): SALIENCE_STRUCTURED_FAILURE_ENABLED flag に
対応する ``salience_enabled`` コンストラクタ引数の有無で

- flag OFF: system prompt に salience 節が **出ない** (= 導入前と byte 同一)、
  episode.salience は常に "low"
- flag ON: system prompt に salience 節が出て、LLM 出力の salience が
  episode.salience に反映される (不正値・欠損は "low" に倒す)

の 2 系統を切り替える。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.llm.contracts.chunk_encoding import build_chunk_encoding_input
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.services.chunk_episode_draft_builder import (
    ChunkEpisodeDraftBuilder,
)
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    _SYSTEM_EPISODE_SUBJECTIVE_JSON,
    EpisodicChunkSubjectiveFieldsService,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _StubSubjectivePort(IEpisodicChunkSubjectiveCompletionPort):
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
    t = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    act = ActionResultEntry(
        occurred_at=t,
        action_summary="待機した",
        result_summary="ok",
        tool_name="world_no_op",
        success=True,
    )
    return build_chunk_encoding_input(PlayerId(1), (), (act,))


class TestSalienceFlagOff:
    """salience_enabled=False (既定) のときの後方互換を保証する。"""

    def test_default_construction_keeps_system_prompt_byte_identical(self) -> None:
        """コンストラクタ引数省略時、system prompt は導入前の定数と
        byte 完全一致する (= 既定 prompt の後退防止)。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc = EpisodicChunkSubjectiveFieldsService(port)
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        sys_content = next(
            (m["content"] for m in port.last_messages if m.get("role") == "system"),
            "",
        )
        assert sys_content == _SYSTEM_EPISODE_SUBJECTIVE_JSON
        assert "salience" not in sys_content

    def test_episode_salience_is_always_low_when_disabled(self) -> None:
        """flag OFF のとき、LLM が誤って salience="high" を返しても無視され
        episode.salience は常に "low" のまま。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "salience": "high"}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, salience_enabled=False)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.salience == "low"


class TestSalienceFlagOn:
    """salience_enabled=True のときの salience 判定・反映を保証する。"""

    def test_system_prompt_includes_salience_instruction(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "salience": "low"}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, salience_enabled=True)
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        sys_content = next(
            (m["content"] for m in port.last_messages if m.get("role") == "system"),
            "",
        )
        assert "salience" in sys_content
        assert "high" in sys_content
        # 既存の指示 (prediction_error 等) は残ったまま追記されている
        assert "prediction_error" in sys_content

    def test_llm_high_salience_is_reflected(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "salience": "high"}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, salience_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.salience == "high"

    def test_invalid_salience_value_falls_back_to_low(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "salience": "medium"}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, salience_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.salience == "low"

    def test_missing_salience_key_falls_back_to_low(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc = EpisodicChunkSubjectiveFieldsService(port, salience_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.salience == "low"

    def test_non_string_salience_falls_back_to_low(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "salience": 1}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, salience_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.salience == "low"

    def test_llm_failure_falls_back_to_low(self) -> None:
        """LLM 呼び出し自体が失敗しても salience は "low" で完走する。"""
        from ai_rpg_world.application.llm.exceptions import LlmApiCallException

        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            LlmApiCallException("down", error_code="LLM_API_CALL_FAILED")
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, salience_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.salience == "low"

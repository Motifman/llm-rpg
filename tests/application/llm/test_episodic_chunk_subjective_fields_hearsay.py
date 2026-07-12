"""EpisodicChunkSubjectiveFieldsService の heard_claims 抽出 (P9 伝聞) を検証する。

HEARSAY_ENABLED flag に対応する ``hearsay_enabled`` コンストラクタ引数の有無で:
- flag OFF: system prompt に heard_claims 節が出ない (= 導入前と byte 同一)、
  episode.heard_claims は常に空タプル
- flag ON: system prompt に heard_claims 節が出て、LLM が返した配列が
  ``HeardClaim`` として episode に載る (speaker 欠落・null は捨てる)
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
    _normalize_heard_claims,
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
        occurred_at=t, action_summary="待機した", result_summary="ok",
        tool_name="world_no_op", success=True,
    )
    return build_chunk_encoding_input(PlayerId(1), (), (act,))


def _sys(port) -> str:
    return next(
        (m["content"] for m in port.last_messages if m.get("role") == "system"), ""
    )


class TestNormalizeHeardClaims:
    """LLM 出力 heard_claims 配列の正規化 (null / 複数 / speaker 欠落は捨てる)。"""

    def test_null_becomes_empty(self) -> None:
        assert _normalize_heard_claims(None) == ()

    def test_non_list_becomes_empty(self) -> None:
        assert _normalize_heard_claims("x") == ()

    def test_multiple_valid_claims_parsed(self) -> None:
        out = _normalize_heard_claims(
            [
                {"speaker": "リオ", "claim": "岩礁海岸は山に通じていない"},
                {"speaker": "エイダ", "claim": "北の泉は安全だ"},
            ]
        )
        assert [c.speaker for c in out] == ["リオ", "エイダ"]
        assert out[1].claim == "北の泉は安全だ"

    def test_entries_missing_speaker_or_claim_are_dropped(self) -> None:
        """話者を特定できない主張は伝聞にしない (捨てる)。"""
        out = _normalize_heard_claims(
            [
                {"claim": "話者不明の主張"},
                {"speaker": "リオ"},
                {"speaker": "  ", "claim": "空白話者"},
                {"speaker": "カイ", "claim": "有効"},
            ]
        )
        assert len(out) == 1
        assert out[0].speaker == "カイ"


class TestHearsayFlagOff:
    def test_system_prompt_byte_identical_when_disabled(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc = EpisodicChunkSubjectiveFieldsService(port)
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)
        assert _sys(port) == _SYSTEM_EPISODE_SUBJECTIVE_JSON
        assert "heard_claims" not in _sys(port)

    def test_heard_claims_ignored_when_disabled(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {
                "interpreted": "i", "recall_text": "r",
                "heard_claims": [{"speaker": "リオ", "claim": "何か"}],
            }
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, hearsay_enabled=False)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.heard_claims == ()


class TestHearsayFlagOn:
    def test_system_prompt_declares_heard_claims_key(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc = EpisodicChunkSubjectiveFieldsService(port, hearsay_enabled=True)
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)
        assert "heard_claims" in _sys(port)

    def test_claims_land_on_episode(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {
                "interpreted": "i", "recall_text": "r",
                "heard_claims": [
                    {"speaker": "リオ", "claim": "岩礁海岸は山に通じていない"}
                ],
            }
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, hearsay_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert len(merged.heard_claims) == 1
        assert merged.heard_claims[0].speaker == "リオ"
        assert merged.heard_claims[0].claim == "岩礁海岸は山に通じていない"

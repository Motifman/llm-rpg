"""EpisodicChunkSubjectiveFieldsService の heard_claims 抽出 (P9 伝聞) を検証する。

HEARSAY_ENABLED flag に対応する ``hearsay_enabled`` コンストラクタ引数の有無で:
- flag OFF: system prompt に heard_claims 節が出ない (= 導入前と byte 同一)、
  episode.heard_claims は常に空タプル
- flag ON: system prompt に heard_claims 節が出て、LLM が返した配列が
  ``HeardClaim`` として episode に載る (speaker 欠落・null は捨てる)

加えて次の入力衛生 (横断レビュー指摘) を検証する:
- H-2 (自己言及ループ): ``actor_name`` と speaker が一致する claim を弾く
- M-2 (暴走ガード): 1 chunk あたり claim 最大3件 + 各 claim の文字数上限
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

    def test_placeholder_speakers_are_dropped(self) -> None:
        """『不明』『誰か』等のプレースホルダ話者は捨てる (誰から来たか不明な

        情報を台帳に残さない。プロンプト無視への決定論的な最後の砦)。"""
        out = _normalize_heard_claims(
            [
                {"speaker": "不明", "claim": "水場は東にある"},
                {"speaker": "誰か", "claim": "北は危ない"},
                {"speaker": "Unknown", "claim": "x"},
                {"speaker": "リオ", "claim": "有効な伝聞"},
            ]
        )
        assert [c.speaker for c in out] == ["リオ"]


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


class TestNormalizeHeardClaimsSelfReference:
    """H-2 (自己言及ループ): actor_name と speaker が一致する claim を弾く。"""

    def test_claim_from_actor_itself_is_dropped(self) -> None:
        """speaker が actor_name と (前後空白除去 + casefold で) 一致する claim は

        「聞いた話」ではなく自分の発言なので捨てる。他の話者の claim は残る。
        """
        out = _normalize_heard_claims(
            [
                {"speaker": "カイト", "claim": "自分でそう言った"},
                {"speaker": "リオ", "claim": "北の泉は安全だ"},
            ],
            actor_name="カイト",
        )
        assert [c.speaker for c in out] == ["リオ"]

    def test_matching_is_case_and_whitespace_insensitive(self) -> None:
        """actor_name/speaker の前後空白や大小文字の違いは同一人物として判定する。"""
        out = _normalize_heard_claims(
            [{"speaker": "  Kaito  ", "claim": "自分の発言"}],
            actor_name="kaito",
        )
        assert out == ()

    def test_actor_name_none_does_not_filter_anyone(self) -> None:
        """actor_name 未配線 (None) のときは自己判定を行わず、全ての speaker を通す

        (provider 未配線で安全側に倒し過ぎて伝聞を全滅させない)。
        """
        out = _normalize_heard_claims(
            [{"speaker": "カイト", "claim": "何か言った"}],
            actor_name=None,
        )
        assert [c.speaker for c in out] == ["カイト"]

    def test_merge_llm_subjective_fields_filters_self_referential_claim(self) -> None:
        """service 経由でも actor_name と一致する speaker の claim が episode に

        載らないこと (coordinator から渡る actor_name が実際に効くことの保証)。
        """
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {
                "interpreted": "i", "recall_text": "r",
                "heard_claims": [
                    {"speaker": "カイト", "claim": "自分の発言"},
                    {"speaker": "リオ", "claim": "北の泉は安全だ"},
                ],
            }
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, hearsay_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc, actor_name="カイト"
        )
        assert [c.speaker for c in merged.heard_claims] == ["リオ"]


class TestNormalizeHeardClaimsRunawayGuard:
    """M-2 (heard_claims の暴走ガード): 1 chunk あたり claim 最大3件 + 文字数上限。"""

    def test_claims_beyond_limit_are_dropped_and_warned(self, caplog) -> None:
        """4件目以降は捨てられ、切り詰めが発生したことが WARNING ログに残る

        (黙って切り捨てない = 観測可能性を保つ)。
        """
        claims = [
            {"speaker": f"話者{i}", "claim": f"主張{i}"} for i in range(5)
        ]
        with caplog.at_level("WARNING"):
            out = _normalize_heard_claims(claims)
        assert len(out) == 3
        assert [c.speaker for c in out] == ["話者0", "話者1", "話者2"]
        assert any("capped" in r.message or "truncated" in r.message for r in caplog.records)

    def test_claim_text_beyond_char_limit_is_truncated_and_warned(self, caplog) -> None:
        """claim が上限文字数を超えると末尾を省略記号で切り詰め、WARNING ログが出る。"""
        long_claim = "あ" * 500
        with caplog.at_level("WARNING"):
            out = _normalize_heard_claims(
                [{"speaker": "リオ", "claim": long_claim}]
            )
        assert len(out) == 1
        assert len(out[0].claim) < len(long_claim)
        assert out[0].claim.endswith("…")
        assert any("truncated" in r.message or "capped" in r.message for r in caplog.records)

    def test_claims_within_limits_produce_no_warning(self, caplog) -> None:
        """件数・文字数とも上限内なら警告ログを出さない (過剰なノイズを避ける)。"""
        with caplog.at_level("WARNING"):
            out = _normalize_heard_claims(
                [{"speaker": "リオ", "claim": "短い主張"}]
            )
        assert len(out) == 1
        assert caplog.records == []

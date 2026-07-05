"""EpisodicChunkSubjectiveFieldsService の誤差ゲート付き解像度 (U8 部品2b) を検証する。

U8 (予測誤差統一設計 §2 U8 / 部品2 誤差ゲート付き符号化): recall_text の長さ指示を
salience 連動にする ``error_gated_encoding_enabled`` コンストラクタ引数の有無で

- flag OFF (既定): recall_text の長さ指示は U6 導入時の一律指示 (250〜450 字)
  のまま byte 一致
- flag ON かつ salience_enabled も True: recall_text の長さ指示が
  salience=high (250〜450字) / salience=low (80〜150字) の連動指示に置き換わる
- flag ON でも salience_enabled が False: salience 自体が存在しないため連動先が
  無く、長さ指示は変わらない (安全に縮退)

の 3 系統を切り替える。LLM は同一呼び出し内で salience を判定してから長さを
選ぶ設計のため、追加 LLM 呼び出しは発生しない (呼び出し回数はテストしない
= stub port の呼び出し方は既存 salience テストと同一)。
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


def _system_content(port: _StubSubjectivePort) -> str:
    assert port.last_messages is not None
    return next(
        (m["content"] for m in port.last_messages if m.get("role") == "system"),
        "",
    )


class TestErrorGatedEncodingFlagOff:
    """error_gated_encoding_enabled=False (既定) のときの後方互換を保証する。"""

    def test_default_construction_keeps_system_prompt_byte_identical(self) -> None:
        """コンストラクタ引数を一切渡さないとき、system prompt は導入前の定数と
        byte 完全一致する (U6/U7 と同じ後退防止テスト)。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc = EpisodicChunkSubjectiveFieldsService(port)
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        assert _system_content(port) == _SYSTEM_EPISODE_SUBJECTIVE_JSON

    def test_flag_off_with_salience_enabled_keeps_uniform_length_instruction(
        self,
    ) -> None:
        """salience_enabled=True でも error_gated_encoding_enabled=False なら
        recall_text の長さ指示は U6 導入時の一律指示 (250〜450 字) のまま。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "salience": "low"}
        )
        svc = EpisodicChunkSubjectiveFieldsService(
            port, salience_enabled=True, error_gated_encoding_enabled=False
        )
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        sys_content = _system_content(port)
        assert "250〜450 字程度で、当時の感情・見立て・手触りを含める。" in sys_content
        assert "80〜150字" not in sys_content


class TestErrorGatedEncodingFlagOn:
    """error_gated_encoding_enabled=True のときの長さ指示切り替えを保証する。"""

    def test_flag_on_with_salience_enabled_uses_salience_conditional_length(
        self,
    ) -> None:
        """flag ON かつ salience_enabled=True のとき、recall_text の長さ指示が
        salience=high/low の連動指示になる。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "salience": "high"}
        )
        svc = EpisodicChunkSubjectiveFieldsService(
            port, salience_enabled=True, error_gated_encoding_enabled=True
        )
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        sys_content = _system_content(port)
        assert "salience=high" in sys_content
        assert "250〜450字程度" in sys_content
        assert "salience=low" in sys_content
        assert "80〜150字程度" in sys_content
        # 元の一律長さ指示の文字列はもう含まれない (置換されている)
        assert "250〜450 字程度で、当時の感情・見立て・手触りを含める。" not in sys_content
        # 既存の指示 (prediction_error 等) は残ったまま
        assert "prediction_error" in sys_content

    def test_flag_on_without_salience_enabled_keeps_uniform_length_instruction(
        self,
    ) -> None:
        """salience_enabled=False のときは error_gated_encoding_enabled=True でも
        連動先の salience が存在しないため、長さ指示は変わらない (安全に縮退)。
        system prompt は U8 導入前 (= salience 節も無い既定 prompt) と byte 一致。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc = EpisodicChunkSubjectiveFieldsService(
            port, salience_enabled=False, error_gated_encoding_enabled=True
        )
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        assert _system_content(port) == _SYSTEM_EPISODE_SUBJECTIVE_JSON

    def test_constructor_type_error_for_non_bool(self) -> None:
        import pytest

        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        with pytest.raises(TypeError, match="error_gated_encoding_enabled"):
            EpisodicChunkSubjectiveFieldsService(
                port, error_gated_encoding_enabled="yes"  # type: ignore[arg-type]
            )

"""EpisodicChunkSubjectiveFieldsService の pending_prediction 抽出 (U10a) を検証する。

U10a (予測誤差統一設計 部品6・pending prediction): PENDING_PREDICTION_ENABLED
flag に対応する ``pending_prediction_enabled`` コンストラクタ引数の有無で

- flag OFF: system prompt に pending_prediction 節が **出ない**
  (= 導入前と byte 同一)、episode.pending_prediction_draft は常に None
- flag ON: system prompt に pending_prediction 節が出て、LLM が返した
  object が ``PendingPredictionDraft`` として episode に載る (不正・null は
  None に倒す)

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


_VALID_PENDING_JSON = {
    "text": "夕方に木の下でカイトとアイテムを交換する",
    "resolution_cues": ["spot:12", "player:カイト"],
    "tick_offset_from": 3,
    "tick_offset_to": 8,
}


class TestPendingPredictionFlagOff:
    """pending_prediction_enabled=False (既定) のときの後方互換を保証する。"""

    def test_default_construction_keeps_system_prompt_byte_identical(self) -> None:
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
        assert "pending_prediction" not in sys_content

    def test_pending_prediction_draft_is_always_none_when_disabled(self) -> None:
        """flag OFF のとき、LLM が誤って pending_prediction を返しても無視され

        episode.pending_prediction_draft は常に None のまま。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {
                "interpreted": "i",
                "recall_text": "r",
                "pending_prediction": dict(_VALID_PENDING_JSON),
            }
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, pending_prediction_enabled=False)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.pending_prediction_draft is None


class TestPendingPredictionFlagOn:
    """pending_prediction_enabled=True のときの抽出・反映を保証する。"""

    def test_system_prompt_includes_pending_prediction_instruction(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc = EpisodicChunkSubjectiveFieldsService(port, pending_prediction_enabled=True)
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        sys_content = next(
            (m["content"] for m in port.last_messages if m.get("role") == "system"),
            "",
        )
        assert "pending_prediction" in sys_content
        assert "resolution_cues" in sys_content
        # 既存の指示 (prediction_error 等) は残ったまま追記されている
        assert "prediction_error" in sys_content

    def test_valid_pending_prediction_is_parsed_into_draft(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {
                "interpreted": "i",
                "recall_text": "r",
                "pending_prediction": dict(_VALID_PENDING_JSON),
            }
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, pending_prediction_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        pending = merged.pending_prediction_draft
        assert pending is not None
        assert pending.text == "夕方に木の下でカイトとアイテムを交換する"
        assert pending.resolution_cues == ("spot:12", "player:カイト")
        assert pending.tick_offset_from == 3
        assert pending.tick_offset_to == 8

    def test_null_pending_prediction_is_none(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "pending_prediction": None}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, pending_prediction_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.pending_prediction_draft is None

    def test_missing_pending_prediction_key_is_none(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort({"interpreted": "i", "recall_text": "r"})
        svc = EpisodicChunkSubjectiveFieldsService(port, pending_prediction_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.pending_prediction_draft is None

    def test_missing_resolution_cues_falls_back_to_none(self) -> None:
        """相手・場所・時刻が特定できない (= resolution_cues 欠落) 出力は

        乱発防止のため None に倒す。"""
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        bad = dict(_VALID_PENDING_JSON)
        del bad["resolution_cues"]
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "pending_prediction": bad}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, pending_prediction_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.pending_prediction_draft is None

    def test_invalid_resolution_cue_format_falls_back_to_none(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        bad = dict(_VALID_PENDING_JSON)
        bad["resolution_cues"] = ["夕方"]
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "pending_prediction": bad}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, pending_prediction_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.pending_prediction_draft is None

    def test_tick_offset_range_reversed_falls_back_to_none(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        bad = dict(_VALID_PENDING_JSON)
        bad["tick_offset_from"] = 8
        bad["tick_offset_to"] = 3
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "pending_prediction": bad}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, pending_prediction_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.pending_prediction_draft is None

    def test_non_int_tick_offset_falls_back_to_none(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        bad = dict(_VALID_PENDING_JSON)
        bad["tick_offset_from"] = "soon"
        port = _StubSubjectivePort(
            {"interpreted": "i", "recall_text": "r", "pending_prediction": bad}
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, pending_prediction_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.pending_prediction_draft is None

    def test_llm_failure_falls_back_to_none(self) -> None:
        """LLM 呼び出し自体が失敗しても pending_prediction_draft は None で完走する。"""
        from ai_rpg_world.application.llm.exceptions import LlmApiCallException

        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort(
            LlmApiCallException("down", error_code="LLM_API_CALL_FAILED")
        )
        svc = EpisodicChunkSubjectiveFieldsService(port, pending_prediction_enabled=True)
        merged = svc.merge_llm_subjective_fields(
            draft, persona_text="", encoding_input=enc
        )
        assert merged.pending_prediction_draft is None


# tick offset クランプ (LLM が tick 尺度を誤って巨大値を返す問題への防御)
from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
    _PENDING_TICK_OFFSET_MAX,
    _PENDING_TICK_WINDOW_MIN,
    _normalize_pending_prediction,
)


class TestPendingTickOffsetClamp:
    """LLM の巨大な tick offset (「夕方」を分=1440 等) を妥当範囲へ丸める。"""

    def test_huge_tick_offset_to_is_clamped_to_max(self) -> None:
        """tick_offset_to=1440 のような巨大値は上限に丸め、窓が永遠に開いた

        ままになる (= tick 失効が効かない) 退化を防ぐ。"""
        draft = _normalize_pending_prediction(
            {
                "text": "夕方に木の下でカイトと会う",
                "resolution_cues": ["spot:12", "player:カイト"],
                "tick_offset_from": 0,
                "tick_offset_to": 1440,
            }
        )
        assert draft is not None
        assert draft.tick_offset_from == 0
        assert draft.tick_offset_to == _PENDING_TICK_OFFSET_MAX

    def test_zero_width_window_is_widened_to_min(self) -> None:
        """from==to の狭すぎる窓は「再浮上する前に過ぎ去る」ため最小幅を確保。"""
        draft = _normalize_pending_prediction(
            {
                "text": "すぐにカイトと会う",
                "resolution_cues": ["player:カイト"],
                "tick_offset_from": 0,
                "tick_offset_to": 0,
            }
        )
        assert draft is not None
        assert draft.tick_offset_to - draft.tick_offset_from == _PENDING_TICK_WINDOW_MIN

    def test_reasonable_offsets_are_left_unchanged(self) -> None:
        draft = _normalize_pending_prediction(
            {
                "text": "数tick後にカイトと会う",
                "resolution_cues": ["player:カイト"],
                "tick_offset_from": 5,
                "tick_offset_to": 12,
            }
        )
        assert draft is not None
        assert draft.tick_offset_from == 5
        assert draft.tick_offset_to == 12

    def test_both_offsets_above_max_are_clamped_and_window_kept(self) -> None:
        draft = _normalize_pending_prediction(
            {
                "text": "遠い未来にカイトと会う",
                "resolution_cues": ["player:カイト"],
                "tick_offset_from": 500,
                "tick_offset_to": 900,
            }
        )
        assert draft is not None
        # 両方上限に丸められた結果 from==to==MAX になるので、最小窓を確保する
        assert draft.tick_offset_from == _PENDING_TICK_OFFSET_MAX
        assert draft.tick_offset_to == _PENDING_TICK_OFFSET_MAX + _PENDING_TICK_WINDOW_MIN

    def test_reversed_range_still_dropped_after_clamp(self) -> None:
        """反転 (from>to) はクランプで補正せず従来どおり None に落とす

        (壊れた出力をもっともらしい約束に化けさせない)。"""
        draft = _normalize_pending_prediction(
            {
                "text": "壊れた約束",
                "resolution_cues": ["player:カイト"],
                "tick_offset_from": 20,
                "tick_offset_to": 5,
            }
        )
        assert draft is None

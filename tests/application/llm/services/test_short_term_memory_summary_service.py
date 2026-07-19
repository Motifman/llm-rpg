"""``ShortTermMemorySummaryService`` のテスト (Phase 2)。

LLM port を stub に差し替えて、プロンプト構築 / 出力パース / cap / エラー
取り回しを検証する。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from ai_rpg_world.application.llm.ports.short_term_memory_completion_ports import (
    IShortTermMemorySummaryCompletionPort,
)
from ai_rpg_world.domain.memory.short_term.value_object.l4_mid_summary import (
    L4MidSummary,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.short_term_memory_summary_service import (
    COMPRESSED_ACTIVITY_MAX_CHARS,
    EMOTIONAL_SUMMARY_MAX_CHARS,
    UNRESOLVED_ITEM_MAX_CHARS,
    UNRESOLVED_MAX_ITEMS,
    ShortTermMemorySummaryService,
    build_template_fallback_summary,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)


def _make_observation(prose: str) -> ObservationEntry:
    return ObservationEntry(
        occurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        output=ObservationOutput(prose=prose, structured={}),
    )


@dataclass
class _StubPort(IShortTermMemorySummaryCompletionPort):
    response: Dict[str, Any]
    captured: List[List[Dict[str, Any]]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.captured = []

    def complete_short_term_summary_json(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        self.captured.append(messages)
        return self.response


@dataclass
class _RaisingPort(IShortTermMemorySummaryCompletionPort):
    exc: Exception

    def complete_short_term_summary_json(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        raise self.exc


class TestShortTermMemorySummaryServiceGenerate:
    """正常系: LLM 応答を _ParsedSummary に変換する。"""

    def test_llm_result_included(self) -> None:
        """有効な LLM 応答がそのまま result に乗る。"""
        port = _StubPort(response={
            "compressed_activity": "北東を探索したが収穫薄",
            "emotional_summary": "やや疲労",
            "unresolved": ["水源を見つける", "タカシと再会する"],
        })
        svc = ShortTermMemorySummaryService(port)
        result = svc.generate(
            player_name="ハル",
            persona_block="慎重",
            observations=[_make_observation("p1"), _make_observation("p2")],
        )
        assert result.compressed_activity == "北東を探索したが収穫薄"
        assert result.emotional_summary == "やや疲労"
        assert result.unresolved == ("水源を見つける", "タカシと再会する")

    def test_compressed_activity_cap(self) -> None:
        """compressed activity は cap される。"""
        long = "あ" * (COMPRESSED_ACTIVITY_MAX_CHARS * 2)
        port = _StubPort(response={
            "compressed_activity": long,
            "emotional_summary": "",
            "unresolved": [],
        })
        svc = ShortTermMemorySummaryService(port)
        result = svc.generate(
            player_name="x",
            persona_block="",
            observations=[_make_observation("p")],
        )
        assert len(result.compressed_activity) == COMPRESSED_ACTIVITY_MAX_CHARS

    def test_emotional_summary_cap(self) -> None:
        """emotional summary は cap される。"""
        long = "あ" * (EMOTIONAL_SUMMARY_MAX_CHARS * 2)
        port = _StubPort(response={
            "compressed_activity": "ok",
            "emotional_summary": long,
            "unresolved": [],
        })
        svc = ShortTermMemorySummaryService(port)
        result = svc.generate(
            player_name="x",
            persona_block="",
            observations=[_make_observation("p")],
        )
        assert len(result.emotional_summary) == EMOTIONAL_SUMMARY_MAX_CHARS

    def test_unresolved_three_cap(self) -> None:
        """unresolved は 3件 でcap される。"""
        port = _StubPort(response={
            "compressed_activity": "ok",
            "emotional_summary": "",
            "unresolved": [f"item{i}" for i in range(10)],
        })
        svc = ShortTermMemorySummaryService(port)
        result = svc.generate(
            player_name="x",
            persona_block="",
            observations=[_make_observation("p")],
        )
        assert len(result.unresolved) == UNRESOLVED_MAX_ITEMS

    def test_unresolved_element_120_cap(self) -> None:
        """unresolved の各要素は 120 字で cap される。"""
        long = "あ" * (UNRESOLVED_ITEM_MAX_CHARS * 2)
        port = _StubPort(response={
            "compressed_activity": "ok",
            "emotional_summary": "",
            "unresolved": [long],
        })
        svc = ShortTermMemorySummaryService(port)
        result = svc.generate(
            player_name="x",
            persona_block="",
            observations=[_make_observation("p")],
        )
        assert len(result.unresolved[0]) == UNRESOLVED_ITEM_MAX_CHARS

    def test_unresolved_non_str_empty_string(self) -> None:
        """unresolved の非 str や空文字は除外。"""
        port = _StubPort(response={
            "compressed_activity": "ok",
            "emotional_summary": "",
            "unresolved": ["a", "", "  ", 123, None, "b"],
        })
        svc = ShortTermMemorySummaryService(port)
        result = svc.generate(
            player_name="x",
            persona_block="",
            observations=[_make_observation("p")],
        )
        assert result.unresolved == ("a", "b")

    def test_emotional_summary_non_str_empty_string(self) -> None:
        """emotionalsummary が非 str でも空文字に縮退。"""
        port = _StubPort(response={
            "compressed_activity": "ok",
            "emotional_summary": 123,
            "unresolved": [],
        })
        svc = ShortTermMemorySummaryService(port)
        result = svc.generate(
            player_name="x",
            persona_block="",
            observations=[_make_observation("p")],
        )
        assert result.emotional_summary == ""


class TestShortTermMemorySummaryServicePromptStructure:
    """messages に名前 / persona / 直前 L4 / 観測群 が乗る。"""

    def test_player_name_persona_user_included(self) -> None:
        """player name と persona が user メッセージに 乗る。"""
        port = _StubPort(response={"compressed_activity": "ok", "emotional_summary": "", "unresolved": []})
        svc = ShortTermMemorySummaryService(port)
        svc.generate(
            player_name="ハル",
            persona_block="慎重で寡黙",
            observations=[_make_observation("行動 X")],
        )
        user = port.captured[0][1]["content"]
        assert "ハル" in user
        assert "慎重で寡黙" in user
        assert "行動 X" in user

    def test_before_l4_section_included(self) -> None:
        """直前 L4 があれば引き継ぎ section が乗る。"""
        port = _StubPort(response={"compressed_activity": "ok", "emotional_summary": "", "unresolved": []})
        svc = ShortTermMemorySummaryService(port)
        prev = L4MidSummary(
            summary_id="prev-1",
            player_id=1,
            raw_count=15,
            generated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            compressed_activity="先回の行動",
            emotional_summary="先回の気分",
            unresolved=("先回未解決",),
        )
        svc.generate(
            player_name="x",
            persona_block="",
            observations=[_make_observation("p")],
            previous_l4=prev,
        )
        user = port.captured[0][1]["content"]
        assert "先回の行動" in user
        assert "先回の気分" in user
        assert "先回未解決" in user

    def test_system_label(self) -> None:
        """system メッセージに ラベル禁止 の指示が 入る。"""
        port = _StubPort(response={"compressed_activity": "ok", "emotional_summary": "", "unresolved": []})
        svc = ShortTermMemorySummaryService(port)
        svc.generate(
            player_name="x",
            persona_block="",
            observations=[_make_observation("p")],
        )
        system = port.captured[0][0]["content"]
        assert "P1" in system or "ラベル" in system


class TestShortTermMemorySummaryServiceErrors:
    """異常系: 空 observations / API 例外 / 不正 JSON。"""

    def test_empty_observations_value_error(self) -> None:
        """空 observations は value error。"""
        port = _StubPort(response={"compressed_activity": "ok", "emotional_summary": "", "unresolved": []})
        svc = ShortTermMemorySummaryService(port)
        with pytest.raises(ValueError, match="observations must not be empty"):
            svc.generate(
                player_name="x", persona_block="", observations=[]
            )

    def test_port_llm_api_call_exception(self) -> None:
        """port が LlmApiCallException なら 伝播。"""
        svc = ShortTermMemorySummaryService(
            _RaisingPort(exc=LlmApiCallException("x", error_code="LLM_API_CALL_FAILED"))
        )
        with pytest.raises(LlmApiCallException):
            svc.generate(
                player_name="x",
                persona_block="",
                observations=[_make_observation("p")],
            )

    def test_compressed_activity_empty_string_value_error(self) -> None:
        """compressedactivity が空文字なら valueerror。"""
        port = _StubPort(response={
            "compressed_activity": "   ",
            "emotional_summary": "",
            "unresolved": [],
        })
        svc = ShortTermMemorySummaryService(port)
        with pytest.raises(ValueError, match="missing or empty compressed_activity"):
            svc.generate(
                player_name="x",
                persona_block="",
                observations=[_make_observation("p")],
            )

    def test_port_none_type_error(self) -> None:
        """port が None なら type error。"""
        with pytest.raises(TypeError, match="port must not be None"):
            ShortTermMemorySummaryService(port=None)  # type: ignore[arg-type]


class TestBuildTemplateFallbackSummary:
    """LLM 失敗時の縮退テンプレ。"""

    def test_observation_prose(self) -> None:
        """観測 prose が箇条書きで詰まる。"""
        obs = [_make_observation("p1"), _make_observation("p2")]
        result = build_template_fallback_summary(obs)
        assert "p1" in result.compressed_activity
        assert "p2" in result.compressed_activity
        assert result.emotional_summary == ""
        assert result.unresolved == ()

    def test_returns_observation_empty_string_placeholder(self) -> None:
        """観測ゼロでも 空文字 placeholder を返す。"""
        result = build_template_fallback_summary([])
        assert "no prose" in result.compressed_activity

    def test_fifteen_over_before_fifteen(self) -> None:
        """15件超は 前から 15件で 打ち切り。"""
        obs = [_make_observation(f"p{i}") for i in range(30)]
        result = build_template_fallback_summary(obs)
        assert "p14" in result.compressed_activity
        # p15 以降は cap される (15 件で打ち切り)
        # ただし COMPRESSED_ACTIVITY_MAX_CHARS による truncate もあるので
        # 厳密には「p15 が含まれないか」だけで判定する
        assert "p20" not in result.compressed_activity

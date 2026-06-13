"""``ShortTermMemoryLongSummaryService`` のテスト (Phase 3)。

LLM port を stub に差し替えて、プロンプト構築 / 出力パース / cap / エラー
取り回し / template fallback を検証する。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from ai_rpg_world.application.llm.ports.short_term_memory_completion_ports import (
    IShortTermMemoryLongSummaryCompletionPort,
)
from ai_rpg_world.domain.memory.short_term.value_object.l4_mid_summary import (
    L4MidSummary,
)
from ai_rpg_world.domain.memory.short_term.value_object.l5_long_summary import (
    L5LongSummary,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.short_term_memory_long_summary_service import (
    SELF_IMAGE_MAX_CHARS,
    WORLD_VIEW_MAX_CHARS,
    ShortTermMemoryLongSummaryService,
    build_template_fallback_long_summary,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _make_l4(
    *,
    summary_id: str = "l4-1",
    compressed: str = "北東を探索",
    emotional: str = "やや疲労",
    unresolved: tuple = ("水源",),
) -> L4MidSummary:
    return L4MidSummary(
        summary_id=summary_id,
        player_id=1,
        raw_count=15,
        generated_at=_NOW,
        compressed_activity=compressed,
        emotional_summary=emotional,
        unresolved=unresolved,
    )


def _make_l5(
    *,
    self_image: str = "私は寡黙な漁師",
    world_view: str = "島は資源豊富だが熊が危険",
    generation_index: int = 1,
) -> L5LongSummary:
    return L5LongSummary(
        summary_id=f"l5-{generation_index}",
        player_id=1,
        generation_index=generation_index,
        generated_at=_NOW,
        self_image=self_image,
        world_view=world_view,
    )


@dataclass
class _StubPort(IShortTermMemoryLongSummaryCompletionPort):
    response: Dict[str, Any]
    captured: List[List[Dict[str, Any]]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.captured = []

    def complete_short_term_long_summary_json(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        self.captured.append(messages)
        return self.response


@dataclass
class _RaisingPort(IShortTermMemoryLongSummaryCompletionPort):
    exc: Exception

    def complete_short_term_long_summary_json(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        raise self.exc


class TestLongSummaryServiceGenerate:
    """正常系: LLM 応答を _ParsedLongSummary に変換する。"""

    def test_有効な_LLM_応答が_そのまま_result_に_乗る(self) -> None:
        port = _StubPort(response={
            "self_image": "私は流木集めで一族を支える寡黙な漁師",
            "world_view": "島は流木と魚で食料は確保できる",
        })
        svc = ShortTermMemoryLongSummaryService(port)
        result = svc.generate(
            player_name="ハル",
            persona_block="慎重で寡黙",
            previous_l5=_make_l5(),
            evicted_l4=_make_l4(),
        )
        assert result.self_image == "私は流木集めで一族を支える寡黙な漁師"
        assert result.world_view == "島は流木と魚で食料は確保できる"

    def test_self_image_は_cap_される(self) -> None:
        long = "あ" * (SELF_IMAGE_MAX_CHARS * 2)
        port = _StubPort(response={"self_image": long, "world_view": "ok"})
        svc = ShortTermMemoryLongSummaryService(port)
        result = svc.generate(
            player_name="x",
            persona_block="",
            previous_l5=None,
            evicted_l4=_make_l4(),
        )
        assert len(result.self_image) == SELF_IMAGE_MAX_CHARS

    def test_world_view_は_cap_される(self) -> None:
        long = "あ" * (WORLD_VIEW_MAX_CHARS * 2)
        port = _StubPort(response={"self_image": "ok", "world_view": long})
        svc = ShortTermMemoryLongSummaryService(port)
        result = svc.generate(
            player_name="x",
            persona_block="",
            previous_l5=None,
            evicted_l4=_make_l4(),
        )
        assert len(result.world_view) == WORLD_VIEW_MAX_CHARS

    def test_world_view_が_非str_でも_空文字に_縮退(self) -> None:
        port = _StubPort(response={"self_image": "ok", "world_view": 123})
        svc = ShortTermMemoryLongSummaryService(port)
        result = svc.generate(
            player_name="x",
            persona_block="",
            previous_l5=None,
            evicted_l4=_make_l4(),
        )
        assert result.world_view == ""


class TestLongSummaryServicePromptStructure:
    """messages に player_name / persona / previous_l5 / evicted_l4 が乗る。"""

    def test_player_name_と_persona_が_user_メッセージに_乗る(self) -> None:
        port = _StubPort(response={"self_image": "ok", "world_view": ""})
        svc = ShortTermMemoryLongSummaryService(port)
        svc.generate(
            player_name="ハル",
            persona_block="慎重で寡黙",
            previous_l5=None,
            evicted_l4=_make_l4(),
        )
        user = port.captured[0][1]["content"]
        assert "ハル" in user
        assert "慎重で寡黙" in user

    def test_previous_l5_が_あれば_user_メッセージに_乗る(self) -> None:
        port = _StubPort(response={"self_image": "ok", "world_view": ""})
        svc = ShortTermMemoryLongSummaryService(port)
        prev = _make_l5(self_image="先回の自己像", world_view="先回の世界観")
        svc.generate(
            player_name="x",
            persona_block="",
            previous_l5=prev,
            evicted_l4=_make_l4(),
        )
        user = port.captured[0][1]["content"]
        assert "先回の自己像" in user
        assert "先回の世界観" in user

    def test_previous_l5_が_None_なら_初期_メッセージが_出る(self) -> None:
        port = _StubPort(response={"self_image": "ok", "world_view": ""})
        svc = ShortTermMemoryLongSummaryService(port)
        svc.generate(
            player_name="x",
            persona_block="",
            previous_l5=None,
            evicted_l4=_make_l4(),
        )
        user = port.captured[0][1]["content"]
        assert "まだ自己像は形成されていない" in user

    def test_evicted_l4_が_user_メッセージに_乗る(self) -> None:
        port = _StubPort(response={"self_image": "ok", "world_view": ""})
        svc = ShortTermMemoryLongSummaryService(port)
        l4 = _make_l4(compressed="北を探索", emotional="不安", unresolved=("食料",))
        svc.generate(
            player_name="x",
            persona_block="",
            previous_l5=None,
            evicted_l4=l4,
        )
        user = port.captured[0][1]["content"]
        assert "北を探索" in user
        assert "不安" in user
        assert "食料" in user

    def test_system_メッセージに_persona_不変_の指示が_入る(self) -> None:
        port = _StubPort(response={"self_image": "ok", "world_view": ""})
        svc = ShortTermMemoryLongSummaryService(port)
        svc.generate(
            player_name="x",
            persona_block="",
            previous_l5=None,
            evicted_l4=_make_l4(),
        )
        system = port.captured[0][0]["content"]
        assert "persona" in system or "性格" in system

    def test_system_メッセージに_ラベル禁止_の指示が_入る(self) -> None:
        port = _StubPort(response={"self_image": "ok", "world_view": ""})
        svc = ShortTermMemoryLongSummaryService(port)
        svc.generate(
            player_name="x",
            persona_block="",
            previous_l5=None,
            evicted_l4=_make_l4(),
        )
        system = port.captured[0][0]["content"]
        assert "P1" in system or "ラベル" in system


class TestLongSummaryServiceErrors:
    """異常系: 空 evicted_l4 / API 例外 / 不正 JSON。"""

    def test_evicted_l4_が_None_なら_value_error(self) -> None:
        port = _StubPort(response={"self_image": "ok", "world_view": ""})
        svc = ShortTermMemoryLongSummaryService(port)
        with pytest.raises(ValueError, match="evicted_l4"):
            svc.generate(
                player_name="x",
                persona_block="",
                previous_l5=None,
                evicted_l4=None,  # type: ignore[arg-type]
            )

    def test_port_例外は_伝播(self) -> None:
        svc = ShortTermMemoryLongSummaryService(
            _RaisingPort(exc=LlmApiCallException("x", error_code="LLM_API_CALL_FAILED"))
        )
        with pytest.raises(LlmApiCallException):
            svc.generate(
                player_name="x",
                persona_block="",
                previous_l5=None,
                evicted_l4=_make_l4(),
            )

    def test_self_image_が_空文字なら_value_error(self) -> None:
        port = _StubPort(response={"self_image": "  ", "world_view": ""})
        svc = ShortTermMemoryLongSummaryService(port)
        with pytest.raises(ValueError, match="missing or empty self_image"):
            svc.generate(
                player_name="x",
                persona_block="",
                previous_l5=None,
                evicted_l4=_make_l4(),
            )

    def test_port_が_None_なら_type_error(self) -> None:
        with pytest.raises(TypeError, match="port must not be None"):
            ShortTermMemoryLongSummaryService(port=None)  # type: ignore[arg-type]


class TestBuildTemplateFallbackLongSummary:
    """LLM 失敗時の縮退テンプレ: previous_l5 があれば延命、無ければ placeholder。"""

    def test_previous_l5_があれば_そのまま_延命(self) -> None:
        prev = _make_l5(self_image="不変の自己像", world_view="不変の世界観")
        result = build_template_fallback_long_summary(
            previous_l5=prev,
            evicted_l4=_make_l4(),
        )
        assert result.self_image == "不変の自己像"
        assert result.world_view == "不変の世界観"

    def test_previous_l5_が_None_なら_placeholder(self) -> None:
        result = build_template_fallback_long_summary(
            previous_l5=None,
            evicted_l4=_make_l4(compressed="行動 X"),
        )
        assert "自己像未生成" in result.self_image
        assert "行動 X" in result.self_image
        assert "世界観未生成" in result.world_view

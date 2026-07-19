"""``SemanticGistService`` のテスト (Phase 1b)。

エピソードクラスタを「学び・教訓」1 件に抽象化する LLM 利用サービス。
LLM port は stub に差し替えて、プロンプト構築 / 出力パース / cap / エラー
取り回しを検証する。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import pytest

from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import EpisodeLocation
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.application.llm.ports.semantic_gist_completion_port import (
    ISemanticGistCompletionPort,
)
from ai_rpg_world.domain.memory.semantic.value_object.semantic_memory_entry import SemanticMemoryEntry
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.semantic_gist_service import (
    SemanticGistResult,
    SemanticGistService,
)


def _make_episode(
    *,
    episode_id: str = "ep-1",
    occurred_at_minute: int = 0,
    recall_text: str = "ある記憶",
    interpreted: str | None = None,
    prediction_error: str | None = None,
) -> SubjectiveEpisode:
    return SubjectiveEpisode(
        episode_id=episode_id,
        player_id=1,
        occurred_at=datetime(2026, 6, 1, 12, occurred_at_minute, tzinfo=timezone.utc),
        game_time_label=None,
        source=EpisodeSource(event_ids=("evt-1",)),
        location=EpisodeLocation(spot_id=3),
        action=EpisodeAction(tool_name="x"),
        who=(),
        what="something happened",
        why=None,
        observed="観測本文",
        expected=None,
        outcome="ok",
        prediction_error=prediction_error,
        felt=None,
        interpreted=interpreted,
        cues=(),
        recall_text=recall_text,
    )


@dataclass
class _StubPort(ISemanticGistCompletionPort):
    """常に固定 dict を返す stub。テスト中に受け取った messages も記録する。"""

    response: Dict[str, Any]
    captured_messages: List[List[Dict[str, Any]]] | None = None

    def __post_init__(self) -> None:
        self.captured_messages = []

    def complete_semantic_gist_json(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        assert self.captured_messages is not None
        self.captured_messages.append(messages)
        return self.response


@dataclass
class _RaisingPort(ISemanticGistCompletionPort):
    """常に例外を投げる stub。"""

    exc: Exception

    def complete_semantic_gist_json(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        raise self.exc


class TestSemanticGistServiceGenerate:
    """正常系: LLM 応答を SemanticGistResult に変換する。"""

    def test_llm_result_included(self) -> None:
        """有効な LLM 応答が そのまま result に乗る。"""
        port = _StubPort(response={
            "gist_text": "タカシは漁の名手で信頼できる",
            "importance_score": 8,
            "tags": ["タカシ", "信頼"],
        })
        svc = SemanticGistService(port)
        eps = [_make_episode(episode_id="e1", recall_text="タカシが魚を分けてくれた")]

        result = svc.generate(
            player_name="ハル",
            persona_block="慎重で寡黙な漁師",
            cluster_episodes=eps,
        )
        assert isinstance(result, SemanticGistResult)
        assert result.gist_text == "タカシは漁の名手で信頼できる"
        assert result.importance_score == 8
        assert result.tags == ("タカシ", "信頼")

    def test_fifty_over_gist_fifty_truncate(self) -> None:
        """50字超の gist は 50字で truncate。"""
        long_text = "あ" * 80
        port = _StubPort(response={"gist_text": long_text, "importance_score": 5, "tags": []})
        svc = SemanticGistService(port)
        result = svc.generate(
            player_name="x",
            persona_block="",
            cluster_episodes=[_make_episode()],
        )
        assert len(result.gist_text) == 50

    def test_importance_score(self) -> None:
        """importancescore が範囲外ならクランプ。"""
        port = _StubPort(response={"gist_text": "g", "importance_score": 99, "tags": []})
        svc = SemanticGistService(port)
        assert svc.generate(
            player_name="x", persona_block="", cluster_episodes=[_make_episode()]
        ).importance_score == 10

        port2 = _StubPort(response={"gist_text": "g", "importance_score": -3, "tags": []})
        svc2 = SemanticGistService(port2)
        assert svc2.generate(
            player_name="x", persona_block="", cluster_episodes=[_make_episode()]
        ).importance_score == 1

    def test_importance_score_non_number_default_five(self) -> None:
        """importancescore が非数値なら default5。"""
        port = _StubPort(response={"gist_text": "g", "importance_score": "abc", "tags": []})
        svc = SemanticGistService(port)
        assert svc.generate(
            player_name="x", persona_block="", cluster_episodes=[_make_episode()]
        ).importance_score == 5

    def test_tags_eight_cap(self) -> None:
        """tags は 8件 までで cap。"""
        port = _StubPort(response={
            "gist_text": "g",
            "importance_score": 5,
            "tags": [f"t{i}" for i in range(20)],
        })
        svc = SemanticGistService(port)
        result = svc.generate(
            player_name="x", persona_block="", cluster_episodes=[_make_episode()]
        )
        assert len(result.tags) == 8

    def test_tag_element_30_cap(self) -> None:
        """tag の各要素は 30文字で cap。"""
        port = _StubPort(response={
            "gist_text": "g",
            "importance_score": 5,
            "tags": ["あ" * 50],
        })
        svc = SemanticGistService(port)
        result = svc.generate(
            player_name="x", persona_block="", cluster_episodes=[_make_episode()]
        )
        assert len(result.tags[0]) == 30

    def test_tags_empty_string_non_str_element(self) -> None:
        """tags の空文字や 非str要素は 除外。"""
        port = _StubPort(response={
            "gist_text": "g",
            "importance_score": 5,
            "tags": ["ok", "", "  ", 123, None, "another"],
        })
        svc = SemanticGistService(port)
        result = svc.generate(
            player_name="x", persona_block="", cluster_episodes=[_make_episode()]
        )
        assert result.tags == ("ok", "another")


class TestSemanticGistServicePromptStructure:
    """messages にペルソナ / 名前 / 記憶 / 既存 semantic が乗る。"""

    def test_player_name_persona_user_included(self) -> None:
        """player name と persona が user メッセージに乗る。"""
        port = _StubPort(response={"gist_text": "g", "importance_score": 5, "tags": []})
        svc = SemanticGistService(port)
        svc.generate(
            player_name="ハル",
            persona_block="慎重で寡黙な漁師",
            cluster_episodes=[_make_episode(recall_text="魚を獲った")],
        )
        msgs = port.captured_messages[0]
        user_content = msgs[1]["content"]
        assert "ハル" in user_content
        assert "慎重で寡黙な漁師" in user_content
        assert "魚を獲った" in user_content

    def test_prediction_error_evidence_user_included(self) -> None:
        """予測との食い違いが記憶の sub-bullet として gist prompt に渡る (PR3)。"""
        port = _StubPort(response={"gist_text": "g", "importance_score": 5, "tags": []})
        svc = SemanticGistService(port)
        svc.generate(
            player_name="リン",
            persona_block="",
            cluster_episodes=[
                _make_episode(
                    recall_text="ノアに話しかけた",
                    prediction_error="話せると思ったが無視された",
                )
            ],
        )
        user_content = port.captured_messages[0][1]["content"]
        assert "予測との食い違い: 話せると思ったが無視された" in user_content

    def test_prediction_error_memory_line(self) -> None:
        """prediction_error が None の記憶では食い違い行を付けない。"""
        port = _StubPort(response={"gist_text": "g", "importance_score": 5, "tags": []})
        svc = SemanticGistService(port)
        svc.generate(
            player_name="リン",
            persona_block="",
            cluster_episodes=[_make_episode(recall_text="散歩した", prediction_error=None)],
        )
        user_content = port.captured_messages[0][1]["content"]
        assert "予測との食い違い" not in user_content

    def test_system_prompt(self) -> None:
        """system prompt に予測誤差を重視する指示と importance rubric がある。"""
        port = _StubPort(response={"gist_text": "g", "importance_score": 5, "tags": []})
        svc = SemanticGistService(port)
        svc.generate(player_name="x", persona_block="", cluster_episodes=[_make_episode()])
        system_content = port.captured_messages[0][0]["content"]
        assert "予測との食い違い" in system_content
        # 予測が繰り返し外れた経験を重要度高に評価する rubric
        assert "予測が繰り返し" in system_content

    def test_existing_semantic_included(self) -> None:
        """既存 semantic があれば参考として乗る。"""
        port = _StubPort(response={"gist_text": "g", "importance_score": 5, "tags": []})
        svc = SemanticGistService(port)
        existing = SemanticMemoryEntry(
            entry_id="sem-1",
            player_id=1,
            text="タカシは漁の名手",
            evidence_episode_ids=("e1",),
            confidence=0.6,
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        svc.generate(
            player_name="x",
            persona_block="",
            cluster_episodes=[_make_episode()],
            existing_related_semantic=[existing],
        )
        user_content = port.captured_messages[0][1]["content"]
        assert "タカシは漁の名手" in user_content

    def test_system_label(self) -> None:
        """system メッセージに ラベル禁止 の指示が入る。"""
        port = _StubPort(response={"gist_text": "g", "importance_score": 5, "tags": []})
        svc = SemanticGistService(port)
        svc.generate(
            player_name="x",
            persona_block="",
            cluster_episodes=[_make_episode()],
        )
        system_content = port.captured_messages[0][0]["content"]
        assert "ラベル" in system_content or "P1" in system_content


class TestSemanticGistServiceErrors:
    """異常系: 空 cluster / API 例外 / 不正 JSON。"""

    def test_empty_cluster_value_error(self) -> None:
        """空 cluster は value error。"""
        port = _StubPort(response={"gist_text": "g", "importance_score": 5, "tags": []})
        svc = SemanticGistService(port)
        with pytest.raises(ValueError, match="cluster_episodes must not be empty"):
            svc.generate(player_name="x", persona_block="", cluster_episodes=[])

    def test_port_llm_api_call_exception(self) -> None:
        """port が LlmApiCallException なら 伝播。"""
        port = _RaisingPort(
            exc=LlmApiCallException("test fail", error_code="LLM_API_CALL_FAILED")
        )
        svc = SemanticGistService(port)
        with pytest.raises(LlmApiCallException):
            svc.generate(
                player_name="x", persona_block="", cluster_episodes=[_make_episode()]
            )

    def test_gist_text_missing_value_error(self) -> None:
        """gisttext が欠落なら valueerror。"""
        port = _StubPort(response={"importance_score": 5, "tags": []})
        svc = SemanticGistService(port)
        with pytest.raises(ValueError, match="missing or empty gist_text"):
            svc.generate(
                player_name="x", persona_block="", cluster_episodes=[_make_episode()]
            )

    def test_gist_text_empty_string_value_error(self) -> None:
        """gisttext が空文字なら valueerror。"""
        port = _StubPort(response={"gist_text": "   ", "importance_score": 5, "tags": []})
        svc = SemanticGistService(port)
        with pytest.raises(ValueError, match="missing or empty gist_text"):
            svc.generate(
                player_name="x", persona_block="", cluster_episodes=[_make_episode()]
            )

    def test_port_none_type_error(self) -> None:
        """port が None なら type error。"""
        with pytest.raises(TypeError, match="port must not be None"):
            SemanticGistService(port=None)  # type: ignore[arg-type]

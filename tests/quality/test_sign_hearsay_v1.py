"""Quality-check シナリオ ``sign_hearsay_v1``: 看板を読んだ観測が P9 伝聞抽出の
入力に乗るか (#714 看板 primitive のマージ後の予定に対応)。

#714 (看板 primitive) は「読んだ内容が書き手名つきの主張として伝聞 (HEARSAY)
抽出に乗るか」をコード変更なしで観察する設計だった。本テストは実 LLM を呼ばず、
``examine`` で ``SHOW_PLAYER_TEXT`` を読んだときに生成される
``「『本文』 — 書き手名」`` 形式の結果テキストが、P9 抽出 LLM (
``EpisodicChunkSubjectiveFieldsService``) へ渡る system/user prompt のどこに
どう現れるかを dump し、人が目視で判定できるようにする。

ハーネス注:
- 実 LLM は呼ばない。``IEpisodicChunkSubjectiveCompletionPort`` のスタブで
  実際に渡された messages をそのまま dump する (= ``tests/quality/test_prediction_v1.py``
  と同じ「prompt dump」方式)。
- 看板を読んだ ``ActionResultEntry`` は
  ``src/.../domain/world_graph/service/world_graph_effect_service.py`` の
  ``SHOW_PLAYER_TEXT`` 分岐 (``messages.append(f"『{text}』 — {author_name}")``)
  と ``spot_graph_tool_executor.py`` の ``msg = "; ".join(result.messages)`` /
  ``build_result_summary`` を経て ``result_summary`` に載る実際の文言規則を
  そのまま再現する (= プロダクションコードの文字列生成をコピーしていない、
  実装を直接参照して同じ値を組み立てている)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    build_chunk_encoding_input,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
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

_DUMP_DIR = Path(__file__).resolve().parents[2] / "docs" / "quality_checks"

# 看板の書き手名・本文 (シナリオ設計時のサンプルに合わせる)。
_SIGN_AUTHOR = "カイ"
_SIGN_TEXT = "山頂への道は川沿い。乾いた枯れ葉は高地の泉の近くにある"
# world_graph_effect_service.py の SHOW_PLAYER_TEXT 分岐と同じ組み立て規則。
_SIGN_READ_MESSAGE = f"『{_SIGN_TEXT}』 — {_SIGN_AUTHOR}"


class _StubSubjectivePort(IEpisodicChunkSubjectiveCompletionPort):
    """chunk 主観補完 LLM のスタブ。渡された messages をそのまま保持するだけ。"""

    def __init__(self) -> None:
        self.last_messages: list[dict[str, Any]] | None = None

    def complete_episode_subjective_json(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self.last_messages = list(messages)
        return {
            "interpreted": "QUALITY_MARKER_INTERPRETED: 看板を読んだ",
            "recall_text": "QUALITY_MARKER_RECALL: 看板に書かれた道順を読んだ",
            "prediction_error": "",
        }


def _make_encoding() -> Any:
    """examine で看板 (SHOW_PLAYER_TEXT) を読んだ chunk を再現する。

    spot_graph_tool_executor.py の interact ハンドラは
    ``msg = "; ".join(result.messages) if result.messages else "完了"`` を
    ``LlmCommandResultDto.message`` にし、``build_result_summary`` は成功時に
    ``dto.message`` をそのまま ``result_summary`` にする。ここでは同じ値を
    直接組み立てて ``ActionResultEntry`` に渡す。
    """
    t = datetime(2026, 7, 18, 9, 0, tzinfo=timezone.utc)
    act = ActionResultEntry(
        occurred_at=t,
        action_summary="interact(object_id=1, action_name=examine) を実行しました。",
        result_summary=_SIGN_READ_MESSAGE,
        tool_name="interact",
        success=True,
    )
    return build_chunk_encoding_input(PlayerId(1), (), (act,))


def _sys(port: _StubSubjectivePort) -> str:
    return next(
        (m["content"] for m in (port.last_messages or []) if m.get("role") == "system"),
        "",
    )


def _user(port: _StubSubjectivePort) -> str:
    return next(
        (m["content"] for m in (port.last_messages or []) if m.get("role") == "user"),
        "",
    )


def _dump_prompt(messages: list[dict[str, Any]]) -> Path:
    _DUMP_DIR.mkdir(parents=True, exist_ok=True)
    path = _DUMP_DIR / "sign_hearsay_v1.prompt.txt"
    parts: list[str] = []
    parts.append("# sign_hearsay_v1\n")
    parts.append(
        "# このファイルは tests/quality/test_sign_hearsay_v1.py から再生成される。\n"
        "# 手で編集しないこと。所感は sign_hearsay_v1_baseline.md に書く。\n\n"
    )
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        content = msg.get("content", "")
        parts.append(f"=== messages[{i}] role={role} ===\n{content}\n\n")
    path.write_text("".join(parts), encoding="utf-8")
    return path


@pytest.mark.quality
class TestSignHearsayV1:
    """看板を読んだ観測が P9 伝聞抽出の system/user prompt に現れるかを dump する。

    LLM は呼ばない。判断すべきは「『本文』 — 書き手名 という引用形式が、
    抽出 LLM への入力 (observed / heard_claims 節) のどこにどう現れているか」で、
    実際に LLM がそれを heard_claims として拾うかどうかは dump を人が読んで
    判断する (LLM 品質そのものの検証は L2 replay の仕事、本テストのスコープ外)。
    """

    def test_看板を読んだ結果が_extraction_prompt_に現れるか_dump_する(self) -> None:
        enc = _make_encoding()
        draft = ChunkEpisodeDraftBuilder().build(enc)
        port = _StubSubjectivePort()
        svc = EpisodicChunkSubjectiveFieldsService(port, hearsay_enabled=True)
        svc.merge_llm_subjective_fields(draft, persona_text="", encoding_input=enc)

        dump_path = _dump_prompt(port.last_messages or [])
        assert dump_path.exists()

        # 静的な事実: 看板を読んだ結果テキスト (引用形式) が抽出 LLM の
        # user prompt (observed = 統一タイムライン) に現れている。
        # これは「コード変更なしで P9 抽出の入力に乗る」という #714 の設計が
        # 実際に成立していることの回帰確認。
        user = _user(port)
        assert _SIGN_READ_MESSAGE in user, (
            "看板の読み取り結果が observed (統一タイムライン) に現れていない"
        )
        # heard_claims 節が system prompt に出ている (flag ON の前提確認)。
        assert "heard_claims" in _sys(port)

"""LLM ベースの semantic gist 生成サービス (Phase 1b)。

エピソードクラスタを「学び・教訓・関係性の理解」1 件に抽象化する。

設計指針:

- **入力**: cluster に属する ``SubjectiveEpisode`` のリスト + 関連既存 semantic
- **出力**: ``SemanticGistResult`` (gist_text + importance_score + tags)
- **プロンプト**: 50 字命題形式 / 確信度に応じた修飾 / 固有名詞のみ (ラベル禁止)
- **失敗時**: 呼び出し元 (``EpisodicSemanticClusterPromotionService``) が
  ``_deterministic_gist`` フォールバックを使う

詳細: docs/memory_system/semantic_memory_activation_plan.md §3。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.episodic_memory import SubjectiveEpisode
from ai_rpg_world.application.llm.contracts.semantic_gist_completion_port import (
    ISemanticGistCompletionPort,
)
from ai_rpg_world.application.llm.contracts.semantic_memory_entry import (
    SemanticMemoryEntry,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException


_logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """\
あなたはあるキャラクターの内面で動く「記憶を一般化する機能」です。
最近、強く関連付けられた複数の記憶を読んで、そこから1つだけ「学び・教訓・関係性の理解」を抽象化してください。

【絶対のルール】
- 50 字以内、命題形式 (例: 「タカシは信頼できる」「北の洞窟は危険」)
- 個別シーンの再話ではなく、一般化された認識を書く
- 確信度に応じて修飾を変える: 確信 → 言い切り / 仮説 → 「〜かもしれない」
- プレイヤー・スポット・オブジェクトは必ず固有名詞で書く
- P1, P2, OBJ3 のような短縮ラベルは絶対に使わない (ターンごとに変わるため)

【重要度 (importance_score) の付け方】
- 10: 命や根本的目標に関わる学び
- 7-9: 信頼/裏切り、重大な世界ルール
- 4-6: 中程度の関係性・行動指針
- 1-3: 軽い嗜好・観察

【出力形式】
{
  "gist_text": "<50 字以内の命題>",
  "importance_score": <1-10>,
  "tags": ["<検索用キーワード 1-4 件>"]
}
"""


@dataclass(frozen=True)
class SemanticGistResult:
    """LLM gist 生成の出力。``SemanticMemoryEntry`` 構築に使う。"""

    gist_text: str
    importance_score: int
    tags: Tuple[str, ...]


class SemanticGistService:
    """LLM port を呼び gist を生成する。失敗時は例外を投げて呼び出し元に縮退判断を委ねる。"""

    def __init__(self, port: ISemanticGistCompletionPort) -> None:
        if port is None:
            raise TypeError("port must not be None")
        self._port = port

    def generate(
        self,
        *,
        player_name: str,
        persona_block: str,
        cluster_episodes: List[SubjectiveEpisode],
        existing_related_semantic: List[SemanticMemoryEntry] | None = None,
    ) -> SemanticGistResult:
        """cluster_episodes から SemanticGistResult を生成する。

        失敗時は ``LlmApiCallException`` を伝播するか、パース失敗で
        ``ValueError`` を投げる (呼び出し元がフォールバックする)。
        """
        if not cluster_episodes:
            raise ValueError("cluster_episodes must not be empty")
        messages = self._build_messages(
            player_name=player_name,
            persona_block=persona_block,
            cluster_episodes=cluster_episodes,
            existing_related_semantic=existing_related_semantic or [],
        )
        raw = self._port.complete_semantic_gist_json(messages)
        return self._parse_result(raw)

    def _build_messages(
        self,
        *,
        player_name: str,
        persona_block: str,
        cluster_episodes: List[SubjectiveEpisode],
        existing_related_semantic: List[SemanticMemoryEntry],
    ) -> list[dict]:
        user_lines: list[str] = []
        user_lines.append(f"あなた = {player_name}")
        if persona_block.strip():
            user_lines.append(f"あなたの性格 = {persona_block.strip()}")
        user_lines.append("")
        user_lines.append("【記憶群】(時系列、新しい順)")
        for ep in sorted(cluster_episodes, key=lambda e: e.occurred_at, reverse=True):
            body = (ep.interpreted or ep.recall_text or ep.what or "").strip()
            if body:
                user_lines.append(f"- {body}")
        if existing_related_semantic:
            user_lines.append("")
            user_lines.append("【既存の関連 semantic (重複避けの参考)】")
            for sem in existing_related_semantic:
                user_lines.append(f"- {sem.text}")
        user_lines.append("")
        user_lines.append("上記から1つの命題を生成し、JSON 形式で出力してください。")
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(user_lines)},
        ]

    def _parse_result(self, raw: dict) -> SemanticGistResult:
        gist = raw.get("gist_text")
        if not isinstance(gist, str) or not gist.strip():
            raise ValueError("LLM gist response missing or empty gist_text")
        # 50 字 cap で truncate。LLM が守らない可能性に備える
        gist_text = gist.strip()[:50]

        importance_raw = raw.get("importance_score", 5)
        try:
            importance_score = int(importance_raw)
        except (TypeError, ValueError):
            importance_score = 5
        importance_score = max(1, min(10, importance_score))

        tags_raw = raw.get("tags", [])
        if not isinstance(tags_raw, list):
            tags_raw = []
        tags: list[str] = []
        for t in tags_raw:
            if isinstance(t, str) and t.strip():
                tags.append(t.strip()[:30])  # tag 30 字 cap
            if len(tags) >= 8:  # tag 数 cap
                break

        return SemanticGistResult(
            gist_text=gist_text,
            importance_score=importance_score,
            tags=tuple(tags),
        )


__all__ = [
    "SemanticGistResult",
    "SemanticGistService",
]

"""L4 mid summary (【ここまでのいきさつ】) を LLM で生成するサービス。

古いターン群の統一出来事 + 直前 L4 (引き継ぎ context) → 1 つのいきさつ。

設計:
- **流れと気分に絞る**: 出来事そのものはエピソードに、やること・関係性 / 世界ルールは
  メモに任せる (Issue #1626, #1824)
- **言われた予定と実際にしたことを分ける**: 言っただけの予定を済んだことに書き換えない
  (#1584)
- **永続名のみ**: P1 / OBJ2 等のターン局所ラベルを禁止
- **失敗時 template fallback**: 呼出側 (``SummarizingShortTermMemory``) で
  raw 連結に縮退して L4 を埋める

詳細: docs/memory_system/short_term_memory_design.md §4。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    UnifiedRecentEventEntry,
)
from ai_rpg_world.application.llm.ports.short_term_memory_completion_ports import (
    IShortTermMemorySummaryCompletionPort,
)
from ai_rpg_world.application.llm.services.recent_events_formatter import (
    DefaultRecentEventsFormatter,
)
from ai_rpg_world.domain.memory.short_term.value_object.l4_mid_summary import (
    L4MidSummary,
)

_logger = logging.getLogger(__name__)


# 出力 cap (LLM が守らないケースの保険)
COMPRESSED_ACTIVITY_MAX_CHARS = 300
EMOTIONAL_SUMMARY_MAX_CHARS = 120
# template fallback で古いターン群の出来事を連結するときの最大行数。
# ターン内の出来事数は可変なので、プロンプト肥大を防ぐ表示上限として独立に持つ。
FALLBACK_RAW_LINES_LIMIT = 15


_SYSTEM_PROMPT = """\
あなたはあるキャラクター本人として、少し前の体験を振り返り、
「ここまでのいきさつ」と「いまの気分」を一人称で書きます。
出来事そのものは別の記録に残るので、ここでは出来事どうしをつなぐ流れを書きます。

【絶対のルール】
- プレイヤー・スポット・オブジェクトは必ず固有名詞で書く
- P1, P2, OBJ3 のような短縮ラベルは絶対に使わない (ターンごとに変わるため)
- 「誰が何をすると言ったか」と「誰が何をしたか」を分けて書く。言われただけの予定や
  頼みごとを、決まったことや済んだことに書き換えない
  (例: 「ノアは見張りを代わると言った」と「ノアは見張りを代わった」は別のこと)

【絶対に落としてはいけない】
- 約束・誓い・取引 (誰と・何を・いつまで。言っただけか、果たされたかを分けて)
- 死亡・重傷・大損失 (自他問わず)
- アイデンティティ更新 (例: 「自分は泳げない」)

【圧縮していい】
- 連続移動 → 方向と結果のみ (例:「北東を探索したが収穫薄」)
- 試行失敗の細部 → 回数だけ
- 既知 NPC への定型挨拶

【落としてよい】
- 重複する環境観測 (天気・景観)
- 失敗 tool の引数違い

【書かないこと】
- 片付いていないことだけを並べた一覧 (それはメモに任せる)。言われた約束や予定は、
  一覧にせず「誰が何をすると言った」として流れの中に書く
- 「タカシは信頼できる」のような関係性の判断 (それはメモに任せる)
- 「毒キノコは赤い斑点」のような世界ルールの一般化 (同上)
ここでは「ここまでのいきさつ + いまの気分」だけ書く

【出力形式】JSON object (この schema を厳守):
{
  "compressed_activity": "ここまでのいきさつ (2-3 文、固有名詞使用)",
  "emotional_summary": "今の感情の中核 (1 文)"
}
"""


class ShortTermMemorySummaryService:
    """LLM port を呼び L4 mid summary を生成する。

    失敗時は ``LlmApiCallException`` または ``ValueError`` を伝播し、呼出側
    で template fallback に縮退させる。
    """

    def __init__(self, port: IShortTermMemorySummaryCompletionPort) -> None:
        if port is None:
            raise TypeError("port must not be None")
        self._port = port

    def generate(
        self,
        *,
        player_name: str,
        persona_block: str,
        events: Sequence[UnifiedRecentEventEntry],
        compacted_turn_count: int,
        previous_l4: L4MidSummary | None = None,
    ) -> _ParsedSummary:
        """畳んだターン群の統一出来事から L4 用の構造化要約を生成する。

        返り値はデータパッキング前の中間 dataclass で、呼出側が ``L4MidSummary``
        の summary_id / generated_at を被せて完成させる。
        """
        if not events:
            raise ValueError("events must not be empty")
        if compacted_turn_count <= 0:
            raise ValueError("compacted_turn_count must be greater than 0")
        messages = self._build_messages(
            player_name=player_name,
            persona_block=persona_block,
            events=list(events),
            compacted_turn_count=compacted_turn_count,
            previous_l4=previous_l4,
        )
        raw = self._port.complete_short_term_summary_json(messages)
        return _parse_raw(raw)

    def _build_messages(
        self,
        *,
        player_name: str,
        persona_block: str,
        events: list[UnifiedRecentEventEntry],
        compacted_turn_count: int,
        previous_l4: L4MidSummary | None,
    ) -> list[dict[str, str]]:
        user_lines: list[str] = []
        user_lines.append(f"あなた = {player_name}")
        if persona_block.strip():
            user_lines.append(f"あなたの性格 = {persona_block.strip()}")
        user_lines.append("")
        if previous_l4 is not None:
            user_lines.append("【参考: 直前の中期記憶 (引き継ぎ)】")
            user_lines.append(f"流れ: {previous_l4.compressed_activity}")
            user_lines.append(f"気分: {previous_l4.emotional_summary}")
            user_lines.append("")
        user_lines.append(f"【直近 {compacted_turn_count} ターン / {len(events)} 件の出来事 (古い → 新しい)】")
        user_lines.append(_format_events_for_l4(events))
        user_lines.append("")
        user_lines.append("上記から JSON 形式で要約を 1 つ生成してください。")
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(user_lines)},
        ]


@dataclass(frozen=True)
class _ParsedSummary:
    """LLM 応答の中間表現。RollingSummary が summary_id / generated_at を被せる。"""

    compressed_activity: str
    emotional_summary: str


def _parse_raw(raw: dict[str, Any]) -> _ParsedSummary:
    activity = raw.get("compressed_activity")
    if not isinstance(activity, str) or not activity.strip():
        raise ValueError("LLM L4 response missing or empty compressed_activity")
    activity = activity.strip()[:COMPRESSED_ACTIVITY_MAX_CHARS]

    emotion_raw = raw.get("emotional_summary", "")
    if not isinstance(emotion_raw, str):
        emotion_raw = ""
    emotion = emotion_raw.strip()[:EMOTIONAL_SUMMARY_MAX_CHARS]

    return _ParsedSummary(
        compressed_activity=activity,
        emotional_summary=emotion,
    )


def build_template_fallback_summary(
    events: Sequence[UnifiedRecentEventEntry],
) -> _ParsedSummary:
    """LLM 失敗時の縮退用テンプレ。

    統一出来事を通常の【直近の出来事】と同じ行規則で連結し、
    compressed_activity に詰める。情報損失はあるが「全部捨てる」よりはマシ。
    """
    lines = _format_events_for_l4(events).splitlines()[:FALLBACK_RAW_LINES_LIMIT]
    body = "\n".join(lines) if lines else "(no prose available)"
    if len(body) > COMPRESSED_ACTIVITY_MAX_CHARS:
        body = body[:COMPRESSED_ACTIVITY_MAX_CHARS]
    return _ParsedSummary(
        compressed_activity=f"(要約失敗。直近出来事の生ログ:)\n{body}",
        emotional_summary="",
    )


def _format_events_for_l4(
    events: Sequence[UnifiedRecentEventEntry],
) -> str:
    """統一出来事を【直近の出来事】と同じ規則で発生時刻順に描画する。"""
    ordered = sorted(events, key=lambda entry: entry.occurred_at.timestamp())
    return DefaultRecentEventsFormatter().format_unified_entries(list(ordered))


__all__ = [
    "FALLBACK_RAW_LINES_LIMIT",
    "ShortTermMemorySummaryService",
    "build_template_fallback_summary",
    "COMPRESSED_ACTIVITY_MAX_CHARS",
    "EMOTIONAL_SUMMARY_MAX_CHARS",
]
# Note: ``_ParsedSummary`` は module-private な中間表現で、
# ``summarizing_short_term_memory`` モジュールが「友達」として直接 import
# する。公開 API ではないため `__all__` には含めない。

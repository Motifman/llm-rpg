"""L4 mid summary (Phase 2) を LLM で生成するサービス。

raw observation 15 件 + 直前 L4 (引き継ぎ context) → 1 つの主観要約。

設計:
- **narrative continuity に絞る**: 学び / 関係性 / 世界ルールは semantic 経路に
  任せる (docs §4)
- **永続名のみ**: P1 / OBJ2 等のターン局所ラベルを禁止
- **失敗時 template fallback**: 呼出側 (``RollingSummaryShortTermMemory``) で
  raw 連結に縮退して L4 を埋める

詳細: docs/memory_system/short_term_memory_design.md §4。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from ai_rpg_world.application.llm.contracts.short_term_memory import (
    IShortTermMemorySummaryCompletionPort,
)
from ai_rpg_world.domain.memory.short_term.value_object.l4_mid_summary import (
    L4MidSummary,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry


_logger = logging.getLogger(__name__)


# 出力 cap (LLM が守らないケースの保険)
COMPRESSED_ACTIVITY_MAX_CHARS = 300
EMOTIONAL_SUMMARY_MAX_CHARS = 120
UNRESOLVED_MAX_ITEMS = 3
UNRESOLVED_ITEM_MAX_CHARS = 120
# template fallback で raw 観測を連結するときの最大行数。
# ``RollingSummaryShortTermMemory.DEFAULT_L1_SOFT_CAP`` (15) と同期させる。
# 循環 import を避けるため、ここに独立した定数として持つ。
FALLBACK_RAW_LINES_LIMIT = 15


_SYSTEM_PROMPT = """\
あなたはあるキャラクター本人として、直近の体験を振り返り、
「最近何があったか」「いまの気分」「未解決のこと」を一人称で要約します。

【絶対のルール】
- プレイヤー・スポット・オブジェクトは必ず固有名詞で書く
- P1, P2, OBJ3 のような短縮ラベルは絶対に使わない (ターンごとに変わるため)

【絶対に落としてはいけない】
- 約束・誓い・取引 (誰と・何を・いつまで)
- 死亡・重傷・大損失 (自他問わず)
- 未解決の脅威・目標
- アイデンティティ更新 (例: 「自分は泳げない」)

【圧縮していい】
- 連続移動 → 方向と結果のみ (例:「北東を探索したが収穫薄」)
- 試行失敗の細部 → 回数だけ
- 既知 NPC への定型挨拶

【落としてよい】
- 重複する環境観測 (天気・景観)
- 失敗 tool の引数違い

【書かないこと】
- 「タカシは信頼できる」のような関係性の判断 (それは別の長期記憶に任せる)
- 「毒キノコは赤い斑点」のような世界ルールの一般化 (同上)
ここでは「最近の流れ + いまの気分 + 未解決」だけ書く

【出力形式】JSON object (この schema を厳守):
{
  "compressed_activity": "行動の流れ (2-3 文、固有名詞使用)",
  "emotional_summary": "今の感情の中核 (1 文)",
  "unresolved": ["未解決の脅威/目標 0-3 件、各短文"]
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
        observations: Sequence[ObservationEntry],
        previous_l4: L4MidSummary | None = None,
    ) -> _ParsedSummary:
        """observations から L4 用の構造化要約を生成する。

        返り値はデータパッキング前の中間 dataclass で、呼出側が ``L4MidSummary``
        の summary_id / generated_at を被せて完成させる。
        """
        if not observations:
            raise ValueError("observations must not be empty")
        messages = self._build_messages(
            player_name=player_name,
            persona_block=persona_block,
            observations=list(observations),
            previous_l4=previous_l4,
        )
        raw = self._port.complete_short_term_summary_json(messages)
        return _parse_raw(raw)

    def _build_messages(
        self,
        *,
        player_name: str,
        persona_block: str,
        observations: List[ObservationEntry],
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
            if previous_l4.unresolved:
                user_lines.append("未解決:")
                for u in previous_l4.unresolved:
                    user_lines.append(f"- {u}")
            user_lines.append("")
        user_lines.append(f"【直近 {len(observations)} 件の観測 (古い → 新しい)】")
        for i, obs in enumerate(observations):
            # observation.output は prose / structured を持つ。LLM には prose を渡す
            prose = (getattr(obs.output, "prose", None) or "").strip()
            if prose:
                user_lines.append(f"{i+1}. {prose}")
            else:
                user_lines.append(f"{i+1}. (no prose)")
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
    unresolved: Tuple[str, ...]


def _parse_raw(raw: dict) -> _ParsedSummary:
    activity = raw.get("compressed_activity")
    if not isinstance(activity, str) or not activity.strip():
        raise ValueError("LLM L4 response missing or empty compressed_activity")
    activity = activity.strip()[:COMPRESSED_ACTIVITY_MAX_CHARS]

    emotion_raw = raw.get("emotional_summary", "")
    if not isinstance(emotion_raw, str):
        emotion_raw = ""
    emotion = emotion_raw.strip()[:EMOTIONAL_SUMMARY_MAX_CHARS]

    unresolved_raw = raw.get("unresolved", [])
    if not isinstance(unresolved_raw, list):
        unresolved_raw = []
    unresolved: list[str] = []
    for item in unresolved_raw:
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if not stripped:
            continue
        unresolved.append(stripped[:UNRESOLVED_ITEM_MAX_CHARS])
        if len(unresolved) >= UNRESOLVED_MAX_ITEMS:
            break

    return _ParsedSummary(
        compressed_activity=activity,
        emotional_summary=emotion,
        unresolved=tuple(unresolved),
    )


def build_template_fallback_summary(
    observations: Sequence[ObservationEntry],
) -> _ParsedSummary:
    """LLM 失敗時の縮退用テンプレ。

    raw observation の prose を改行連結して compressed_activity に詰める
    だけ。情報損失はあるが「全部捨てる」よりはマシ。
    """
    lines: list[str] = []
    for obs in observations:
        prose = (getattr(obs.output, "prose", None) or "").strip()
        if prose:
            lines.append(f"- {prose}")
        if len(lines) >= FALLBACK_RAW_LINES_LIMIT:
            break
    body = "\n".join(lines) if lines else "(no prose available)"
    if len(body) > COMPRESSED_ACTIVITY_MAX_CHARS:
        body = body[:COMPRESSED_ACTIVITY_MAX_CHARS]
    return _ParsedSummary(
        compressed_activity=f"(要約失敗。直近観測の生ログ:)\n{body}",
        emotional_summary="",
        unresolved=(),
    )


__all__ = [
    "FALLBACK_RAW_LINES_LIMIT",
    "ShortTermMemorySummaryService",
    "build_template_fallback_summary",
    "COMPRESSED_ACTIVITY_MAX_CHARS",
    "EMOTIONAL_SUMMARY_MAX_CHARS",
    "UNRESOLVED_MAX_ITEMS",
    "UNRESOLVED_ITEM_MAX_CHARS",
]
# Note: ``_ParsedSummary`` は module-private な中間表現で、
# ``rolling_summary_short_term_memory`` モジュールが「友達」として直接 import
# する。公開 API ではないため `__all__` には含めない。

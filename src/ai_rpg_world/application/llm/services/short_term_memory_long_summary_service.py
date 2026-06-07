"""L5 long summary (Phase 3) を LLM で生成するサービス。

previous_l5 + 最古 L4 (evict 寸前) → 統合した新 L5。

設計指針 (docs/memory_system/short_term_memory_design.md §4.2):
- **narrative voice のみ**: 学び / 関係性 / 世界ルールは含めない (semantic
  経路の責務)
- **persona drift 防止**: 性格 (persona) は previous_l5 のものを保ち、
  事実認識のみ更新される。プロンプトで強制
- **永続名のみ**: P1 / OBJ2 等のラベル禁止
- **失敗時 template fallback**: 呼出側で previous_l5 をそのまま延命する
  形に縮退 (= 沈黙の劣化を防ぐ)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ai_rpg_world.application.llm.contracts.short_term_memory import (
    IShortTermMemoryLongSummaryCompletionPort,
    L4MidSummary,
    L5LongSummary,
)


_logger = logging.getLogger(__name__)


# 出力 cap (LLM が守らないケースの保険)
SELF_IMAGE_MAX_CHARS = 240
WORLD_VIEW_MAX_CHARS = 240


_SYSTEM_PROMPT = """\
あなたはあるキャラクター本人として、自分の自己像と世界観を更新する作業を
します。これは長期記憶 (L5) の統合: 中期記憶 (L4) が古くなって evict される
直前に、その内容を「いまの私」「いまの世界」に溶かし込みます。

【絶対のルール】
- プレイヤー・スポット・オブジェクトは必ず固有名詞で書く
- P1, P2, OBJ3 のような短縮ラベルは絶対に使わない (ターンごとに変わるため)

【統合のルール】
- 細部 (tick / 個別 action) は捨てる。L5 は時を超えた認識
- 「次の行動選択に効く根本」だけ残す
- 信念が変わったら **古い信念を上書きする** (両論併記しない)
- **性格 (persona) は previous_l5 のものを保つ**。揺れるのは事実認識のみ。
  「慎重な性格だったが大胆になった」のような persona drift は禁止
- evicted L4 の細かい出来事は L5 に直接書かない。あくまで「自分の見方の
  変化」として抽象化する

【書かないこと】
- 「タカシは信頼できる」のような関係性の判断 → semantic 経路の責務
- 「毒キノコは赤い斑点」のような世界ルール → 同上
- 「今日の動き / 気分」→ L4 の責務

【出力形式】JSON object (この schema を厳守):
{
  "self_image": "今の自分を 2-3 文で (narrative voice / persona 不変)",
  "world_view": "この島について 2-3 文で (narrative voice)"
}
"""


class ShortTermMemoryLongSummaryService:
    """LLM port を呼び L5 long summary を生成する。

    失敗時は ``LlmApiCallException`` または ``ValueError`` を伝播し、呼出側
    で template fallback (previous_l5 延命) に縮退させる。
    """

    def __init__(self, port: IShortTermMemoryLongSummaryCompletionPort) -> None:
        if port is None:
            raise TypeError("port must not be None")
        self._port = port

    def generate(
        self,
        *,
        player_name: str,
        persona_block: str,
        previous_l5: L5LongSummary | None,
        evicted_l4: L4MidSummary,
    ) -> _ParsedLongSummary:
        """previous_l5 + evicted_l4 から新 L5 用の中間表現を生成する。

        返り値は dataclass パッキング前の中間で、呼出側が summary_id /
        generated_at / generation_index を被せて完成させる。
        """
        if evicted_l4 is None:
            raise ValueError("evicted_l4 must not be None")
        messages = self._build_messages(
            player_name=player_name,
            persona_block=persona_block,
            previous_l5=previous_l5,
            evicted_l4=evicted_l4,
        )
        raw = self._port.complete_short_term_long_summary_json(messages)
        return _parse_raw(raw)

    def _build_messages(
        self,
        *,
        player_name: str,
        persona_block: str,
        previous_l5: L5LongSummary | None,
        evicted_l4: L4MidSummary,
    ) -> list[dict[str, str]]:
        lines: list[str] = []
        lines.append(f"あなた = {player_name}")
        if persona_block.strip():
            lines.append(f"あなたの性格 (不変) = {persona_block.strip()}")
        lines.append("")
        lines.append("【現在のあなた (previous L5)】")
        if previous_l5 is not None:
            lines.append(f"自己像: {previous_l5.self_image}")
            lines.append(f"世界観: {previous_l5.world_view}")
        else:
            lines.append("(まだ自己像は形成されていない。初期 persona を起点に作る)")
        lines.append("")
        lines.append("【evict される中期記憶 (oldest L4)】")
        lines.append(f"行動の流れ: {evicted_l4.compressed_activity}")
        if evicted_l4.emotional_summary.strip():
            lines.append(f"気分: {evicted_l4.emotional_summary}")
        if evicted_l4.unresolved:
            lines.append("未解決:")
            for u in evicted_l4.unresolved:
                lines.append(f"- {u}")
        lines.append("")
        lines.append(
            "これらを統合して新しい self_image / world_view を JSON で出力してください。"
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(lines)},
        ]


@dataclass(frozen=True)
class _ParsedLongSummary:
    """LLM 応答の中間表現。RollingSummary が summary_id 等を被せる。"""

    self_image: str
    world_view: str


def _parse_raw(raw: dict) -> _ParsedLongSummary:
    self_image = raw.get("self_image")
    if not isinstance(self_image, str) or not self_image.strip():
        raise ValueError("LLM L5 response missing or empty self_image")
    self_image = self_image.strip()[:SELF_IMAGE_MAX_CHARS]

    world_view_raw = raw.get("world_view", "")
    if not isinstance(world_view_raw, str):
        world_view_raw = ""
    world_view = world_view_raw.strip()[:WORLD_VIEW_MAX_CHARS]

    return _ParsedLongSummary(self_image=self_image, world_view=world_view)


def build_template_fallback_long_summary(
    *,
    previous_l5: L5LongSummary | None,
    evicted_l4: L4MidSummary,
) -> _ParsedLongSummary:
    """LLM 失敗時の縮退テンプレ。

    previous_l5 があればそれをそのまま延命 (= 自己像が drift しない)。
    無ければ evicted_l4 の compressed_activity を self_image の代わりに
    詰める (情報損失はあるが「全部捨てる」よりはマシ)。
    """
    if previous_l5 is not None:
        return _ParsedLongSummary(
            self_image=previous_l5.self_image,
            world_view=previous_l5.world_view,
        )
    fallback = f"(自己像未生成: 直近の行動 = {evicted_l4.compressed_activity})"
    return _ParsedLongSummary(
        self_image=fallback[:SELF_IMAGE_MAX_CHARS],
        world_view="(世界観未生成)",
    )


__all__ = [
    "SELF_IMAGE_MAX_CHARS",
    "ShortTermMemoryLongSummaryService",
    "WORLD_VIEW_MAX_CHARS",
    "build_template_fallback_long_summary",
]

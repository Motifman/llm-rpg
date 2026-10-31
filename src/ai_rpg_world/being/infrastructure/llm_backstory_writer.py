"""直近の範囲から外す出来事を、LLM でここまでのいきさつにまとめる (#1824、design_decisions D1824-11)。

指示の文面は、今の短期記憶の要約に使っていた文に、字数の上限を足したもの (design_decisions D1824-12)。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ai_rpg_world.being.application.recent_events_text import experiences_text
from ai_rpg_world.being.domain.backstory_writer import BackstoryWriter, WrittenBackstory
from ai_rpg_world.being.domain.short_term_memory import Backstory, Experience

FLOW_MAX_CHARS = 300
MOOD_MAX_CHARS = 120
# まとめる出来事が無い範囲のいきさつ。LLM を呼ばずに、前のいきさつの流れを引き継ぐ。
NOTHING_HAPPENED_FLOW = "（この間に覚えている出来事は無い）"

SYSTEM_PROMPT = f"""\
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

【字数】
- ここまでのいきさつは {FLOW_MAX_CHARS} 字まで、いまの気分は {MOOD_MAX_CHARS} 字まで
- 超えた分は途中で切れるので、字数の中で文を終える

【出力形式】JSON object (この schema を厳守):
{{
  "compressed_activity": "ここまでのいきさつ (2-3 文、{FLOW_MAX_CHARS} 字まで、固有名詞使用)",
  "emotional_summary": "今の感情の中核 (1 文、{MOOD_MAX_CHARS} 字まで)"
}}
"""


class LlmBackstoryWriter(BackstoryWriter):
    """``complete_json`` は、無ツールの JSON 完了 (messages を渡すと応答の dict を返す)。"""

    def __init__(self, complete_json: Callable[[list[dict[str, str]]], Any]) -> None:
        self._complete_json = complete_json

    def write(
        self,
        *,
        self_name: str,
        persona: str,
        experiences: tuple[Experience, ...],
        previous: Backstory | None,
        until_turn: int,
        written_turn: int,
    ) -> WrittenBackstory:
        if not experiences:
            flow = previous.flow if previous is not None else NOTHING_HAPPENED_FLOW
            mood = previous.mood if previous is not None else ""
            return WrittenBackstory(
                backstory=Backstory(flow=flow, mood=mood, written_turn=written_turn, until_turn=until_turn)
            )
        response = self._complete_json(
            _messages(self_name=self_name, persona=persona, experiences=experiences, previous=previous)
        )
        flow, mood, truncated = _read(response)
        return WrittenBackstory(
            backstory=Backstory(flow=flow, mood=mood, written_turn=written_turn, until_turn=until_turn),
            truncated=truncated,
        )


def _messages(
    *, self_name: str, persona: str, experiences: tuple[Experience, ...], previous: Backstory | None
) -> list[dict[str, str]]:
    lines = [f"あなた = {self_name}"]
    if persona.strip():
        lines.append(f"あなたの性格 = {persona.strip()}")
    lines.append("")
    if previous is not None:
        lines += ["【参考: 直前の中期記憶 (引き継ぎ)】", f"流れ: {previous.flow}", f"気分: {previous.mood}", ""]
    lines += [
        f"【まとめる {len(experiences)} 件の出来事 (古い → 新しい)】",
        experiences_text(experiences),
        "",
        "上記から JSON 形式で要約を 1 つ生成してください。",
    ]
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": "\n".join(lines)}]


def _read(response: Any) -> tuple[str, str, dict[str, int]]:
    """流れと気分と、上限を超えて切り詰めた項目と切り詰める前の長さ。"""
    if not isinstance(response, dict):
        raise ValueError("backstory response must be a JSON object")
    flow = response.get("compressed_activity")
    if not isinstance(flow, str) or not flow.strip():
        raise ValueError("backstory response has no compressed_activity")
    mood = response.get("emotional_summary", "")
    texts = {"flow": flow.strip(), "mood": mood.strip() if isinstance(mood, str) else ""}
    limits = {"flow": FLOW_MAX_CHARS, "mood": MOOD_MAX_CHARS}
    truncated = {key: len(text) for key, text in texts.items() if len(text) > limits[key]}
    return texts["flow"][:FLOW_MAX_CHARS], texts["mood"][:MOOD_MAX_CHARS], truncated


__all__ = ["FLOW_MAX_CHARS", "MOOD_MAX_CHARS", "NOTHING_HAPPENED_FLOW", "SYSTEM_PROMPT", "LlmBackstoryWriter"]

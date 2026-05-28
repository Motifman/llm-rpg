"""コンテキストフォーマット戦略 (escape_game format に統一)。"""

from ai_rpg_world.application.llm.contracts.interfaces import IContextFormatStrategy


class SectionBasedContextFormatStrategy(IContextFormatStrategy):
    """``【...】`` 見出し形式でコンテキストを組み立てる戦略。

    Issue #227 chore β (経路統一プロジェクト後続):
        旧 ``## ...`` markdown 見出し形式から escape_game runtime で実戦投入され
        ていた ``【...】`` 形式に統一した。実 LLM での試行錯誤を経て調整された
        section 順序を採用し、本家経路と escape_game の prompt 形式の二重管理
        による drift を解消する。

    section 順 (空セクションは出力しない = ノイズ削減):

    1. **【現在の目的】** — objective_text (固定の目標文。実行時に provider が指定)
    2. **【現在地と周囲】** — current_state_text (必須)
    3. **【進行中のメモ】** — active_memos_text (memo_add の未完了)
    4. **【直近の出来事】** — recent_events_text (観測 + 行動結果の時系列)
    5. **【関連する記憶】** — relevant_memories_text (episodic_passive_recall)
    6. **【所持・判明した物証】** — inventory_text (provider が生成)

    「進行中のメモ」は現在地直後に置き、LLM が「今やるべきこと / 守るべき
    約束」を毎ターン真っ先に思い出せる位置にする。
    「関連する記憶」は記録から得た知見の section で、直近の出来事の後ろに置く
    (「今あった出来事」を踏まえて「過去の似た記憶」を読む順序)。
    「所持・判明した物証」は最後に置く (LLM が即時 actionable な持ち物を
    確認できる位置)。
    """

    def format(
        self,
        current_state_text: str,
        recent_events_text: str,
        relevant_memories_text: str = "",
        active_memos_text: str = "",
        objective_text: str = "",
        inventory_text: str = "",
    ) -> str:
        for name, value in (
            ("current_state_text", current_state_text),
            ("recent_events_text", recent_events_text),
            ("relevant_memories_text", relevant_memories_text),
            ("active_memos_text", active_memos_text),
            ("objective_text", objective_text),
            ("inventory_text", inventory_text),
        ):
            if not isinstance(value, str):
                raise TypeError(f"{name} must be str")

        sections: list[str] = []

        # 1. 現在の目的 (実行時に provider が指定。空なら section ごと省略)
        if objective_text.strip():
            sections.extend([
                "【現在の目的】",
                objective_text.strip(),
                "",
            ])

        # 2. 現在地と周囲 (必須)
        sections.extend([
            "【現在地と周囲】",
            current_state_text.strip() or "（情報なし）",
        ])

        # 3. 進行中のメモ (空なら省略)
        if active_memos_text.strip():
            sections.extend([
                "",
                "【進行中のメモ】",
                active_memos_text.strip(),
            ])

        # 4. 直近の出来事 (常に出す。空なら「（なし）」)
        sections.extend([
            "",
            "【直近の出来事】",
            "観測（世界から届いた事象）と、あなた自身の行動の結果が時系列に並びます。",
            recent_events_text.strip() or "（なし）",
        ])

        # 5. 関連する記憶 (episodic_passive_recall の結果。空なら省略)
        if relevant_memories_text.strip():
            sections.extend([
                "",
                "【関連する記憶】",
                relevant_memories_text.strip(),
            ])

        # 6. 所持・判明した物証 (provider が生成。空なら省略)
        if inventory_text.strip():
            sections.extend([
                "",
                "【所持・判明した物証】",
                inventory_text.strip(),
            ])

        return "\n".join(sections)

"""コンテキストフォーマット戦略の案A実装（セクション見出し形式）"""

from ai_rpg_world.application.llm.contracts.interfaces import IContextFormatStrategy


class SectionBasedContextFormatStrategy(IContextFormatStrategy):
    """
    案A: セクション見出し形式でコンテキストを組み立てる。
    ## 現在の状況 / ## 直近の出来事（新しい順） / ## 関連する記憶
    """

    def format(
        self,
        current_state_text: str,
        recent_events_text: str,
        relevant_memories_text: str,
    ) -> str:
        if not isinstance(current_state_text, str):
            raise TypeError("current_state_text must be str")
        if not isinstance(recent_events_text, str):
            raise TypeError("recent_events_text must be str")
        if not isinstance(relevant_memories_text, str):
            raise TypeError("relevant_memories_text must be str")

        sections = [
            "## 現在の状況",
            current_state_text.strip() or "（情報なし）",
            "",
            "## 直近の出来事（新しい順）",
            recent_events_text.strip() or "（なし）",
            "",
            "## 関連する記憶",
            relevant_memories_text.strip() or "（なし）",
        ]
        return "\n".join(sections)

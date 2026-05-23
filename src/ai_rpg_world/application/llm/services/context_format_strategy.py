"""コンテキストフォーマット戦略の案A実装（セクション見出し形式）"""

from ai_rpg_world.application.llm.contracts.interfaces import IContextFormatStrategy


class SectionBasedContextFormatStrategy(IContextFormatStrategy):
    """
    案A: セクション見出し形式でコンテキストを組み立てる。

    section 順 (Issue #188 Phase 1a で「進行中のメモ」を追加):

    1. ## 現在の状況
    2. ## 進行中のメモ (memo_add で固定したもの、未完了のみ)
    3. ## 直近の出来事（時系列順）
    4. ## 関連する記憶

    「進行中のメモ」は現在状態の直後に置き、LLM が「今やるべきこと / 守るべき
    約束」を毎ターン真っ先に思い出せる位置にする。
    """

    def format(
        self,
        current_state_text: str,
        recent_events_text: str,
        relevant_memories_text: str = "",
        active_memos_text: str = "",
    ) -> str:
        if not isinstance(current_state_text, str):
            raise TypeError("current_state_text must be str")
        if not isinstance(recent_events_text, str):
            raise TypeError("recent_events_text must be str")
        if not isinstance(relevant_memories_text, str):
            raise TypeError("relevant_memories_text must be str")
        if not isinstance(active_memos_text, str):
            raise TypeError("active_memos_text must be str")

        sections = [
            "## 現在の状況",
            current_state_text.strip() or "（情報なし）",
        ]
        # memo が空のときは section ごと出さない (ノイズ削減)
        if active_memos_text.strip():
            sections.extend([
                "",
                "## 進行中のメモ",
                active_memos_text.strip(),
            ])
        sections.extend([
            "",
            "## 直近の出来事（時系列順）",
            recent_events_text.strip() or "（なし）",
            "",
            "## 関連する記憶",
            relevant_memories_text.strip() or "（なし）",
        ])
        return "\n".join(sections)

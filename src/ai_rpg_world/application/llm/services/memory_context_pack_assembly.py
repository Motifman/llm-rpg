"""MemoryContextPack の最小組み立て（P5 導入段階）。

完全な §2.7 の検索・リンク解決は store / 想起パイプ側の今後の拡張に委ね、ここでは
プロンプト組み立てで既に揃う断片から Pack を生成する。
"""

from __future__ import annotations

from typing import Tuple

from ai_rpg_world.application.llm.contracts.memory_context_pack import MemoryContextPack


def assemble_memory_context_pack_for_recall_turn(
    *,
    situation_summary: str,
    current_goals: str,
    current_attention: str = "",
    recalled_episode_ids: Tuple[str, ...] = (),
) -> MemoryContextPack:
    """Passive Recall 直後など、想起 id が確定しているターン用の薄い組み立て。

    - ``focus_episode_id`` は想起リストの先頭（並びは呼び出し側のポリシーに従う）。
    - ``co_recalled_episode_ids`` には同一ターンで想起された id をそのまま載せる。
    """
    focus: str | None = recalled_episode_ids[0] if recalled_episode_ids else None
    return MemoryContextPack(
        current_situation=situation_summary,
        current_goals=current_goals,
        current_attention=current_attention,
        focus_episode_id=focus,
        co_recalled_episode_ids=recalled_episode_ids,
    )

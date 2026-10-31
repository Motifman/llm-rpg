"""Being の短期記憶のいきさつを、毎ターンのプロンプトの【ここまでのいきさつ】に出す本文にする (#1824)。

書き方は、今の短期記憶の要約を出していたころと同じ。
"""

from __future__ import annotations

from ai_rpg_world.being.domain.short_term_memory import ShortTermMemory


def backstory_text(memory: ShortTermMemory) -> str:
    """新しいいきさつから順に並べる。いきさつが無ければ空文字で、【ここまでのいきさつ】は出ない。"""
    blocks: list[str] = []
    for generation, backstory in enumerate(reversed(memory.backstories), start=1):
        label = "[最新]" if generation == 1 else f"[{generation} 世代前]"
        lines = [f"{label} {backstory.flow.strip()}"]
        if backstory.mood.strip():
            lines.append(f"  気分: {backstory.mood.strip()}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


__all__ = ["backstory_text"]

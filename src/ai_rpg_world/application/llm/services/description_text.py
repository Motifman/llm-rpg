"""Being へ渡す説明文 (Description) を、今のプロンプトの書き方で文にする。

作業記憶 (#1630) が Being の側で文にするようになるまでのつなぎ。
"""

from __future__ import annotations

from collections.abc import Iterable

from ai_rpg_world.being.contract import Description


def description_text(description: Description) -> str:
    return f"【{description.heading}】\n{description.text}"


def descriptions_text(descriptions: Iterable[Description]) -> str:
    return "\n\n".join(description_text(d) for d in descriptions)

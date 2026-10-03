"""環境に入るときに一度だけ渡す取り決め。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.contract.errors import require_optional_text, require_text


@dataclass(frozen=True, kw_only=True)
class EnvironmentEntry:
    """``self_name`` は、Being が自分の書いた文の中の自分を見分けるのに使う。
    観測の主体や宛先は環境が判定して観測に書くが、予期や信念の文の中の名前は
    環境には分からない。
    """

    environment_name: str
    self_name: str
    imposed_goal: str | None = None

    def __post_init__(self) -> None:
        require_text(self.environment_name, "environment_name")
        require_text(self.self_name, "self_name")
        require_optional_text(self.imposed_goal, "imposed_goal")

"""環境が Being に出している、Being 自身のための道具の一覧 (#1630)。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.contract.errors import require_bool, require_optional_text


@dataclass(frozen=True, kw_only=True)
class OfferedBeingTools:
    """名前は環境の tool の引数や tool の名前。出していない道具は None。

    Being は、出している道具の書き方だけを作法に書く。出していない道具を勧めると、
    エージェントは無い引数や tool を使おうとする。
    """

    inner_thought: str | None = None
    """行動の tool に添える独白の引数。"""
    memo: str | None = None
    """行動の tool に添えるメモ帳への書き込みの引数。"""
    episode_recall: str | None = None
    """呼び名を指定してエピソードの本文を思い出す tool。"""
    episode_index_shown: bool = False
    """【思い出せる出来事】(エピソードの目次) を毎ターン出すか。"""

    def __post_init__(self) -> None:
        for name in ("inner_thought", "memo", "episode_recall"):
            require_optional_text(getattr(self, name), name)
        require_bool(self.episode_index_shown, "episode_index_shown")

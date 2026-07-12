"""GoalEntry — 目的 (取り下げない選好的予測) の journal エントリ VO。

P5 (goal_layer_design_active_inference.md G1): 目的を per-Being の journal
方式で保持する (belief journal と同型: 改訂は supersede、履歴は消えない)。
【現在の目的】はこの store の active エントリから描画され、シナリオの
目的文は run 開始時に ``locked=True, origin="scenario"`` で seed される
(locked 初期値なら描画結果は従来の静的テキストと同一)。

- status: active | achieved | abandoned | superseded
  (belief と違い、改訂できるのは意識 (G2) だけ。無意識は監査するが書かない)
- locked: True なら意識 (G2) でも改訂不可 (勝利条件のあるシナリオの初期目的)
- origin: scenario (初期注入) | self (エージェント自身が立てた)
- supersedes: 改訂元の goal_id (journal 系譜)。無ければ None
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ai_rpg_world.domain.memory.goal.exception.goal_exception import (
    GoalEntryValidationException,
)

GOAL_STATUS_ACTIVE = "active"
GOAL_STATUS_ACHIEVED = "achieved"
GOAL_STATUS_ABANDONED = "abandoned"
GOAL_STATUS_SUPERSEDED = "superseded"
_VALID_GOAL_STATUS_VALUES = frozenset(
    {
        GOAL_STATUS_ACTIVE,
        GOAL_STATUS_ACHIEVED,
        GOAL_STATUS_ABANDONED,
        GOAL_STATUS_SUPERSEDED,
    }
)

GOAL_ORIGIN_SCENARIO = "scenario"
GOAL_ORIGIN_SELF = "self"
_VALID_GOAL_ORIGIN_VALUES = frozenset({GOAL_ORIGIN_SCENARIO, GOAL_ORIGIN_SELF})

# 目的文の上限。プロンプトの【現在の目的】section に載るため、belief の
# 命題 (50字) より長めだが青天井にはしない。
MAX_GOAL_TEXT_CHARS = 200


@dataclass(frozen=True)
class GoalEntry:
    """1 件の目的 (journal エントリ、immutable)。"""

    goal_id: str
    player_id: int
    text: str
    status: str
    locked: bool
    origin: str
    created_tick: int
    created_at: datetime
    supersedes: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.goal_id, str) or not self.goal_id.strip():
            raise GoalEntryValidationException(
                "goal_id must be non-empty str", field="goal_id", value=self.goal_id
            )
        object.__setattr__(self, "goal_id", self.goal_id.strip())

        if not isinstance(self.player_id, int) or isinstance(self.player_id, bool):
            raise GoalEntryValidationException(
                "player_id must be int", field="player_id", value=self.player_id
            )

        if not isinstance(self.text, str) or not self.text.strip():
            raise GoalEntryValidationException(
                "text must be non-empty str", field="text", value=self.text
            )
        object.__setattr__(self, "text", self.text.strip())
        if len(self.text) > MAX_GOAL_TEXT_CHARS:
            raise GoalEntryValidationException(
                f"text must be <= {MAX_GOAL_TEXT_CHARS} chars",
                field="text",
                value=len(self.text),
            )

        if self.status not in _VALID_GOAL_STATUS_VALUES:
            raise GoalEntryValidationException(
                f"status must be one of {sorted(_VALID_GOAL_STATUS_VALUES)}",
                field="status",
                value=self.status,
            )

        if not isinstance(self.locked, bool):
            raise GoalEntryValidationException(
                "locked must be bool", field="locked", value=self.locked
            )

        if self.origin not in _VALID_GOAL_ORIGIN_VALUES:
            raise GoalEntryValidationException(
                f"origin must be one of {sorted(_VALID_GOAL_ORIGIN_VALUES)}",
                field="origin",
                value=self.origin,
            )

        if not isinstance(self.created_tick, int) or isinstance(self.created_tick, bool):
            raise GoalEntryValidationException(
                "created_tick must be int",
                field="created_tick",
                value=self.created_tick,
            )
        if self.created_tick < 0:
            raise GoalEntryValidationException(
                "created_tick must be >= 0",
                field="created_tick",
                value=self.created_tick,
            )

        if not isinstance(self.created_at, datetime):
            raise GoalEntryValidationException(
                "created_at must be datetime",
                field="created_at",
                value=self.created_at,
            )

        if self.supersedes is not None:
            if not isinstance(self.supersedes, str) or not self.supersedes.strip():
                raise GoalEntryValidationException(
                    "supersedes must be non-empty str or None",
                    field="supersedes",
                    value=self.supersedes,
                )
            object.__setattr__(self, "supersedes", self.supersedes.strip())


__all__ = [
    "GoalEntry",
    "GOAL_STATUS_ACTIVE",
    "GOAL_STATUS_ACHIEVED",
    "GOAL_STATUS_ABANDONED",
    "GOAL_STATUS_SUPERSEDED",
    "GOAL_ORIGIN_SCENARIO",
    "GOAL_ORIGIN_SELF",
    "MAX_GOAL_TEXT_CHARS",
]

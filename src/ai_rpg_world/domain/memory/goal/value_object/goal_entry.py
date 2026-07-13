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
    GoalUpdateTextTooLongException,
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

# 目的文の VO 不変条件としての上限 (= 健全性の上限)。プロンプトの【現在の目的】
# section にそのまま載るため青天井にはしないが、値そのものは大きく取る。
#
# 経緯 (HIGH-1 回帰): この上限はもともと 200 字で、GOAL_STORE=ON + 長い目的文の
# シナリオ (survival_island_v2 系, 300 字超) で世界注入 (world_runtime の遅延
# seed) が毎回この上限に阻まれて GoalEntryValidationException → provider が
# ERROR ログ + 空文字へ縮退 →【現在の目的】section 自体が消える、という静かな
# 失敗を起こしていた。シナリオ由来の目的文 (数百字の箇条書き) を VO として正当
# に保持できる必要があるため、VO の上限は「壊れた入力を弾く健全性チェック」
# としてのみ機能させ、大きく引き上げる。
#
# 「エージェントが goal_update で自分で書く目的は短い命題であるべき」という
# 元々の意図はここでは守らない。その制約は goal_update の入口
# (tool schema の maxLength と GoalRevisionApplier の事前チェック) が担う —
# SELF_AUTHORED_GOAL_TEXT_MAX_CHARS と validate_self_authored_goal_text を参照。
MAX_GOAL_TEXT_CHARS = 2000

# goal_update (自筆の言い直し) の入口で守る上限。VO 全体の上限 (上記) より厳しい。
# tool schema の maxLength と一致させる (単一の真実源として ai_rpg_world.
# application.llm.services.tool_catalog.subjective_action がこれを import する)。
SELF_AUTHORED_GOAL_TEXT_MAX_CHARS = 200


def validate_self_authored_goal_text(text: str) -> None:
    """goal_update で書かれた自筆の目的文が入口の上限内かを検証する。

    VO (``GoalEntry``) 自体の上限は健全性チェックまで緩めたため、
    「エージェント自筆の目的は短い命題であるべき」という制約はここで守る。
    tool schema の maxLength (advisory) だけに頼らず、GoalRevisionApplier が
    GoalEntry を構築する前にこの関数を呼び、超過時は
    ``GoalUpdateTextTooLongException`` を投げる (呼び出し側が観測として本人に
    返す拒否経路に載せる)。
    """
    if len(text) > SELF_AUTHORED_GOAL_TEXT_MAX_CHARS:
        raise GoalUpdateTextTooLongException(
            f"self-authored goal text must be <= "
            f"{SELF_AUTHORED_GOAL_TEXT_MAX_CHARS} chars",
            field="text",
            value=len(text),
        )


# P6: active 目的が無いとき (open world 等) の【現在の目的】描画。毎ターン見える
# 欠落自体が「目的を立てる」需要信号になる (goal 設計 §4 G2 / P6)。
GOAL_UNSET_DISPLAY = "(まだ定まっていない)"


def render_current_goal(active_goal: "Optional[GoalEntry]") -> str:
    """【現在の目的】section の本文を返す。active が無ければ未定表示 (P6)。"""
    return active_goal.text if active_goal is not None else GOAL_UNSET_DISPLAY


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
    "SELF_AUTHORED_GOAL_TEXT_MAX_CHARS",
    "validate_self_authored_goal_text",
]

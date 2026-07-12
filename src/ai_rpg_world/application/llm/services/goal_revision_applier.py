"""GoalRevisionApplier — LLM が書いた goal_update を goal store に反映する (P6)。

goal_layer_design_active_inference.md §4 G2 (2026-07-12 改訂): 目的の改訂は
意識 (エージェント自身) が行う。``goal_update`` は全 world-action tool に常時
露出される optional フィールド (schema は tick 間不変) で、非 null のとき本
applier が goal store を supersede 更新する。**書き込みゲート (トリガターン
限定) は無い** — どのターンでも書ける。高度 (目的が次の 1 手に退化しない
こと) は schema 説明文の摩擦と journal 観測で守る (§4 G2)。

- 現在の active 目的が **locked** (シナリオ初期目的) への書き換えは拒否し、
  観測で本人に返す (silent にしない)
- active 目的が unlocked: supersede で新目的 (origin=self) に更新
- active 目的が無い (open world 等): 新目的を追加
"""

from __future__ import annotations

import logging
from typing import Callable, Optional
from uuid import uuid4

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.goal.repository.goal_journal_repository import (
    GoalJournalRepository,
)
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_ORIGIN_SELF,
    GOAL_STATUS_ACTIVE,
    GoalEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_logger = logging.getLogger(__name__)

# locked 目的への書き換えを拒否したとき本人に返す観測文 (§4 G2)。
GOAL_LOCKED_REJECTION_OBSERVATION = (
    "その目的は今は手放せない、と自分でも分かっている。"
)


class GoalRevisionApplier:
    """非 null の goal_update を goal store に反映する。"""

    def __init__(
        self,
        goal_store: GoalJournalRepository,
        *,
        observation_sink: Callable[[PlayerId, str], None],
        current_tick_provider: Callable[[], int],
        now_provider: Callable[[], "object"],
    ) -> None:
        if not isinstance(goal_store, GoalJournalRepository):
            raise TypeError("goal_store must be GoalJournalRepository")
        if not callable(observation_sink):
            raise TypeError("observation_sink must be callable")
        if not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable")
        if not callable(now_provider):
            raise TypeError("now_provider must be callable")
        self._goal_store = goal_store
        self._observation_sink = observation_sink
        self._current_tick_provider = current_tick_provider
        self._now_provider = now_provider

    def apply(
        self, being_id: BeingId, player_id: PlayerId, goal_update_text: Optional[str]
    ) -> Optional[GoalEntry]:
        """goal_update を反映する。反映した新 entry を返す (何もしなければ None)。

        - ``goal_update_text`` が None / 空白のみ: 何もしない (= 目的を変えない)
        - active 目的が locked: 拒否 + 観測 (新 entry は作らない)
        - unlocked active: supersede / active 無し: add
        """
        if not isinstance(goal_update_text, str) or not goal_update_text.strip():
            return None
        text = goal_update_text.strip()

        active = self._goal_store.get_active_by_being(being_id)
        if active is not None and active.locked:
            # 拒否は silent にしない — 本人の意識に観測で返す (§4 G2)。
            self._observation_sink(player_id, GOAL_LOCKED_REJECTION_OBSERVATION)
            return None

        new_entry = GoalEntry(
            goal_id=f"goal-{uuid4().hex}",
            player_id=int(player_id.value),
            text=text,
            status=GOAL_STATUS_ACTIVE,
            locked=False,
            origin=GOAL_ORIGIN_SELF,
            created_tick=self._resolve_tick(),
            created_at=self._now_provider(),
            supersedes=active.goal_id if active is not None else None,
        )
        if active is not None:
            self._goal_store.supersede_by_being(
                being_id, old_goal_id=active.goal_id, new_entry=new_entry
            )
        else:
            self._goal_store.add_by_being(being_id, new_entry)
        return new_entry

    def _resolve_tick(self) -> int:
        try:
            tick = self._current_tick_provider()
        except Exception:
            _logger.debug("current_tick_provider raised; using 0", exc_info=True)
            return 0
        return tick if isinstance(tick, int) and not isinstance(tick, bool) else 0


__all__ = ["GoalRevisionApplier", "GOAL_LOCKED_REJECTION_OBSERVATION"]

"""GoalJournalRepository — 目的 journal の per-Being 保管庫 interface。

P5 (goal_layer_design_active_inference.md G1): belief journal と同型の
per-Being journal (一次キーは ``BeingId``)。改訂は supersede で行い履歴は
消えない (「目的の履歴が自伝になる」= 設計原則 #4 自己の継続性)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import GoalEntry


class GoalJournalRepository(ABC):
    """目的 journal を保持する。一次キーは ``BeingId``。"""

    @abstractmethod
    def add_by_being(self, being_id: BeingId, entry: GoalEntry) -> None:
        """目的エントリを 1 件追加する (seed / 新規目的)。"""

    @abstractmethod
    def list_all_by_being(self, being_id: BeingId) -> list[GoalEntry]:
        """being 配下の全目的エントリを追加順で返す (snapshot capture / 監査用)。"""

    @abstractmethod
    def get_active_by_being(self, being_id: BeingId) -> Optional[GoalEntry]:
        """being の現在 active な目的を返す (無ければ None)。

        【現在の目的】section の描画に使う。active が複数ある実装上の想定は
        しない (見直し G2 は supersede で 1 本に保つ) が、複数あるときは
        最後に追加された active を返す。
        """

    @abstractmethod
    def supersede_by_being(
        self,
        being_id: BeingId,
        *,
        old_goal_id: str,
        new_entry: GoalEntry,
    ) -> None:
        """``old_goal_id`` を superseded にし、``new_entry`` を active で追加する。

        belief journal の supersede と同型。旧エントリは消さず status だけ
        変える (履歴保持)。見直し (G2) からのみ呼ばれる想定。
        """

    @abstractmethod
    def settle_by_being(
        self, being_id: BeingId, *, goal_id: str, outcome_status: str
    ) -> Optional[GoalEntry]:
        """``goal_id`` の active 目的を ``outcome_status`` (achieved / abandoned)

        で閉じる (P8 目的の清算)。閉じた entry を返す。対象が active でない /
        存在しないときは何もせず None を返す (安全な no-op)。supersede と違い
        新しい目的は足さない — 「本人が目的を成し遂げた / 見切った」宣言に対応し、
        履歴は残す (status だけ変える)。``outcome_status`` は ACHIEVED /
        ABANDONED のみ許容する。
        """


    @abstractmethod
    def replace_all_by_being(
        self, being_id: BeingId, entries: list[GoalEntry]
    ) -> None:
        """being 配下を ``entries`` で完全置換する (snapshot restore primitive)。"""


__all__ = ["GoalJournalRepository"]

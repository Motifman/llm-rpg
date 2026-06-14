"""MemoRepository — 「経験を持つ AI」(Being) ごとの memo を保持するリポジトリ。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/interfaces.py::MemoRepository`` を domain に昇格し、
``*Repository`` 命名に統一。

K run (PR #466) で memo が **LLM agent の Plan tier 相当** の役割を担うことが
観測された (全 action の 34% を占めた)。本 Repository が永続化対象の中核となる
(Issue #469 checkpoint Stage 1 でも対象 store の一つ)。

## Phase 3 移行履歴

- Phase 1 PR5: ``application/llm/contracts/`` から ``domain/memory/memo/`` に昇格
- Phase 3 Step 3a-1: ``*_by_being`` API を並走追加
- Phase 3 Step 3a-2: caller を新 API に切替
- Phase 3 Step 3a-3 (本ファイル現状): 旧 ``player_id`` 版 API を撤去し、
  ``being_id`` keyed のみに統一

既知の具象実装は ``InMemoryMemoStore`` (= application/llm/services/) のみ。
新たに MemoRepository を継承する場合は below の 4 abstractmethod を実装すること。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
from ai_rpg_world.domain.memory.memo.value_object.memo_fulfillment_context import (
    MemoFulfillmentContext,
)


class MemoRepository(ABC):
    """Being ごとの memo を保持する。

    LLM が context に固定したい情報 (タスク / 目標 / 戦略メモ / 注意事項など) を
    扱う。``add_by_being`` には optional な ``current_tick`` を渡せる: age 表示 /
    stale 判定用。``complete_by_being`` には ``fulfillment_context`` (周辺
    sliding_window 抜粋) を渡せる: 後で episodic cue 経由で recall するときに
    「達成時の状況」を辿る情報源となる。
    """

    @abstractmethod
    def add_by_being(
        self,
        being_id: BeingId,
        content: str,
        *,
        current_tick: int | None = None,
    ) -> str:
        """being_id keyed で memo を追加し、生成された ID を返す。"""

    @abstractmethod
    def list_uncompleted_by_being(self, being_id: BeingId) -> list[MemoEntry]:
        """being_id keyed で未完了 memo を新しい順で返す。"""

    @abstractmethod
    def complete_by_being(
        self,
        being_id: BeingId,
        memo_id: str,
        *,
        fulfillment_context: MemoFulfillmentContext | None = None,
    ) -> bool:
        """being_id keyed で memo を完了する。存在しなければ False。"""

    @abstractmethod
    def remove_by_being(self, being_id: BeingId, memo_id: str) -> bool:
        """being_id keyed で memo を削除する。存在しなければ False。"""

    @abstractmethod
    def list_all_by_being(self, being_id: BeingId) -> list[MemoEntry]:
        """being_id keyed で **完了済も含む** 全 memo を保持順 (= 古い→新しい) で返す。

        Phase 4 Step 4-2 (Issue #470): ``BeingMemorySnapshotService`` が
        run 途中再開のため snapshot を取る際に呼ぶ。``list_uncompleted_by_being``
        は LLM 走行時の active list だけを返すので、完了済 memo の永続化に
        足りない。
        """

    @abstractmethod
    def replace_all_by_being(
        self, being_id: BeingId, entries: list[MemoEntry]
    ) -> None:
        """being_id 配下を ``entries`` で完全置換する (= restore primitive)。

        Phase 4 Step 4-2: snapshot restore 用。**既存エントリは全て削除** され
        ``entries`` の順序通りに再構築される。memo_id は ``entries`` 側の値を
        そのまま使う (= ``add_by_being`` のような uuid 自動生成は行わない)。

        Snapshot 経路以外からの呼び出しは想定しない (= destructive overwrite
        なので一般 use case で安易に使わないこと)。
        """


__all__ = ["MemoRepository"]

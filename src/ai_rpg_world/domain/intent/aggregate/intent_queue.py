"""``IntentQueue`` 集約。

tick 単位の intent 群をフェーズ・優先度・seed 順で決定論的に取り出すための
集約。マルチエージェント世界の「同時性」をこの集約が定義する。

不変条件
--------
- 同一プレイヤーは同一 tick に複数の intent を持てない (LLM の "1 ターン 1
  ツール" の規約を BC レベルで保証する)。
- ``drain_ready_for_tick`` で取り出された intent は queue から除去される。
- 未解決 (complete_at_tick が未来) の intent は queue 内に残り、将来の tick
  まで持ち越される。

同時性の決定論
--------------
``drain_ready_for_tick`` の戻り値は以下のキーで安定ソート:

1. ``phase.value`` 昇順 (フェーズ順 — MOVEMENT が先)
2. ``priority.value`` 降順 (高優先度が先)
3. ``submitted_at_tick.value`` 昇順 (早く投稿された方が先)
4. ``intent_id.value`` 昇順 (タイブレーカー — 投入順を保証)

これにより同 tick に 2 体が同じ動作を投稿しても、ID 採番順で勝者が決まる
(後述の resolution service が「片方成功 / 片方 LOST_RACE」を判定可能)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.intent.exception.intent_exception import (
    DuplicateIntentForPlayerException,
    IntentValidationException,
    UnknownIntentException,
)
from ai_rpg_world.domain.intent.value_object.intent import Intent
from ai_rpg_world.domain.intent.value_object.intent_id import IntentId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _sort_key(intent: Intent) -> tuple[int, int, int, int]:
    return (
        intent.phase.value,
        -intent.priority.value,
        intent.submitted_at_tick.value,
        intent.intent_id.value,
    )


@dataclass
class IntentQueue:
    """Tick 内 intent をフェーズ順で決定論的に取り出す集約。"""

    _items: list[Intent] = field(default_factory=list)

    def submit(self, intent: Intent) -> None:
        if not isinstance(intent, Intent):
            raise IntentValidationException("intent must be Intent")
        # VO の __eq__ で比較する (PlayerId が将来フィールド追加された時も追従)
        for existing in self._items:
            if (
                existing.player_id == intent.player_id
                and existing.submitted_at_tick == intent.submitted_at_tick
            ):
                raise DuplicateIntentForPlayerException(
                    "player already submitted an intent in this tick",
                    player_id=intent.player_id.value,
                    tick=intent.submitted_at_tick.value,
                )
        self._items.append(intent)

    def drain_ready_for_tick(self, current_tick: WorldTick) -> list[Intent]:
        """``complete_at_tick <= current_tick`` の intent をフェーズ順で取り出す。

        取り出した intent は queue から除去される。未来の intent
        (``complete_at_tick > current_tick``) は queue 内に残る。
        """
        if not isinstance(current_tick, WorldTick):
            raise IntentValidationException("current_tick must be WorldTick")
        ready = [
            i
            for i in self._items
            if i.complete_at_tick.value <= current_tick.value
        ]
        self._items = [
            i
            for i in self._items
            if i.complete_at_tick.value > current_tick.value
        ]
        ready.sort(key=_sort_key)
        return ready

    def pending(self) -> list[Intent]:
        """queue 内の全 intent (resolve 前) のスナップショット。テスト用。"""
        return list(self._items)

    def pending_for(self, player_id: PlayerId) -> list[Intent]:
        """指定プレイヤーが queue に乗せている intent。"""
        return [i for i in self._items if i.player_id == player_id]

    def remove(self, intent_id: IntentId) -> Intent:
        """ID 指定で intent を取り消す (LLM が割り込みで cancel 操作する想定)。"""
        for idx, item in enumerate(self._items):
            if item.intent_id.value == intent_id.value:
                del self._items[idx]
                return item
        raise UnknownIntentException(
            "intent not found in queue", intent_id=intent_id.value
        )

    def size(self) -> int:
        return len(self._items)

    def extend(self, intents: Iterable[Intent]) -> None:
        """submit を複数まとめて行うヘルパー (all-or-none)。

        途中の intent でバリデーションが失敗した場合は queue の状態を呼び出し
        前にロールバックし、例外を再送出する。partial commit による集約状態の
        不整合を避けるため。
        """
        snapshot = list(self._items)
        try:
            for intent in intents:
                self.submit(intent)
        except Exception:
            self._items = snapshot
            raise

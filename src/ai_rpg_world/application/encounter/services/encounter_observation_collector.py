"""``EncounterObservationCollector``: 観測から familiarity 信号を抽出する collector。

ObservationAppender が 1 件の observation を player に届けるたびに本 collector の
``on_observation`` を呼ぶ。collector は observation の ``structured`` field を読み、
encounter 対象 (entity / spot / event-type) を判定して
``IEncounterMemory.observe`` を呼ぶ。

設計判断 (PR3):

- **責務を 1 つに絞る**。「observation を解釈して encounter signal を抽出する」だけ。
  ObservationAppender に直接書くと append の責務が肥大化するため、別 class として
  独立させる
- **抽出ロジックは保守的に**。PR3 では entity_entered_spot (= 他 player との
  同 spot 観測) と scenario_event (= 物語イベント) の 2 種類だけを encounter
  として記録する。spot 自体の encounter (= 「自分が新しい spot に着いた」) は
  PR4 で別経路 (do_move の完了 hook) から記録する
- **silent failure を避ける**。observe 中の例外は本来の observation pipeline を
  止めないが、debug ログだけは残す
- **同 tick で同じ key が複数回観測されても count は正しく進む** (= 同 spot で
  複数 observation が起きる経路を考慮、PR1 の挙動と整合)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional

from ai_rpg_world.application.encounter.contracts.interfaces import (
    IEncounterMemory,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    # circular import 回避: ObservationOutput は ``application.observation``
    # 側で定義されるが、そちら経由で ``llm.services`` → ``observation`` の
    # ループに入る。collector は ObservationOutput の structured 属性しか触ら
    # ないので、type hint のみで参照する。
    from ai_rpg_world.application.observation.contracts.dtos import (
        ObservationOutput,
    )


_logger = logging.getLogger(__name__)


# observation の ``structured.type`` 値。PR3 で取り扱う種別。
_TYPE_ENTITY_ENTERED_SPOT = "entity_entered_spot"
_TYPE_SCENARIO_EVENT = "scenario_event"


class EncounterObservationCollector:
    """1 件の observation から encounter signal を抽出して memory に記録する。

    本 collector は **読み取り側** (= 観測した player) の視点で記録する。
    ``entity_entered_spot`` 観測なら、観測した player が actor に対する encounter
    を持つ (= 「私は actor を見た」)。``scenario_event`` なら、観測した player
    がその event を経験した記録になる。
    """

    def __init__(
        self,
        memory: IEncounterMemory,
        current_tick_provider: Callable[[], int],
    ) -> None:
        if not isinstance(memory, IEncounterMemory):
            raise TypeError(
                f"memory must be IEncounterMemory (got {type(memory)!r})"
            )
        if not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable")
        self._memory = memory
        self._current_tick_provider = current_tick_provider

    def on_observation(
        self,
        player_id: PlayerId,
        output: ObservationOutput,
    ) -> None:
        """observation 1 件を解釈して encounter を記録する。

        例外は飲み込まず、log + 続行する。silent failure を防ぐが、本来の
        observation pipeline を破壊するのも避けたい (= encounter は補助記憶層、
        本流は止めない)。
        """
        try:
            self._on_observation_impl(player_id, output)
        except Exception:
            _logger.exception(
                "EncounterObservationCollector.on_observation failed "
                "(player_id=%s, type=%r); skipping",
                player_id.value,
                (output.structured or {}).get("type"),
            )

    # ────────────────────────────────────────────────────────
    # 内部ロジック
    # ────────────────────────────────────────────────────────

    def _on_observation_impl(
        self,
        player_id: PlayerId,
        output: ObservationOutput,
    ) -> None:
        structured = output.structured or {}
        if not isinstance(structured, Mapping):
            return
        type_ = structured.get("type")
        if type_ == _TYPE_ENTITY_ENTERED_SPOT:
            self._handle_entity_entered_spot(player_id, structured)
        elif type_ == _TYPE_SCENARIO_EVENT:
            self._handle_scenario_event(player_id, structured)
        # それ以外の type は PR3 のスコープ外。silent skip。

    def _handle_entity_entered_spot(
        self,
        player_id: PlayerId,
        structured: Mapping[str, Any],
    ) -> None:
        """「他 player が同 spot に入った」観測から actor encounter を記録する。

        actor の解決は ``actor`` field (= 表示名 / 安定名) を使う。EntityId 数値が
        欲しい場合は ``entity_id_value`` 等を見るが、PR3 では「人として識別できる
        名前」を優先する (= 同じ人物が ID 再採番されても継続性を保つため、表示名
        ベースで encounter する)。
        """
        actor = structured.get("actor")
        if not isinstance(actor, str) or not actor.strip():
            return
        self._observe(player_id, EncounterKey.player(actor.strip()))

    def _handle_scenario_event(
        self,
        player_id: PlayerId,
        structured: Mapping[str, Any],
    ) -> None:
        event_id = structured.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            return
        self._observe(player_id, EncounterKey.event(event_id.strip()))

    def _observe(self, player_id: PlayerId, key: EncounterKey) -> None:
        current_tick = self._safe_current_tick()
        if current_tick is None:
            # tick が取れない (= provider が None を返す等) なら encounter
            # 記録を諦める。silent skip。debug ログだけ残す。
            _logger.debug(
                "EncounterObservationCollector: current_tick unavailable; "
                "skipping observe(player=%s, key=%s)",
                player_id.value,
                key.canonical,
            )
            return
        self._memory.observe(player_id, key, current_tick)

    def _safe_current_tick(self) -> Optional[int]:
        try:
            tick = self._current_tick_provider()
        except Exception:
            _logger.exception(
                "EncounterObservationCollector: current_tick_provider raised"
            )
            return None
        if not isinstance(tick, int) or isinstance(tick, bool):
            return None
        if tick < 0:
            return None
        return tick


__all__ = ["EncounterObservationCollector"]

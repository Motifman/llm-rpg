"""ターンの終わりの清算で決めた欄の選択と体の帯を、次にプロンプトを組むときへ渡す (#1414)。

run の中だけで持ち、snapshot に入れない。1 ターンで作り直せる一時的な状態で、
失っても次の清算で戻る (design_decisions D1414-3)。

選択は清算したターンの番号と一緒に持つ。プロンプトは次の手を受け取ってターンを
進める前に組むので、清算したターンと同じ番号のときだけ使う。清算が呼ばれなかった
ターンに、前の場面の選択を使い回さない。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.application.being.recall.body_band import BodyBandReading
from ai_rpg_world.application.being.recall.situation import FieldSelection
from ai_rpg_world.domain.being.value_object.being_id import BeingId

DEGRADED_NO_SELECTION = "no_selection"
DEGRADED_STALE_SELECTION = "stale_selection"
#: 清算を切った run。最初のターンや再開した直後の no_selection と分けて数えられるようにする。
DEGRADED_SETTLEMENT_DISABLED = "settlement_disabled"
#: 清算は欄を選んだが、帯を渡さなかった。清算がまだ無い no_selection と分ける。
DEGRADED_BAND_NOT_READ = "band_not_read"


@dataclass(frozen=True)
class _Settled:
    turn: int
    selection: FieldSelection
    band: BodyBandReading | None


class NextTurnFieldSelections:
    def __init__(self) -> None:
        self._by_being: dict[BeingId, _Settled] = {}

    def put(
        self,
        being_id: BeingId,
        *,
        settled_turn: int,
        selection: FieldSelection,
        band: BodyBandReading | None = None,
    ) -> None:
        if not isinstance(selection, FieldSelection):
            raise TypeError("selection must be FieldSelection")
        if band is not None and not isinstance(band, BodyBandReading):
            raise TypeError("band must be BodyBandReading or None")
        self._by_being[being_id] = _Settled(settled_turn, selection, band)

    def for_prompt(self, being_id: BeingId, *, current_turn: int) -> FieldSelection:
        settled = self._settled(being_id, current_turn)
        if isinstance(settled, tuple):
            return FieldSelection.degraded(*settled)
        return settled.selection

    def band_for_prompt(self, being_id: BeingId, *, current_turn: int) -> BodyBandReading:
        """欄の選択と同じ決まりで、清算したターンの帯を渡す。"""
        settled = self._settled(being_id, current_turn)
        if isinstance(settled, tuple):
            return BodyBandReading.degraded(*settled)
        if settled.band is None:
            return BodyBandReading.degraded(
                DEGRADED_BAND_NOT_READ, "the settlement did not read the body band"
            )
        return settled.band

    def _settled(self, being_id: BeingId, current_turn: int) -> _Settled | tuple[str, str]:
        settled = self._by_being.get(being_id)
        if settled is None:
            return DEGRADED_NO_SELECTION, "no settlement has chosen fields for this being yet"
        if settled.turn != current_turn:
            return (
                DEGRADED_STALE_SELECTION,
                f"selection was settled at turn {settled.turn}, prompt is at turn {current_turn}",
            )
        return settled


__all__ = [
    "DEGRADED_BAND_NOT_READ",
    "DEGRADED_NO_SELECTION",
    "DEGRADED_SETTLEMENT_DISABLED",
    "DEGRADED_STALE_SELECTION",
    "NextTurnFieldSelections",
]
